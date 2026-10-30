"""Bounded, evidence-only helpers for the Film Programming Brief.

The recommendation engine remains the source of truth for the shortlist.  This
module may ask a model which *permitted* evidence to inspect, but never gives
it authority to add candidates, alter ranks, or state unverified film facts.
"""
from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Mapping, Protocol, Sequence
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class ProviderUnavailable(Exception):
    pass


@dataclass(frozen=True)
class Source:
    title: str
    url: str
    date: str | None = None


@dataclass(frozen=True)
class ToolObservation:
    name: str
    arguments: dict[str, object]
    observation: dict[str, object] | None = None
    status: str = "executed"


@dataclass(frozen=True)
class ProgrammingBrief:
    status: str  # ready, clarification_needed, unavailable
    summary: str
    tradeoffs: tuple[str, ...]
    uncertainty: str
    sources: tuple[Source, ...] = ()
    tools_used: tuple[str, ...] = ()
    input_tokens: int = 0
    output_tokens: int = 0
    estimated_cost_usd: float = 0.0
    latency_ms: int = 0
    agent_activity: str = "deterministic_only"
    evidence_refs: tuple[str, ...] = ()
    tool_observations: tuple[ToolObservation, ...] = ()
    model_turns: int = 0


class HttpOpener(Protocol):
    def __call__(self, request: Request, timeout: float = ...) -> object: ...


def _json_request(url: str, payload: dict[str, object], api_key: str, opener: HttpOpener = urlopen) -> dict[str, object]:
    request = Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with opener(request, timeout=8) as response:  # type: ignore[union-attr]
            decoded = json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, ValueError, TypeError, AttributeError, OSError) as error:
        raise ProviderUnavailable("external programming provider unavailable") from error
    if not isinstance(decoded, dict):
        raise ProviderUnavailable("invalid programming provider response")
    return decoded


def _shortlist_payload(result: object) -> list[dict[str, object]]:
    candidates = getattr(result, "candidates", ())
    return [
        {"id": item.candidate.entity_id, "rank": item.rank, "title": item.candidate.title, "year": item.candidate.release_year,
         "fit": item.fit_explanation, "warning": item.warning_text}
        for item in candidates
    ]


def _needs_current_search(details: str) -> bool:
    words = details.casefold()
    return any(word in words for word in ("recent", "latest", "announcement", "release information", "new release"))


class DeepSeekSearch:
    """The documented raw Search API, deliberately limited to one result set."""
    def __init__(self, api_key: str, opener: HttpOpener = urlopen) -> None:
        self.api_key, self.opener = api_key, opener

    def search(self, query: str) -> tuple[Source, ...]:
        payload = _json_request("https://api.deepseek.com/v1/tools/search", {"query": query[:128], "count": 3, "need_content": False}, self.api_key, self.opener)
        sources: list[Source] = []
        for item in payload.get("results", []):
            if not isinstance(item, dict):
                continue
            url = item.get("url")
            title = item.get("title")
            if isinstance(url, str) and url.startswith(("https://", "http://")) and isinstance(title, str):
                date = item.get("date") or item.get("published_at")
                sources.append(Source(title=title[:160], url=url, date=date[:40] if isinstance(date, str) else None))
        return tuple(sources)


