"""Staging-only agentic recovery experiment.

This module deliberately has no FastAPI route and is not imported by the
recommendation endpoint.  It investigates evidence *about* an already-created
shortlist; it cannot add candidates, calculate ranks, or affect selection.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Callable, Mapping

from .programming import HttpOpener, ProviderUnavailable, _json_request
from .recommendations import QlooError, QlooHttpAdapter


MODEL = "deepseek-flash"
INPUT_PRICE_PER_MILLION = 0.30
OUTPUT_PRICE_PER_MILLION = 1.20
_TOOLS = frozenset({
    "inspect_qloo_themes",
    "inspect_movie_evidence",
    "query_qloo_focused",
    "inspect_audience_coverage",
})
FocusedQlooExecutor = Callable[[str, str, list[str], str, tuple[str, ...]], Mapping[str, object]]


@dataclass(frozen=True)
class ToolTranscript:
    name: str
    arguments: dict[str, object]
    result: dict[str, object]


@dataclass(frozen=True)
class RecoveryOutcome:
    decision: str
    observation: str
    uncertainty: str
    evidence_refs: tuple[str, ...]
    tool_transcript: tuple[ToolTranscript, ...]
    stopping_reason: str
    model_turns: int
    input_tokens: int
    output_tokens: int
    estimated_cost_usd: float
    latency_ms: int


def _usage(response: Mapping[str, object]) -> tuple[int, int]:
    raw = response.get("usage")
    raw = raw if isinstance(raw, Mapping) else {}
    values = (raw.get("input_tokens", 0), raw.get("output_tokens", 0))
    return tuple(value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else 0 for value in values)  # type: ignore[return-value]


def _cost(input_tokens: int, output_tokens: int) -> float:
    return (input_tokens * INPUT_PRICE_PER_MILLION + output_tokens * OUTPUT_PRICE_PER_MILLION) / 1_000_000


def _text(response: Mapping[str, object]) -> str | None:
    direct = response.get("output_text")
    if isinstance(direct, str):
        return direct
    output = response.get("output")
    if not isinstance(output, list):
        return None
    for item in output:
        if not isinstance(item, Mapping) or item.get("type") != "message":
            continue
        content = item.get("content")
        if not isinstance(content, list):
            continue
        for part in content:
            if isinstance(part, Mapping) and part.get("type") in {"output_text", "text"} and isinstance(part.get("text"), str):
                return str(part["text"])
    return None


def _one_function_call(response: Mapping[str, object]) -> Mapping[str, object] | None:
    output = response.get("output")
    if not isinstance(output, list):
        return None
    calls = [item for item in output if isinstance(item, Mapping) and item.get("type") == "function_call"]
    return calls[0] if len(calls) == 1 else None


class RecoveryEvidenceRegistry:
    """Typed, read-only evidence boundary for one frozen or staging packet.

    Focused-query results are pre-registered evidence and may only describe
    members of the existing deterministic shortlist.  They are never used to
    merge or compare Qloo affinity scores from separate queries.
    """

    def __init__(self, packet: Mapping[str, object], *, focused_query_executor: FocusedQlooExecutor | None = None) -> None:
        self.packet = packet
        self._focused_query_executor = focused_query_executor
        self.shortlist = tuple(str(item) for item in packet.get("shortlist", []) if isinstance(item, str))
        mappings = [item for item in packet.get("mappings", []) if isinstance(item, Mapping)]
        # Recovery fixtures use the compact qloo_entities shape; the older
        # value experiment packet carries the same facts in mappings.
        mappings.extend(
            {
                "qloo_entity_id": item.get("id"),
                "qloo_type": item.get("type"),
                "tmdb_media_type": "tv" if item.get("type") == "urn:entity:tv_show" else "movie",
            }
            for item in packet.get("qloo_entities", [])
            if isinstance(item, Mapping)
        )
        self._entities = {
            str(item["qloo_entity_id"]): item
            for item in mappings
            if isinstance(item.get("qloo_entity_id"), str)
        }
        self._candidate_evidence = packet.get("candidate_evidence")
        self._candidate_evidence = self._candidate_evidence if isinstance(self._candidate_evidence, Mapping) else {}
        self._themes = packet.get("qloo_themes")
        self._themes = self._themes if isinstance(self._themes, Mapping) else {}
        self._focused = packet.get("focused_query_results")
        self._focused = self._focused if isinstance(self._focused, Mapping) else {}

    @staticmethod
    def _exact_keys(args: Mapping[str, object], allowed: set[str], required: set[str]) -> bool:
        return set(args) <= allowed and required <= set(args)

    def available_evidence(self) -> dict[str, object]:
        """Advertise evidence *availability*, never the evidence itself."""
        titles = [title for title in self.shortlist if title in self._candidate_evidence]
        titles.extend(
            str(item.get("title"))
            for item in self._candidate_evidence.values()
            if isinstance(item, Mapping) and isinstance(item.get("title"), str) and str(item["title"]) in self.shortlist
        )
        return {
            "theme_entity_ids": sorted(key for key, tags in self._themes.items() if isinstance(tags, list)),
            "candidate_titles_with_evidence": sorted(set(titles)),
            "coverage_available": True,
            "focused_query_registered": bool(self._focused) or self._focused_query_executor is not None,
        }

    def execute(self, name: str, args: dict[str, object]) -> dict[str, object]:
        if name not in _TOOLS:
            raise ValueError("unpermitted recovery tool")
        if name == "inspect_audience_coverage":
            if args:
                raise ValueError("coverage inspection takes no arguments")
            coverage = self.packet.get("coverage")
            unresolved = [item for item in self.packet.get("mappings", []) if isinstance(item, Mapping) and item.get("resolution")]
            if isinstance(coverage, Mapping):
                unresolved.extend({"title": title, "resolution": "unresolved"} for title in coverage.get("unresolved", []) if isinstance(title, str))
            return {
                "coverage": self.packet.get("coverage"),
                "unresolved_mappings": unresolved,
            }
        if name == "inspect_qloo_themes":
            if not self._exact_keys(args, {"entity_id", "media_type"}, {"entity_id", "media_type"}):
                raise ValueError("invalid themes arguments")
            entity_id, media_type = args.get("entity_id"), args.get("media_type")
            entity = self._entities.get(entity_id) if isinstance(entity_id, str) else None
            expected_media_type = entity.get("tmdb_media_type") if entity is not None else None
            if expected_media_type not in {"movie", "tv"}:
                expected_media_type = "tv" if entity is not None and entity.get("qloo_type") == "urn:entity:tv_show" else "movie"
            if entity is None or media_type != expected_media_type:
                raise ValueError("unverified entity or media type")
            tags = self._themes.get(entity_id, [])
            if not isinstance(tags, list) or not all(isinstance(tag, str) and 0 < len(tag) <= 80 for tag in tags):
                raise ValueError("unverified theme evidence")
            return {"entity_id": entity_id, "media_type": media_type, "tags": tags}
        if name == "inspect_movie_evidence":
            if not self._exact_keys(args, {"candidate_title"}, {"candidate_title"}):
                raise ValueError("invalid movie evidence arguments")
            title = args.get("candidate_title")
            evidence = self._candidate_evidence.get(title) if isinstance(title, str) and title in self.shortlist else None
            if evidence is None and isinstance(title, str) and title in self.shortlist:
                evidence = next((item for item in self._candidate_evidence.values() if isinstance(item, Mapping) and item.get("title") == title), None)
            if not isinstance(evidence, Mapping):
                raise ValueError("unverified candidate")
            return {"candidate_title": title, "evidence": dict(evidence)}
        # A focused query may use only signals registered as verified themes.
        if not self._exact_keys(args, {"entity_id", "media_type", "tags", "question"}, {"entity_id", "media_type", "tags", "question"}):
            raise ValueError("invalid focused query arguments")
        entity_id, media_type, tags, question = args.get("entity_id"), args.get("media_type"), args.get("tags"), args.get("question")
        entity = self._entities.get(entity_id) if isinstance(entity_id, str) else None
        allowed_tags = self._themes.get(entity_id, []) if isinstance(entity_id, str) else []
        expected_media_type = entity.get("tmdb_media_type") if entity is not None else None
        if expected_media_type not in {"movie", "tv"}:
            expected_media_type = "tv" if entity is not None and entity.get("qloo_type") == "urn:entity:tv_show" else "movie"
        if entity is None or media_type != expected_media_type or not isinstance(tags, list) or not all(isinstance(tag, str) and tag in allowed_tags for tag in tags) or not isinstance(question, str) or not 0 < len(question.strip()) <= 160:
            raise ValueError("unverified focused-query signal")
        key = f"{entity_id}|{'|'.join(sorted(tags))}"
        result = (
            self._focused_query_executor(entity_id, str(expected_media_type), list(tags), question, self.shortlist)
            if self._focused_query_executor is not None
            else self._focused.get(key)
        )
        if not isinstance(result, Mapping):
            raise ValueError("no registered focused-query evidence")
        mentioned = result.get("candidate_titles", [])
        if not isinstance(mentioned, list) or not all(isinstance(title, str) and title in self.shortlist for title in mentioned):
            raise ValueError("focused query introduced a candidate")
        if any(key in result for key in ("rank", "score", "raw_score")):
            raise ValueError("focused query cannot supply ranking evidence")
        return dict(result)


def qloo_focused_executor(adapter: QlooHttpAdapter) -> FocusedQlooExecutor:
    """Return a backend-only, read-only Insights adapter for staging research.

    Qloo's safely configured signal here is the verified selected entity. Tags
    are validated by the registry and remain provenance for the investigator's
    question; they are not sent as an undocumented provider parameter.  The
    response is filtered to the immutable existing shortlist and intentionally
    strips provider scores and positions.
    """
    def execute(entity_id: str, _media_type: str, _tags: list[str], _question: str, shortlist: tuple[str, ...]) -> Mapping[str, object]:
        data = adapter._request_json(  # backend-only adapter; never exposed to a browser
            adapter.ranking_path or "/v2/insights",
            query={
                "filter.type": "urn:entity:movie",
                "signal.interests.entities": entity_id,
                "take": "12",
            },
        )
        titles: list[str] = []
        for item in adapter._items(data):
            candidate = adapter._candidate(item)
            if candidate is not None and candidate.title in shortlist and candidate.title not in titles:
                titles.append(candidate.title)
        return {
            "candidate_titles": titles,
            "query": {"filter.type": "urn:entity:movie", "signal.interests.entities": entity_id},
            "evidence": "Focused Qloo response filtered to the existing deterministic shortlist; no provider scores or ranks retained.",
        }
    return execute


def deterministic_recovery(registry: RecoveryEvidenceRegistry) -> RecoveryOutcome:
    """C0: fixed, transparent evidence recovery for comparison with the agent."""
    packet = registry.packet
    raw_coverage = packet.get("coverage", "")
    coverage = str(raw_coverage).casefold()
    has_unresolved = any(isinstance(item, Mapping) and item.get("resolution") for item in packet.get("mappings", []))
    conflict = isinstance(raw_coverage, Mapping) and raw_coverage.get("conflict") is True
    below_threshold = (isinstance(raw_coverage, Mapping) and raw_coverage.get("threshold_met") is False) or "below" in coverage or "sparse" in coverage
    if below_threshold or has_unresolved or conflict:
        evidence = registry.execute("inspect_audience_coverage", {})
        unresolved = evidence.get("unresolved_mappings", [])
        decision = "clarification_needed" if conflict or any(isinstance(item, Mapping) and item.get("title") == "AOT" for item in unresolved if isinstance(unresolved, list)) else "abstain"
        return RecoveryOutcome(decision, "Coverage evidence contains unresolved, conflicting, or insufficient input.", "A complete shortlist cannot repair missing or contradictory audience evidence.", ("tool:inspect_audience_coverage",), (ToolTranscript("inspect_audience_coverage", {}, evidence),), "deterministic_coverage_check", 0, 0, 0, 0.0, 0)
    return RecoveryOutcome("accept_existing_shortlist", "The deterministic recovery rule found no predefined evidence gap requiring lookup.", "No new evidence was requested by C0.", ("packet:scenario",), (), "deterministic_no_lookup", 0, 0, 0, 0.0, 0)


class DeepSeekRecoveryExperiment:
    """Maximum-three-turn, two-lookup recovery loop for staging experiments."""

    max_model_turns = 3
    max_lookups = 2
    max_focused_queries = 1

    def __init__(self, api_key: str, opener: HttpOpener, *, max_cost_usd: float = 0.10) -> None:
        self.api_key, self.opener, self.max_cost_usd = api_key, opener, max(0.0, min(max_cost_usd, 0.10))

    @staticmethod
    def _fallback(reason: str, *, turns: int = 0, input_tokens: int = 0, output_tokens: int = 0, latency_ms: int = 0, transcript: tuple[ToolTranscript, ...] = ()) -> RecoveryOutcome:
        return RecoveryOutcome("abstain", "No experimental recovery conclusion was accepted.", "The deterministic shortlist remains unchanged because evidence recovery was unavailable or invalid.", ("packet:scenario",), transcript, reason, turns, input_tokens, output_tokens, _cost(input_tokens, output_tokens), latency_ms)

    @staticmethod
    def _tools() -> list[dict[str, object]]:
        return [
            {"type": "function", "name": "inspect_qloo_themes", "description": "Read verified Qloo theme tags for one selected interest. Use only if tags could resolve a stated uncertainty.", "parameters": {"type": "object", "properties": {"entity_id": {"type": "string"}, "media_type": {"type": "string", "enum": ["movie", "tv"]}}, "required": ["entity_id", "media_type"], "additionalProperties": False}},
            {"type": "function", "name": "inspect_movie_evidence", "description": "Read verified stored evidence for one existing deterministic candidate.", "parameters": {"type": "object", "properties": {"candidate_title": {"type": "string"}}, "required": ["candidate_title"], "additionalProperties": False}},
            {"type": "function", "name": "query_qloo_focused", "description": "One registered read-only Qloo investigation for a selected entity using only verified tags. It cannot discover candidates or return rankings.", "parameters": {"type": "object", "properties": {"entity_id": {"type": "string"}, "media_type": {"type": "string", "enum": ["movie", "tv"]}, "tags": {"type": "array", "items": {"type": "string"}, "maxItems": 4}, "question": {"type": "string", "maxLength": 160}}, "required": ["entity_id", "media_type", "tags", "question"], "additionalProperties": False}},
            {"type": "function", "name": "inspect_audience_coverage", "description": "Read existing coverage and unresolved-preference evidence before deciding whether to abstain or clarify.", "parameters": {"type": "object", "properties": {}, "additionalProperties": False}},
        ]

    @staticmethod
    def _output_schema() -> dict[str, object]:
        """Provider-enforced shape; local evidence closure remains mandatory."""
        return {
            "type": "object",
            "additionalProperties": False,
            "required": ["decision", "observation", "uncertainty", "evidence_refs", "stopping_reason"],
            "properties": {
                "decision": {"type": "string", "enum": ["accept_existing_shortlist", "clarification_needed", "abstain"]},
                "observation": {"type": "string", "minLength": 1, "maxLength": 600},
                "uncertainty": {"type": "string", "minLength": 1, "maxLength": 400},
                "evidence_refs": {"type": "array", "minItems": 1, "uniqueItems": True, "items": {"type": "string", "pattern": "^(packet:scenario|tool:(inspect_qloo_themes|inspect_movie_evidence|query_qloo_focused|inspect_audience_coverage))$"}},
                "stopping_reason": {"type": "string", "minLength": 1, "maxLength": 160},
            },
        }

    @staticmethod
    def _final(text: str | None, refs: set[str]) -> tuple[str, str, str, tuple[str, ...], str] | None:
        try:
            data = json.loads(text or "")
        except ValueError:
            return None
        if not isinstance(data, Mapping) or data.get("decision") not in {"accept_existing_shortlist", "clarification_needed", "abstain"}:
            return None
        observation, uncertainty, stopping = data.get("observation"), data.get("uncertainty"), data.get("stopping_reason")
        evidence_refs = data.get("evidence_refs")
        if not all(isinstance(value, str) and value.strip() and len(value) <= maximum for value, maximum in ((observation, 600), (uncertainty, 400), (stopping, 160))):
            return None
        if not isinstance(evidence_refs, list) or not evidence_refs or not all(isinstance(ref, str) and ref in refs for ref in evidence_refs):
            return None
        # Candidate nomination or numerical re-ranking must be impossible in
        # the model's final structured response.
        if any(key in data for key in ("candidate", "candidate_title", "rank", "score", "recommended_title")):
            return None
        return str(data["decision"]), observation.strip(), uncertainty.strip(), tuple(evidence_refs), stopping.strip()

    def run(self, *, organizer_objective: str, attendee_reasons: list[str], registry: RecoveryEvidenceRegistry) -> RecoveryOutcome:
        if not self.api_key:
            return self._fallback("missing_api_key")
        started, input_tokens, output_tokens = time.monotonic(), 0, 0
        transcript: list[ToolTranscript] = []
        focused_queries = 0
        evidence_refs = {"packet:scenario"}
        context = {"organizer_objective": organizer_objective[:500], "attendee_reasons": attendee_reasons[:12], "shortlist": registry.shortlist, "coverage": registry.packet.get("coverage"), "mappings": registry.packet.get("mappings", []), "recovery_trigger": registry.packet.get("recovery_trigger"), "available_evidence": registry.available_evidence()}
        instructions = (
            "You are a staging-only CineBridge recovery investigator. The existing deterministic shortlist, eligibility, and order are immutable. "
            "Investigate only a concrete uncertainty that a permitted read could resolve; do not call a tool merely to appear agentic. "
            "If recovery_trigger identifies an evidence gap and a listed tool can directly inspect it, make that one read before your final decision. "
            "You may make up to two read-only lookups total and at most one query_qloo_focused call. "
            "Never request new candidates, raw scores, ranking, availability, rights, or unverified tags. "
            "When finished return JSON only: decision (accept_existing_shortlist|clarification_needed|abstain), observation, uncertainty, evidence_refs, stopping_reason. "
            "evidence_refs is mandatory: use exactly packet:scenario for packet facts and exactly tool:<tool name> for each tool result used; never write descriptive citations. "
            "Do not include candidate, candidate_title, rank, score, or recommended_title fields."
        )
        history: list[object] = [{"role": "user", "content": json.dumps(context, ensure_ascii=False)}]
        for turn in range(1, self.max_model_turns + 1):
            try:
                response = _json_request("https://api.deepseek.com/responses", {"model": MODEL, "instructions": instructions, "input": history, "tools": self._tools(), "max_output_tokens": 400, "reasoning": {"effort": "none"}, "text": {"format": {"type": "json_schema", "name": "recovery_outcome", "schema": self._output_schema()}}}, self.api_key, self.opener)
            except ProviderUnavailable:
                return self._fallback("provider_unavailable", turns=turn, input_tokens=input_tokens, output_tokens=output_tokens, latency_ms=int((time.monotonic() - started) * 1000), transcript=tuple(transcript))
            added_input, added_output = _usage(response)
            input_tokens += added_input
            output_tokens += added_output
            if response.get("status") == "incomplete":
                return self._fallback("provider_incomplete", turns=turn, input_tokens=input_tokens, output_tokens=output_tokens, latency_ms=int((time.monotonic() - started) * 1000), transcript=tuple(transcript))
            if _cost(input_tokens, output_tokens) > self.max_cost_usd:
                return self._fallback("per_run_cost_cap", turns=turn, input_tokens=input_tokens, output_tokens=output_tokens, latency_ms=int((time.monotonic() - started) * 1000), transcript=tuple(transcript))
            call = _one_function_call(response)
            if call is None:
                final = self._final(_text(response), evidence_refs)
                if final is None:
                    return self._fallback("invalid_final_response", turns=turn, input_tokens=input_tokens, output_tokens=output_tokens, latency_ms=int((time.monotonic() - started) * 1000), transcript=tuple(transcript))
                decision, observation, uncertainty, refs, stopping = final
                return RecoveryOutcome(decision, observation, uncertainty, refs, tuple(transcript), stopping, turn, input_tokens, output_tokens, _cost(input_tokens, output_tokens), int((time.monotonic() - started) * 1000))
            if len(transcript) >= self.max_lookups:
                return self._fallback("lookup_limit_reached", turns=turn, input_tokens=input_tokens, output_tokens=output_tokens, latency_ms=int((time.monotonic() - started) * 1000), transcript=tuple(transcript))
            name, call_id, raw_args = call.get("name"), call.get("call_id"), call.get("arguments")
            if not isinstance(name, str) or name not in _TOOLS or not isinstance(call_id, str) or not isinstance(raw_args, str):
                return self._fallback("invalid_tool_request", turns=turn, input_tokens=input_tokens, output_tokens=output_tokens, latency_ms=int((time.monotonic() - started) * 1000), transcript=tuple(transcript))
            if name == "query_qloo_focused":
                focused_queries += 1
                if focused_queries > self.max_focused_queries:
                    return self._fallback("focused_query_limit_reached", turns=turn, input_tokens=input_tokens, output_tokens=output_tokens, latency_ms=int((time.monotonic() - started) * 1000), transcript=tuple(transcript))
            try:
                args = json.loads(raw_args)
                if not isinstance(args, dict):
                    raise ValueError("arguments")
                tool_result = registry.execute(name, args)
            except (QlooError, TypeError, ValueError):
                return self._fallback("invalid_tool_arguments", turns=turn, input_tokens=input_tokens, output_tokens=output_tokens, latency_ms=int((time.monotonic() - started) * 1000), transcript=tuple(transcript))
            transcript.append(ToolTranscript(name, args, tool_result))
            evidence_refs.add(f"tool:{name}")
            output = response.get("output")
            history.extend(output if isinstance(output, list) else [])
            history.append({"type": "function_call_output", "call_id": call_id, "output": json.dumps({f"tool:{name}": tool_result}, ensure_ascii=False)})
        return self._fallback("model_turn_limit_reached", turns=self.max_model_turns, input_tokens=input_tokens, output_tokens=output_tokens, latency_ms=int((time.monotonic() - started) * 1000), transcript=tuple(transcript))


__all__ = ["DeepSeekRecoveryExperiment", "RecoveryEvidenceRegistry", "RecoveryOutcome", "ToolTranscript", "deterministic_recovery", "qloo_focused_executor"]
