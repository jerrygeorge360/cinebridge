#!/usr/bin/env python3
"""Run the staging-only recovery sample under one aggregate $0.10 ledger."""
from __future__ import annotations

import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from urllib.request import urlopen

CINEBRIDGE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(CINEBRIDGE / "api"))

from app.programming import ProviderUnavailable
from app.recovery_experiment import (
    DeepSeekRecoveryExperiment,
    RecoveryEvidenceRegistry,
    _cost,
)


FIXTURES = CINEBRIDGE / "api" / "tests" / "fixtures" / "deepseek_value_experiment_v1.json"
LEDGER = CINEBRIDGE / "docs" / "AGENTIC_RECOVERY_LIVE_LEDGER.json"
REPORT = CINEBRIDGE / "docs" / "AGENTIC_RECOVERY_LIVE_RESULTS.md"
CAP = 0.10
# Peak cache-miss Flash reservation: 4,000 input + 400 output tokens.
RESERVATION = _cost(4000, 400)


class BudgetedOpener:
    def __init__(self, initial_reserved: float = 0.0) -> None:
        self.reserved = initial_reserved
        self.calls = 0
        self.responses: list[object] = []

    def __call__(self, request, timeout=8):
        if self.reserved + RESERVATION > CAP:
            raise ProviderUnavailable("aggregate experiment cap reached")
        self.reserved += RESERVATION
        self.calls += 1
        return _CapturedResponse(urlopen(request, timeout=timeout), self.responses)


class _CapturedResponse:
    def __init__(self, raw, recorded: list[object]) -> None:
        self.raw, self.recorded = raw, recorded

    def __enter__(self):
        self.raw.__enter__()
        return self

    def __exit__(self, *args):
        return self.raw.__exit__(*args)

    def read(self):
        value = self.raw.read()
        try:
            self.recorded.append(json.loads(value.decode("utf-8")))
        except (UnicodeDecodeError, json.JSONDecodeError):
            self.recorded.append({"unparseable_provider_response": True})
        return value


def _packet(scenario: dict[str, object]) -> dict[str, object]:
    packet = dict(scenario)
    if packet["id"] == "code-geass-politics-v1":
        packet.update({
            "qloo_themes": {"fixture-code-geass-tv": ["political conflict", "strategy", "moral dilemma"]},
            "candidate_evidence": {
                "Fixture KonoSuba": {"year": 2019, "media_type": "movie"},
                "Fixture DanMachi": {"year": 2019, "media_type": "movie"},
                "Fixture Demon Slayer": {"year": 2020, "media_type": "movie"},
            },
            "focused_query_results": {
                "fixture-code-geass-tv|strategy": {"candidate_titles": ["Fixture KonoSuba"], "evidence": "Frozen registered evidence only."}
            },
            "recovery_trigger": "Candidate-level thematic evidence is unavailable in the deterministic result, but registered evidence exists for every current candidate. Inspect one existing candidate with inspect_movie_evidence before deciding whether the shortlist is defensible.",
        })
    elif packet["id"] == "weak-coverage-v1":
        packet["recovery_trigger"] = "Coverage is below threshold and one preference is unresolved; inspect audience coverage before deciding whether to abstain."
    return packet


def main() -> int:
    key = os.getenv("DEEPSEEK_API_KEY", "").strip()
    if not key:
        print("DEEPSEEK_API_KEY is absent; no live request was made.", file=sys.stderr)
        return 2
    fixtures = json.loads(FIXTURES.read_text())
    selected = [scenario for scenario in fixtures["scenarios"] if scenario["id"] in {"anime-reasons-v1", "code-geass-politics-v1", "weak-coverage-v1"}]
    previous = json.loads(LEDGER.read_text()) if LEDGER.exists() else {}
    previous_reserved = float(previous.get("reserved_usd", 0.0))
    previous_cost = float(previous.get("actual_estimated_cost_usd", 0.0))
    previous_calls = int(previous.get("provider_calls", 0))
    opener = BudgetedOpener(previous_reserved)
    records = list(previous.get("records", [])) if isinstance(previous.get("records"), list) else []
    for scenario in selected:
        packet = _packet(scenario)
        response_start = len(opener.responses)
        outcome = DeepSeekRecoveryExperiment(key, opener, max_cost_usd=0.10).run(
            organizer_objective=f"Assess whether the existing shortlist needs evidence recovery for {scenario['id']}.",
            attendee_reasons=list(scenario.get("attendee_reasons", [])),
            registry=RecoveryEvidenceRegistry(packet),
        )
        records.append({
            "scenario": scenario["id"],
            "decision": outcome.decision,
            "observation": outcome.observation,
            "uncertainty": outcome.uncertainty,
            "evidence_refs": list(outcome.evidence_refs),
            "stopping_reason": outcome.stopping_reason,
            "model_turns": outcome.model_turns,
            "input_tokens": outcome.input_tokens,
            "output_tokens": outcome.output_tokens,
            "estimated_cost_usd": outcome.estimated_cost_usd,
            "latency_ms": outcome.latency_ms,
            "tool_calls": [{"name": item.name, "arguments": item.arguments, "result": item.result} for item in outcome.tool_transcript],
            "raw_provider_responses": opener.responses[response_start:],
        })
    estimated = previous_cost + sum(float(record["estimated_cost_usd"]) for record in records[len(previous.get("records", [])):])
    payload = {
        "experiment": "cinebridge-agentic-recovery-v1",
        "executed_at": datetime.now(UTC).isoformat(),
        "aggregate_cap_usd": CAP,
        "reserved_usd": opener.reserved,
        "actual_estimated_cost_usd": estimated,
        "model": "deepseek-flash",
        "price_basis": "DeepSeek Flash peak cache-miss: input $0.30/M, output $1.20/M; estimate only.",
        "provider_calls": previous_calls + opener.calls,
        "records": records,
    }
    LEDGER.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
    tool_calls = sum(len(record["tool_calls"]) for record in records)
    REPORT.write_text(
        "# Agentic recovery experiment — live sample\n\n"
        f"Executed: {payload['executed_at']}\n\n"
        f"Three frozen scenarios were evaluated under one ${CAP:.2f} aggregate cap. "
        f"Provider attempts: {payload['provider_calls']}; reserved maximum: ${opener.reserved:.6f}; "
        f"actual token-based estimated cost: ${estimated:.6f}; tool calls: {tool_calls}. "
        "Costs are estimates, not a billing export.\n\n"
        "The detailed, redacted ledger records every accepted observation, decision, tool argument/result, stop reason, usage, and latency: "
        "`docs/AGENTIC_RECOVERY_LIVE_LEDGER.json`. This staging sample does not enable production behavior or change rankings.\n"
    )
    print(json.dumps({"provider_calls": opener.calls, "tool_calls": tool_calls, "reserved_usd": opener.reserved, "actual_estimated_cost_usd": estimated}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