class FilmProgrammingAgent:
    """A staging-only, evidence-grounded two-turn programming brief agent.

    The deterministic recommendation result remains authoritative.  The model
    can request one read-only observation from the verified evidence packet,
    receive that observation in a second turn, and return only the validated
    briefing fields.  This class deliberately does not call the rejected
    recommendation-recovery experiment.
    """
    input_price_per_million = 0.30
    output_price_per_million = 1.20
    max_cost_usd = 0.10
    max_model_turns = 2
    max_input_tokens = 100_000
    max_output_tokens = 1_200
    _tool_names = frozenset({
        "inspect_audience_coverage",
        "inspect_candidate_evidence",
        "inspect_qloo_entity",
    })
    _allowed_media_types = frozenset({"movie", "tv"})

    def __init__(self, api_key: str | None = None, opener: HttpOpener = urlopen) -> None:
        self.api_key = api_key if api_key is not None else os.getenv("DEEPSEEK_API_KEY", "")
        self.opener = opener

    @classmethod
    def _usage(cls, response: Mapping[str, object]) -> tuple[int, int]:
        usage = response.get("usage")
        usage = usage if isinstance(usage, Mapping) else {}
        input_tokens, output_tokens = usage.get("input_tokens", 0), usage.get("output_tokens", 0)
        return (
            input_tokens if isinstance(input_tokens, int) and not isinstance(input_tokens, bool) and input_tokens >= 0 else 0,
            output_tokens if isinstance(output_tokens, int) and not isinstance(output_tokens, bool) and output_tokens >= 0 else 0,
        )

    @classmethod
    def _cost(cls, input_tokens: int, output_tokens: int) -> float:
        return (input_tokens * cls.input_price_per_million + output_tokens * cls.output_price_per_million) / 1_000_000

    @staticmethod
    def _redact_reason(reason: object) -> str | None:
        if not isinstance(reason, str):
            return None
        value = reason.strip()
        if not value:
            return None
        # Reasons are already separated from attendee records by the caller.
        # Remove common direct identifiers if a registrant included one in the
        # free text, while retaining the useful preference explanation.
        value = re.sub(r"https?://\S+|www\.\S+", "[redacted-url]", value, flags=re.IGNORECASE)
        value = re.sub(r"\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b", "[redacted-email]", value)
        value = re.sub(r"\b(?:attendee|guest|participant)\s*(?:id|name)?\s*[:=#-]?\s*[A-Za-z0-9_-]{2,}", "[redacted-person]", value, flags=re.IGNORECASE)
        value = re.sub(r"\b(?:id|name)\s*[:=]\s*[^\s,;]+", "[redacted-person]", value, flags=re.IGNORECASE)
        value = re.sub(r"\b\+?[0-9][0-9(). -]{7,}[0-9]\b", "[redacted-phone]", value)
        value = re.sub(r"\b[0-9a-f]{8}-[0-9a-f-]{27,}\b", "[redacted-id]", value, flags=re.IGNORECASE)
        return value[:300]

    @staticmethod
    def _response_schema() -> dict[str, object]:
        return {
            "type": "json_schema",
            "name": "cinebridge_film_programming_brief",
            "strict": True,
            "schema": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "status": {"type": "string", "enum": ["ready", "clarification_needed"]},
                    "summary": {"type": "string", "maxLength": 900},
                    "tradeoffs": {"type": "array", "items": {"type": "string", "maxLength": 300}, "maxItems": 4},
                    "uncertainty": {"type": "string", "maxLength": 500},
                    "evidence_refs": {"type": "array", "items": {"type": "string", "maxLength": 160}, "minItems": 1, "maxItems": 8},
                },
                "required": ["status", "summary", "tradeoffs", "uncertainty", "evidence_refs"],
            },
        }

    @staticmethod
    def _text(response: Mapping[str, object]) -> str | None:
        direct = response.get("output_text")
        if isinstance(direct, str):
            return direct
        outputs = response.get("output")
        if not isinstance(outputs, list):
            return None
        for item in outputs:
            if not isinstance(item, Mapping) or item.get("type") != "message":
                continue
            content = item.get("content")
            if not isinstance(content, list):
                continue
            for part in content:
                if isinstance(part, Mapping) and part.get("type") in {"output_text", "text"} and isinstance(part.get("text"), str):
                    return part["text"]
        return None

    @staticmethod
    def _function_calls(response: Mapping[str, object]) -> list[dict[str, object]]:
        outputs = response.get("output")
        if not isinstance(outputs, list):
            return []
        return [dict(item) for item in outputs if isinstance(item, Mapping) and item.get("type") == "function_call"]

    @classmethod
    def _brief_from_text(
        cls,
        text: str,
        *,
        evidence_ids: set[str],
        fallback: ProgrammingBrief,
    ) -> ProgrammingBrief | None:
        try:
            payload = json.loads(text)
        except (TypeError, ValueError):
            return None
        if not isinstance(payload, dict):
            return None
        expected_keys = {"status", "summary", "tradeoffs", "uncertainty", "evidence_refs"}
        if set(payload) != expected_keys or payload.get("status") not in {"ready", "clarification_needed"}:
            return None
        summary = payload.get("summary")
        uncertainty = payload.get("uncertainty")
        tradeoffs = payload.get("tradeoffs")
        refs = payload.get("evidence_refs")
        if not isinstance(summary, str) or not summary.strip() or len(summary) > 900:
            return None
        if not isinstance(uncertainty, str) or len(uncertainty) > 500:
            return None
        if not isinstance(tradeoffs, list) or len(tradeoffs) > 4 or not all(isinstance(item, str) and item.strip() and len(item) <= 300 for item in tradeoffs):
            return None
        if not isinstance(refs, list) or not 1 <= len(refs) <= 8 or len(set(refs)) != len(refs) or not all(isinstance(ref, str) and ref in evidence_ids for ref in refs):
            return None
        # The model may discuss verified titles, but it cannot smuggle a new
        # candidate, rank, score, rights claim, or availability assertion into
        # an otherwise valid JSON response.
        if re.search(r"\b(?:rank|score)\s*(?:is|=|:)\s*[0-9]", summary + " " + " ".join(tradeoffs)):
            return None
        if re.search(r"\b(?:screening rights?|availability)\s+(?:are\s+)?(?:confirmed|secured|guaranteed|available)", summary + " " + uncertainty, flags=re.IGNORECASE):
            return None
        if re.search(r"\b(?:will enjoy|guarantee(?:d)? enjoyment|proof of enjoyment|everyone will enjoy)\b", summary + " " + " ".join(tradeoffs), flags=re.IGNORECASE):
            return None
        return ProgrammingBrief(
            str(payload["status"]), summary.strip(), tuple(item.strip() for item in tradeoffs), uncertainty.strip(),
            evidence_refs=tuple(refs),
        )

    @classmethod
    def _fallback(cls, result: object, *, activity: str = "deterministic_only", model_turns: int = 0,
                  input_tokens: int = 0, output_tokens: int = 0, estimated_cost_usd: float = 0.0,
                  latency_ms: int = 0, tools_used: tuple[str, ...] = (),
                  evidence_refs: tuple[str, ...] = (), tool_observations: tuple[ToolObservation, ...] = ()) -> ProgrammingBrief:
        shortlist = _shortlist_payload(result)
        if len(shortlist) != 3:
            return ProgrammingBrief("clarification_needed", "A programming brief needs a complete, provider-backed shortlist.", (), "No brief is generated until three eligible candidates are available.", agent_activity=activity, model_turns=model_turns)
        return ProgrammingBrief(
            "ready", f"{shortlist[0]['title']} is the deterministic top pick; the two alternatives remain available for the organizer to weigh.",
            tuple(f"#{item['rank']} {item['title']}: {item['fit']}" for item in shortlist[1:]),
            "Qloo affinity is a cultural signal, not proof of enjoyment, availability, or screening rights.",
            tools_used=tools_used, input_tokens=input_tokens, output_tokens=output_tokens,
            estimated_cost_usd=estimated_cost_usd, latency_ms=latency_ms, agent_activity=activity,
            evidence_refs=evidence_refs, tool_observations=tool_observations, model_turns=model_turns,
        )

    def create_brief(
        self,
        *,
        result: object,
        event_details: str,
        attendee_reasons: Sequence[str] = (),
        verified_evidence: Mapping[str, object] | None = None,
        tool_executor: Callable[[str, dict[str, object]], dict[str, object]] | None = None,
    ) -> ProgrammingBrief:
        shortlist = _shortlist_payload(result)
        fallback = self._fallback(result)
        if len(shortlist) != 3:
            return fallback
        # DeepSeek remains disabled unless staging explicitly opts in.  The
        # normal recommendation endpoint therefore spends nothing by default.
        if not self.api_key or os.getenv("FILM_AGENT_ENABLED", "false").lower() != "true":
            return fallback
        if verified_evidence is None or tool_executor is None:
            return self._fallback(result, activity="agent_no_action")

        started = time.monotonic()
        packet_refs = verified_evidence.get("evidence_refs", ())
        evidence_ids = set(packet_refs) if isinstance(packet_refs, Sequence) and not isinstance(packet_refs, (str, bytes)) else set()
        if not evidence_ids:
            return self._fallback(result, activity="agent_rejected_output")
        safe_reasons = [
            redacted for reason in attendee_reasons
            if (redacted := self._redact_reason(reason)) is not None
        ][:12]
        context = {
            "shortlist": shortlist,
            "coverage_evidence": verified_evidence.get("coverage", {}),
            "candidate_evidence": verified_evidence.get("candidate_evidence", {}),
            "attendee_reasons": [{"reason_ref": f"reason:{index}", "text": reason} for index, reason in enumerate(safe_reasons, 1)],
            "event_details": event_details[:600],
        }
        tools = [
            {"type": "function", "name": "inspect_audience_coverage", "description": "Read verified aggregate audience coverage. No arguments.", "parameters": {"type": "object", "additionalProperties": False, "properties": {}}},
            {"type": "function", "name": "inspect_candidate_evidence", "description": "Read evidence for one existing deterministic shortlist candidate. It cannot add or rank candidates.", "parameters": {"type": "object", "additionalProperties": False, "properties": {"candidate_id": {"type": "string", "maxLength": 160}, "media_type": {"type": "string", "enum": ["movie", "tv"]}}, "required": ["candidate_id", "media_type"]}},
            {"type": "function", "name": "inspect_qloo_entity", "description": "Read one already-verified Qloo entity and its matching media type.", "parameters": {"type": "object", "additionalProperties": False, "properties": {"entity_id": {"type": "string", "maxLength": 160}, "media_type": {"type": "string", "enum": ["movie", "tv"]}}, "required": ["entity_id", "media_type"]}},
        ]
        instructions = (
            "You are CineBridge's staging Film Programming Agent. The deterministic shortlist, eligibility, and ranks are authoritative. "
            "Use at most one read-only evidence tool, only when useful, then return JSON only with the required schema. "
            "Cite one or more supplied packet or tool evidence_refs. Do not select, remove, add, reorder, rank, score, or change candidates. "
            "Do not claim screening rights, availability, or that an attendee will enjoy a film. Do not repeat attendee identifiers."
        )
        user_context = json.dumps(context, ensure_ascii=False)
        request_base: dict[str, object] = {
            "model": "deepseek-flash",
            "instructions": instructions,
            "input": user_context,
            "tools": tools,
            "text": {"format": self._response_schema()},
            "max_output_tokens": 400,
        }
        input_tokens = output_tokens = 0
        try:
            first = _json_request("https://api.deepseek.com/responses", request_base, self.api_key, self.opener)
        except ProviderUnavailable:
            return self._fallback(result, activity="agent_provider_unavailable", model_turns=1, latency_ms=int((time.monotonic() - started) * 1000))
        first_input, first_output = self._usage(first)
        input_tokens += first_input
        output_tokens += first_output
        if input_tokens > self.max_input_tokens or output_tokens > self.max_output_tokens or self._cost(input_tokens, output_tokens) > self.max_cost_usd:
            return self._fallback(result, activity="agent_limits_exceeded", model_turns=1, input_tokens=input_tokens, output_tokens=output_tokens, estimated_cost_usd=self._cost(input_tokens, output_tokens), latency_ms=int((time.monotonic() - started) * 1000))

        calls = self._function_calls(first)
        if not calls:
            parsed = self._text(first)
            validated = self._brief_from_text(parsed, evidence_ids=evidence_ids, fallback=fallback) if parsed else None
            if validated is None:
                return self._fallback(result, activity="agent_rejected_output", model_turns=1, input_tokens=input_tokens, output_tokens=output_tokens, estimated_cost_usd=self._cost(input_tokens, output_tokens), latency_ms=int((time.monotonic() - started) * 1000))
            return ProgrammingBrief(validated.status, validated.summary, validated.tradeoffs, validated.uncertainty, input_tokens=input_tokens, output_tokens=output_tokens, estimated_cost_usd=self._cost(input_tokens, output_tokens), latency_ms=int((time.monotonic() - started) * 1000), agent_activity="agent_no_action", evidence_refs=validated.evidence_refs, model_turns=1)
        if len(calls) != 1:
            return self._fallback(result, activity="agent_rejected_output", model_turns=1, input_tokens=input_tokens, output_tokens=output_tokens, estimated_cost_usd=self._cost(input_tokens, output_tokens), latency_ms=int((time.monotonic() - started) * 1000))

        call = calls[0]
        name, call_id, raw_arguments = call.get("name"), call.get("call_id"), call.get("arguments")
        if not isinstance(name, str) or name not in self._tool_names or not isinstance(call_id, str) or not 1 <= len(call_id) <= 128 or not call_id.strip() or not isinstance(raw_arguments, str) or len(raw_arguments) > 2_000:
            return self._fallback(result, activity="agent_rejected_output", model_turns=1, input_tokens=input_tokens, output_tokens=output_tokens, estimated_cost_usd=self._cost(input_tokens, output_tokens), latency_ms=int((time.monotonic() - started) * 1000))
        try:
            arguments = json.loads(raw_arguments)
        except (TypeError, ValueError):
            arguments = None
        valid_arguments = self._valid_tool_arguments(name, arguments, verified_evidence, shortlist)
        if valid_arguments is None:
            rejected = ToolObservation(name=name, arguments={}, observation={"reason": "invalid_arguments"}, status="rejected")
            return self._fallback(result, activity="agent_rejected_output", model_turns=1, input_tokens=input_tokens, output_tokens=output_tokens, estimated_cost_usd=self._cost(input_tokens, output_tokens), latency_ms=int((time.monotonic() - started) * 1000), tool_observations=(rejected,))
        try:
            observation = tool_executor(name, arguments)
        except (KeyError, TypeError, ValueError, ProviderUnavailable):
            observation = None
        if not isinstance(observation, dict):
            rejected = ToolObservation(name=name, arguments=arguments, observation={"reason": "tool_unavailable"}, status="rejected")
            return self._fallback(result, activity="agent_provider_unavailable", model_turns=1, input_tokens=input_tokens, output_tokens=output_tokens, estimated_cost_usd=self._cost(input_tokens, output_tokens), latency_ms=int((time.monotonic() - started) * 1000), tool_observations=(rejected,))
        executed = ToolObservation(name=name, arguments=arguments, observation=observation)
        tool_ref = f"tool:{name}"
        function_call_output: dict[str, object] = {
            "type": "function_call_output",
            "call_id": call_id,
            "output": json.dumps({"evidence_ref": tool_ref, "observation": observation}, ensure_ascii=False),
        }
        second_input: list[dict[str, object]] = [
            {"role": "user", "content": user_context},
            call,
            function_call_output,
        ]
        second_request: dict[str, object] = {
            "model": "deepseek-flash",
            "instructions": instructions,
            "input": second_input,
            "text": {"format": self._response_schema()},
            "max_output_tokens": 400,
        }
        try:
            second = _json_request("https://api.deepseek.com/responses", second_request, self.api_key, self.opener)
        except ProviderUnavailable:
            return self._fallback(result, activity="agent_provider_unavailable", model_turns=2, input_tokens=input_tokens, output_tokens=output_tokens, estimated_cost_usd=self._cost(input_tokens, output_tokens), latency_ms=int((time.monotonic() - started) * 1000), tools_used=(name,), evidence_refs=(tool_ref,), tool_observations=(executed,))
        second_input_tokens, second_output_tokens = self._usage(second)
        input_tokens += second_input_tokens
        output_tokens += second_output_tokens
        total_cost = self._cost(input_tokens, output_tokens)
        observations = (executed,)
        if input_tokens > self.max_input_tokens or output_tokens > self.max_output_tokens or total_cost > self.max_cost_usd:
            return self._fallback(result, activity="agent_limits_exceeded", model_turns=2, input_tokens=input_tokens, output_tokens=output_tokens, estimated_cost_usd=total_cost, latency_ms=int((time.monotonic() - started) * 1000), tools_used=(name,), evidence_refs=(tool_ref,), tool_observations=observations)
        if self._function_calls(second):
            return self._fallback(result, activity="agent_rejected_output", model_turns=2, input_tokens=input_tokens, output_tokens=output_tokens, estimated_cost_usd=total_cost, latency_ms=int((time.monotonic() - started) * 1000), tools_used=(name,), evidence_refs=(tool_ref,), tool_observations=observations)
        parsed = self._text(second)
        validated = self._brief_from_text(parsed, evidence_ids=evidence_ids | {tool_ref}, fallback=fallback) if parsed else None
        if validated is None:
            return self._fallback(result, activity="agent_rejected_output", model_turns=2, input_tokens=input_tokens, output_tokens=output_tokens, estimated_cost_usd=total_cost, latency_ms=int((time.monotonic() - started) * 1000), tools_used=(name,), evidence_refs=(tool_ref,), tool_observations=observations)
        return ProgrammingBrief(validated.status, validated.summary, validated.tradeoffs, validated.uncertainty, input_tokens=input_tokens, output_tokens=output_tokens, estimated_cost_usd=total_cost, latency_ms=int((time.monotonic() - started) * 1000), agent_activity="agent_tool_loop", evidence_refs=validated.evidence_refs, tools_used=(name,), tool_observations=observations, model_turns=2)

    @classmethod
    def _valid_tool_arguments(cls, name: str, arguments: object, evidence: Mapping[str, object], shortlist: list[dict[str, object]]) -> dict[str, object] | None:
        if not isinstance(arguments, dict):
            return None
        candidate_evidence = evidence.get("candidate_evidence")
        candidate_evidence = candidate_evidence if isinstance(candidate_evidence, Mapping) else {}
        qloo_entities = evidence.get("qloo_entities")
        qloo_entities = qloo_entities if isinstance(qloo_entities, Mapping) else {}
        if name == "inspect_audience_coverage":
            return arguments if not arguments else None
        if name == "inspect_candidate_evidence":
            if set(arguments) != {"candidate_id", "media_type"}:
                return None
            candidate_id, media_type = arguments.get("candidate_id"), arguments.get("media_type")
            if not isinstance(candidate_id, str) or not 1 <= len(candidate_id) <= 160 or not isinstance(media_type, str) or media_type not in cls._allowed_media_types:
                return None
            item = candidate_evidence.get(candidate_id)
            return arguments if isinstance(item, Mapping) and item.get("media_type") == media_type and any(str(candidate.get("id")) == candidate_id for candidate in shortlist) else None
        if name == "inspect_qloo_entity":
            if set(arguments) != {"entity_id", "media_type"}:
                return None
            entity_id, media_type = arguments.get("entity_id"), arguments.get("media_type")
            if not isinstance(entity_id, str) or not 1 <= len(entity_id) <= 160 or not isinstance(media_type, str) or media_type not in cls._allowed_media_types:
                return None
            item = qloo_entities.get(entity_id)
            return arguments if isinstance(item, Mapping) and item.get("media_type") == media_type else None
        return None


