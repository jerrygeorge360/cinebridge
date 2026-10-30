#!/usr/bin/env python3
"""Run the bounded, staging-only DeepSeek value comparison.

This is intentionally an experiment runner, not an application integration.
It uses two redacted frozen packets and records a shared, conservative budget
ledger before every request.  It never calls Qloo or alters CineBridge data.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


CINEBRIDGE_ROOT = Path(__file__).resolve().parents[2]
API_ROOT = CINEBRIDGE_ROOT / "api"
FIXTURES = API_ROOT / "tests" / "fixtures" / "deepseek_value_experiment_v1.json"
RESPONSES = CINEBRIDGE_ROOT / "docs" / "DEEPSEEK_VALUE_EXPERIMENT_LIVE_RESPONSES.json"
REPORT = CINEBRIDGE_ROOT / "docs" / "DEEPSEEK_VALUE_EXPERIMENT_LIVE_RESULTS.md"
API_URL = "https://api.deepseek.com/responses"
MODEL = "deepseek-flash"
AGGREGATE_CAP_USD = 0.15
# Peak cache-miss Flash pricing from DeepSeek's official pricing page checked
# 2026-10-27: input $0.30/M; output $1.20/M.  Reservation is deliberately
# higher than this runner's prompt and completion limits.
INPUT_PRICE_PER_MILLION = 0.30
OUTPUT_PRICE_PER_MILLION = 1.20
MAX_INPUT_TOKENS_RESERVED = 4000
MAX_OUTPUT_TOKENS = 250
RESERVATION_USD = (
    MAX_INPUT_TOKENS_RESERVED * INPUT_PRICE_PER_MILLION
    + MAX_OUTPUT_TOKENS * OUTPUT_PRICE_PER_MILLION
) / 1_000_000
SCENARIO_IDS = ("code-geass-politics-v1", "weak-coverage-v1")


def _extract_text(response: dict[str, object]) -> str | None:
    direct = response.get("output_text")
    if isinstance(direct, str):
        return direct
    for item in response.get("output", []):
        if not isinstance(item, dict) or item.get("type") != "message":
            continue
        for part in item.get("content", []):
            if isinstance(part, dict) and part.get("type") in {"output_text", "text"} and isinstance(part.get("text"), str):
                return part["text"]
    return None


def _function_call(response: dict[str, object]) -> dict[str, object] | None:
    calls = [item for item in response.get("output", []) if isinstance(item, dict) and item.get("type") == "function_call"]
    return calls[0] if len(calls) == 1 else None


def _usage(response: dict[str, object]) -> tuple[int, int]:
    usage = response.get("usage")
    usage = usage if isinstance(usage, dict) else {}
    values = (usage.get("input_tokens", 0), usage.get("output_tokens", 0))
    return tuple(value if isinstance(value, int) and value >= 0 else 0 for value in values)  # type: ignore[return-value]


def _cost(input_tokens: int, output_tokens: int) -> float:
    return (input_tokens * INPUT_PRICE_PER_MILLION + output_tokens * OUTPUT_PRICE_PER_MILLION) / 1_000_000


def _post(api_key: str, payload: dict[str, object]) -> tuple[dict[str, object] | None, int, str | None]:
    request = Request(API_URL, data=json.dumps(payload).encode(), headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}, method="POST")
    started = time.monotonic()
    try:
        with urlopen(request, timeout=45) as raw:
            parsed = json.loads(raw.read().decode())
        return (parsed if isinstance(parsed, dict) else None), int((time.monotonic() - started) * 1000), None
    except (HTTPError, URLError, TimeoutError, ValueError) as error:
        return None, int((time.monotonic() - started) * 1000), f"{type(error).__name__}: {str(error)[:240]}"


def _prompt(condition: str, packet: dict[str, object]) -> str:
    return (
        "You are evaluating a film-club programming brief using only this redacted, frozen evidence packet. "
        "The deterministic shortlist is authoritative: do not select, rank, score, reorder, or name a candidate. "
        "Do not invent film facts, availability, rights, tags, release dates, or attendee preferences. "
        "Return only JSON with outcome (brief, clarification_needed, or abstain), summary (<=600 chars), "
        "tradeoffs (array of <=4 strings, each <=240 chars), uncertainty (<=320 chars), evidence_refs (use packet:scenario), "
        "and tool_rationale (string or null). "
        "For weak coverage, abstain or ask for clarification rather than express confidence. "
        f"Condition: {condition}.\nFrozen evidence packet:\n{json.dumps(packet, ensure_ascii=False, separators=(',', ':'))}"
    )


def _validate(text: str | None, packet: dict[str, object], *, tool_used: str | None) -> tuple[bool, str]:
    if not text:
        return False, "missing textual response"
    try:
        body = json.loads(text)
    except ValueError:
        return False, "response was not JSON"
    if not isinstance(body, dict) or body.get("outcome") not in {"brief", "clarification_needed", "abstain"}:
        return False, "invalid outcome"
    if not isinstance(body.get("summary"), str) or not body["summary"].strip() or len(body["summary"]) > 600:
        return False, "invalid summary"
    if not isinstance(body.get("uncertainty"), str) or len(body["uncertainty"]) > 320:
        return False, "invalid uncertainty"
    if not isinstance(body.get("tradeoffs"), list) or len(body["tradeoffs"]) > 4 or not all(isinstance(item, str) and item.strip() and len(item) <= 240 for item in body["tradeoffs"]):
        return False, "invalid tradeoffs"
    refs = body.get("evidence_refs")
    allowed_refs = {"packet:scenario"}
    if tool_used:
        allowed_refs.add(f"tool:{tool_used}")
    if not isinstance(refs, list) or not refs or not all(isinstance(ref, str) and ref in allowed_refs for ref in refs):
        return False, "invalid evidence references"
    if body.get("tool_rationale") is not None and not isinstance(body.get("tool_rationale"), str):
        return False, "invalid tool rationale"
    prose = " ".join([body["summary"], body["uncertainty"], *body["tradeoffs"]]).casefold()
    if any(str(title).casefold() in prose for title in packet["shortlist"]):
        return False, "candidate title mentioned in advisory prose"
    if re.search(r"\b(?:#\s*[123]|first|second|third|top pick|best choice|score)\b", prose):
        return False, "ranking or score language in advisory prose"
    if packet["id"] == "weak-coverage-v1" and body["outcome"] == "brief":
        return False, "weak coverage accepted an unqualified brief"
    return True, "passed structural and rank-integrity checks"


def _tool_result(name: str, arguments: object, packet: dict[str, object]) -> tuple[dict[str, object] | None, str | None]:
    if not isinstance(arguments, str):
        return None, "tool arguments were not text"
    try:
        args = json.loads(arguments)
    except ValueError:
        return None, "tool arguments were not JSON"
    if not isinstance(args, dict) or name not in {"inspect_qloo_tags", "inspect_movie_metadata", "investigate_qloo"}:
        return None, "tool is not permitted"
    # The frozen packet is the complete tool source: this experiment makes no
    # live Qloo call and cannot discover candidates.
    return {"packet:scenario": packet["id"], "registered_evidence": {"qloo_tags": packet.get("qloo_tags", []), "mappings": packet.get("mappings", [])}}, None


def main() -> int:
    api_key = os.getenv("DEEPSEEK_API_KEY", "").strip()
    if not api_key:
        print("DEEPSEEK_API_KEY is absent; no live request was made.", file=sys.stderr)
        return 2
    fixture = json.loads(FIXTURES.read_text())
    scenarios = [item for item in fixture["scenarios"] if item["id"] in SCENARIO_IDS]
    records: list[dict[str, object]] = []
    reserved = actual_cost = 0.0
    stop_reason = "completed"
    tools = [{"type": "function", "name": "inspect_qloo_tags", "description": "Read only registered Qloo tags from this frozen packet.", "parameters": {"type": "object", "properties": {"entity_id": {"type": "string"}}, "required": ["entity_id"]}}, {"type": "function", "name": "inspect_movie_metadata", "description": "Read only registered metadata from this frozen packet.", "parameters": {"type": "object", "properties": {"candidate_id": {"type": "string"}}, "required": ["candidate_id"]}}, {"type": "function", "name": "investigate_qloo", "description": "Read only registered mapping evidence; cannot search or discover candidates.", "parameters": {"type": "object", "properties": {"entity_id": {"type": "string"}, "question": {"type": "string"}}, "required": ["entity_id", "question"]}}]
    for packet in scenarios:
        for condition in ("B", "C"):
            if reserved + RESERVATION_USD > AGGREGATE_CAP_USD:
                stop_reason = "aggregate cap reservation reached"
                break
            payload: dict[str, object] = {"model": MODEL, "instructions": "Return JSON only. Do not reveal reasoning.", "input": _prompt(condition, packet), "max_output_tokens": MAX_OUTPUT_TOKENS, "reasoning": {"effort": "none"}, "text": {"format": {"type": "json_object"}}}
            if condition == "C":
                payload["tools"] = tools
            reserved += RESERVATION_USD
            response, latency_ms, error = _post(api_key, payload)
            record: dict[str, object] = {"timestamp": datetime.now(UTC).isoformat(), "scenario": packet["id"], "version": packet["version"], "packet_sha256": hashlib.sha256(json.dumps(packet, sort_keys=True, separators=(",", ":")).encode()).hexdigest(), "condition": condition, "model": MODEL, "reservation_usd": RESERVATION_USD, "latency_ms": latency_ms, "tool_calls": [], "stop_reason": "provider_failure" if error else "completed"}
            if error or response is None:
                record.update({"validation": "not_run", "error": error})
                records.append(record)
                continue
            input_tokens, output_tokens = _usage(response)
            actual_cost += _cost(input_tokens, output_tokens)
            call = _function_call(response) if condition == "C" else None
            if call:
                name = call.get("name")
                tool_data, tool_error = _tool_result(str(name), call.get("arguments"), packet)
                record["tool_calls"] = [{"name": name, "arguments": call.get("arguments"), "result_sha256": hashlib.sha256(json.dumps(tool_data, sort_keys=True).encode()).hexdigest() if tool_data else None, "error": tool_error}]
                if tool_error or reserved + RESERVATION_USD > AGGREGATE_CAP_USD:
                    record.update({"validation": "failed", "error": tool_error or "aggregate cap reservation reached before second turn", "response": response})
                    records.append(record)
                    continue
                reserved += RESERVATION_USD
                history = [{"role": "user", "content": _prompt(condition, packet)}, *response.get("output", []), {"type": "function_call_output", "call_id": call.get("call_id"), "output": json.dumps(tool_data, ensure_ascii=False)}]
                followup = {"model": MODEL, "instructions": "Return JSON only. Do not reveal reasoning.", "input": history, "max_output_tokens": MAX_OUTPUT_TOKENS, "reasoning": {"effort": "none"}, "text": {"format": {"type": "json_object"}}}
                response, followup_latency, error = _post(api_key, followup)
                latency_ms += followup_latency
                record["latency_ms"] = latency_ms
                if error or response is None:
                    record.update({"validation": "not_run", "error": error, "stop_reason": "provider_failure"})
                    records.append(record)
                    continue
                next_input, next_output = _usage(response)
                input_tokens += next_input
                output_tokens += next_output
                actual_cost += _cost(next_input, next_output)
            text = _extract_text(response)
            valid, note = _validate(text, packet, tool_used=str(call.get("name")) if call else None)
            record.update({"input_tokens": input_tokens, "output_tokens": output_tokens, "estimated_cost_usd": _cost(input_tokens, output_tokens), "validation": "passed" if valid else "failed", "validation_note": note, "response": text})
            records.append(record)
        if stop_reason != "completed":
            break
    data = {"experiment": fixture["experiment"], "executed_at": datetime.now(UTC).isoformat(), "aggregate_cap_usd": AGGREGATE_CAP_USD, "price_basis": "DeepSeek Flash peak cache-miss: input $0.30/M, output $1.20/M (official pricing checked 2026-10-27)", "reservation_usd": reserved, "actual_estimated_cost_usd": actual_cost, "stop_reason": stop_reason, "records": records}
    RESPONSES.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    passed = sum(item.get("validation") == "passed" for item in records)
    REPORT.write_text("# DeepSeek value experiment — live B/C sample\n\n"
        f"Executed: {data['executed_at']}\n\n"
        f"Two frozen scenarios were sampled: {', '.join(SCENARIO_IDS)}. The aggregate spending cap was ${AGGREGATE_CAP_USD:.2f}; conservative reserved maximum was ${reserved:.6f}; actual token-based estimated spend was ${actual_cost:.6f}. Costs are estimates; no billing export was used.\n\n"
        f"Valid outputs: {passed}/{len(records)}. Stop reason: {stop_reason}. Full redacted response and tool transcript ledger: `docs/{RESPONSES.name}`.\n\n"
        "This live sample does not establish organizer usefulness: no independent organizer scores have been collected. It does not change production behavior, ranking, UI, or release approval.\n")
    print(json.dumps({"records": len(records), "passed": passed, "reserved_usd": reserved, "actual_estimated_cost_usd": actual_cost, "stop_reason": stop_reason}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