ExperimentalToolExecutor = Callable[[str, dict[str, object]], dict[str, object]]


class BoundedDeepSeekExperiment:
    """An opt-in, fixture-friendly two-turn experiment for approach C.

    This is deliberately not wired into recommendation generation.  The
    deterministic result is supplied to the model as read-only evidence and
    remains the only source of candidate ranks.  A caller supplies the
    permitted evidence executor, making it possible to test the loop without
    either DeepSeek or Qloo credentials.
    """

    input_price_per_million = FilmProgrammingAgent.input_price_per_million
    output_price_per_million = FilmProgrammingAgent.output_price_per_million
    max_cost_usd = 0.15
    _tool_names = frozenset({"inspect_qloo_tags", "inspect_movie_metadata", "investigate_qloo"})

    def __init__(self, api_key: str, opener: HttpOpener = urlopen, *, max_cost_usd: float = max_cost_usd) -> None:
        self.api_key, self.opener = api_key, opener
        self.max_cost_usd = max(0.0, min(max_cost_usd, self.max_cost_usd))

    @classmethod
    def _usage(cls, response: dict[str, object]) -> tuple[int, int]:
        usage = response.get("usage")
        usage = usage if isinstance(usage, dict) else {}
        input_tokens, output_tokens = usage.get("input_tokens", 0), usage.get("output_tokens", 0)
        return (
            input_tokens if isinstance(input_tokens, int) and not isinstance(input_tokens, bool) and input_tokens >= 0 else 0,
            output_tokens if isinstance(output_tokens, int) and not isinstance(output_tokens, bool) and output_tokens >= 0 else 0,
        )

    @classmethod
    def _cost(cls, input_tokens: int, output_tokens: int) -> float:
        return (input_tokens * cls.input_price_per_million + output_tokens * cls.output_price_per_million) / 1_000_000

    @staticmethod
    def _fallback(result: object) -> ProgrammingBrief:
        shortlist = _shortlist_payload(result)
        return ProgrammingBrief(
            "ready",
            f"{shortlist[0]['title']} is the deterministic top pick; the two alternatives remain available for the organizer to weigh.",
            tuple(f"#{item['rank']} {item['title']}: {item['fit']}" for item in shortlist[1:]),
            "Qloo affinity is a cultural signal, not proof of enjoyment, availability, or screening rights.",
        )

    @staticmethod
    def _text(response: dict[str, object]) -> str | None:
        direct = response.get("output_text")
        if isinstance(direct, str):
            return direct
        outputs = response.get("output")
        if not isinstance(outputs, list):
            return None
        for item in outputs:
            if not isinstance(item, dict) or item.get("type") != "message":
                continue
            content = item.get("content")
            if not isinstance(content, list):
                continue
            for part in content:
                if isinstance(part, dict) and part.get("type") in {"output_text", "text"} and isinstance(part.get("text"), str):
                    return part["text"]
        return None

    @staticmethod
    def _function_call(response: dict[str, object]) -> dict[str, object] | None:
        outputs = response.get("output")
        if not isinstance(outputs, list):
            return None
        calls = [item for item in outputs if isinstance(item, dict) and item.get("type") == "function_call"]
        # One investigation is the hard experimental bound, including malformed
        # attempts to request more than one call.
        return calls[0] if len(calls) == 1 else None

    @staticmethod
    def _validated_brief(text: str, fallback: ProgrammingBrief, evidence_ids: set[str]) -> ProgrammingBrief | None:
        try:
            payload = json.loads(text)
        except (TypeError, ValueError):
            return None
        if not isinstance(payload, dict) or payload.get("status") not in {"ready", "clarification_needed", "abstain"}:
            return None
        summary, uncertainty, tradeoffs, refs = payload.get("summary"), payload.get("uncertainty"), payload.get("tradeoffs"), payload.get("evidence_refs", [])
        if not isinstance(summary, str) or not summary.strip() or len(summary) > 900:
            return None
        if not isinstance(uncertainty, str) or len(uncertainty) > 500:
            return None
        if not isinstance(tradeoffs, list) or not all(isinstance(item, str) and item.strip() and len(item) <= 300 for item in tradeoffs[:4]):
            return None
        if not isinstance(refs, list) or not all(isinstance(ref, str) and ref in evidence_ids for ref in refs):
            return None
        # The model is advisory: it may describe evidence, but cannot nominate a
        # different candidate or transmit a rank.  Those fields are rejected.
        if any(key in payload for key in ("recommended_title", "candidate", "rank", "score")):
            return None
        return ProgrammingBrief(str(payload["status"]), summary.strip(), tuple(tradeoffs[:4]), uncertainty.strip(), agent_activity="experimental_tool_loop")

    def run(
        self,
        *,
        result: object,
        attendee_reasons: list[str],
        verified_evidence: dict[str, object],
        tool_executor: ExperimentalToolExecutor,
    ) -> ProgrammingBrief:
        """Run at most two model turns and one validated evidence lookup.

        ``verified_evidence`` must only contain backend-verified Qloo/TMDB data.
        The executor is called only after its tool name and arguments pass the
        allow-list checks below.  It is never given authority over candidates.
        """
        shortlist = _shortlist_payload(result)
        if len(shortlist) != 3 or not self.api_key:
            return self._fallback(result)
        fallback = self._fallback(result)
        started = time.monotonic()
        allowed_ids = {str(item.get("id")) for item in shortlist if item.get("id") is not None}
        context = {"shortlist": shortlist, "attendee_reasons": attendee_reasons[:12], "verified_evidence": verified_evidence}
        tools = [
            {"type": "function", "name": "inspect_qloo_tags", "description": "Inspect tags for an already-resolved Qloo entity.", "parameters": {"type": "object", "properties": {"entity_id": {"type": "string"}}, "required": ["entity_id"]}},
            {"type": "function", "name": "inspect_movie_metadata", "description": "Inspect verified metadata for an existing shortlist candidate.", "parameters": {"type": "object", "properties": {"candidate_id": {"type": "string"}}, "required": ["candidate_id"]}},
            {"type": "function", "name": "investigate_qloo", "description": "One focused Qloo investigation for a resolved entity; it cannot request candidates or change ranks.", "parameters": {"type": "object", "properties": {"entity_id": {"type": "string"}, "question": {"type": "string", "maxLength": 128}}, "required": ["entity_id", "question"]}},
        ]
        instructions = (
            "You are an experiment-only evidence analyst. The deterministic shortlist is authoritative. "
            "You may call exactly one permitted tool, then return JSON only with status, summary, tradeoffs, uncertainty, and evidence_refs. "
            "Do not recommend a title, rank candidates, invent facts, or claim availability/rights. Abstain when evidence is insufficient."
        )
        try:
            first = _json_request("https://api.deepseek.com/responses", {"model": "deepseek-flash", "instructions": instructions, "input": json.dumps(context, ensure_ascii=False), "tools": tools, "max_output_tokens": 350}, self.api_key, self.opener)
        except ProviderUnavailable:
            return fallback
        input_tokens, output_tokens = self._usage(first)
        total_cost = self._cost(input_tokens, output_tokens)
        if total_cost > self.max_cost_usd:
            return fallback
        call = self._function_call(first)
        if call is None:
            parsed = self._text(first)
            validated = self._validated_brief(parsed, fallback, set(verified_evidence)) if parsed else None
            return validated or fallback
        name, call_id, raw_arguments = call.get("name"), call.get("call_id"), call.get("arguments", "{}")
        if not isinstance(name, str) or name not in self._tool_names or not isinstance(call_id, str) or not isinstance(raw_arguments, str):
            return fallback
        try:
            args = json.loads(raw_arguments)
        except ValueError:
            return fallback
        if not isinstance(args, dict):
            return fallback
        entity_id = args.get("entity_id")
        candidate_id = args.get("candidate_id")
        valid = (
            (name == "inspect_qloo_tags" and isinstance(entity_id, str) and entity_id in set(map(str, verified_evidence.get("qloo_entity_ids", []))))
            or (name == "inspect_movie_metadata" and isinstance(candidate_id, str) and candidate_id in allowed_ids)
            or (name == "investigate_qloo" and isinstance(entity_id, str) and entity_id in set(map(str, verified_evidence.get("qloo_entity_ids", []))) and isinstance(args.get("question"), str) and 0 < len(args["question"].strip()) <= 128)
        )
        if not valid:
            return fallback
        try:
            tool_result = tool_executor(name, args)
        except (TypeError, ValueError, KeyError, ProviderUnavailable):
            return fallback
        if not isinstance(tool_result, dict):
            return fallback
        evidence_key = f"tool:{name}"
        try:
            second = _json_request("https://api.deepseek.com/responses", {"model": "deepseek-flash", "instructions": instructions, "input": [{"type": "function_call_output", "call_id": call_id, "output": json.dumps({evidence_key: tool_result}, ensure_ascii=False)}], "max_output_tokens": 350}, self.api_key, self.opener)
        except ProviderUnavailable:
            return fallback
        second_input, second_output = self._usage(second)
        input_tokens += second_input
        output_tokens += second_output
        total_cost = self._cost(input_tokens, output_tokens)
        if total_cost > self.max_cost_usd:
            return fallback
        parsed = self._text(second)
        evidence_ids = set(verified_evidence) | {evidence_key}
        validated = self._validated_brief(parsed, fallback, evidence_ids) if parsed else None
        if not validated:
            return fallback
        return ProgrammingBrief(validated.status, validated.summary, validated.tradeoffs, validated.uncertainty, tools_used=(name,), input_tokens=input_tokens, output_tokens=output_tokens, estimated_cost_usd=total_cost, latency_ms=int((time.monotonic() - started) * 1000), agent_activity="experimental_tool_loop")


__all__ = ["BoundedDeepSeekExperiment", "DeepSeekSearch", "FilmProgrammingAgent", "ProgrammingBrief", "ProviderUnavailable", "Source", "ToolObservation"]
