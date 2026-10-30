#!/usr/bin/env python3
"""One preregistered, staging-only Code Geass recovery comparison.

This is intentionally a separate ledger from the earlier exploratory sample.
It makes one model-directed recovery attempt and one fixed-rule C0 comparison;
neither can change application data, candidates, ranks, or production behavior.
"""
from __future__ import annotations

import json
import os
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from urllib.request import urlopen

CINEBRIDGE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(CINEBRIDGE / "api"))

from app.programming import ProviderUnavailable
from app.recommendations import QlooHttpAdapter
from app.recovery_experiment import (
    DeepSeekRecoveryExperiment,
    RecoveryEvidenceRegistry,
    _cost,
    qloo_focused_executor,
)


LEDGER = CINEBRIDGE / "docs" / "AGENTIC_RECOVERY_FINAL_LIVE_LEDGER.json"
CAP = 0.02
# Conservative upper bound per DeepSeek Response call: 4,000 input + 400 output.
RESERVATION = _cost(4000, 400)
ENTITY_ID = "60FC0842-480F-478E-86D2-B4E3E64B75BF"
SHORTLIST = [
    "Konosuba!: God's Blessing on This Wonderful World! - Legend of Crimson",
    "Is It Wrong to Try to Pick Up Girls in a Dungeon - Arrow of the Orion",
    "Demon Slayer: Kimetsu no Yaiba - The Movie: Mugen Train",
]
THEMES = ["Political", "Military strategy", "Moral ambiguity", "Political intrigue"]


class _CapturedResponse:
    def __init__(self, raw, captured: list[object]) -> None:
        self.raw, self.captured = raw, captured

    def __enter__(self):
        self.raw.__enter__()
        return self

    def __exit__(self, *args):
        return self.raw.__exit__(*args)

    def read(self) -> bytes:
        value = self.raw.read()
        try:
            self.captured.append(json.loads(value.decode("utf-8")))
        except (UnicodeDecodeError, json.JSONDecodeError):
            self.captured.append({"unparseable_provider_response": True})
        return value


class BudgetedOpener:
    def __init__(self) -> None:
        self.reserved = 0.0
        self.calls = 0
        self.responses: list[object] = []

    def __call__(self, request, timeout=8):
        if self.reserved + RESERVATION > CAP:
            raise ProviderUnavailable("final aggregate experiment cap reached")
        self.reserved += RESERVATION
        self.calls += 1
        return _CapturedResponse(urlopen(request, timeout=timeout), self.responses)


def _packet() -> dict[str, object]:
    return {
        "id": "code-geass-final-protocol-v1",
        "shortlist": SHORTLIST,
        "mappings": [{
            "tmdb_id": 255107,
            "tmdb_media_type": "tv",
            "title": "Code Geass: Rozé of the Recapture",
            "qloo_entity_id": ENTITY_ID,
            "qloo_type": "urn:entity:tv_show",
            "qloo_request_type": "urn:entity:tv_show",
        }],
        # Tags and initial shortlist were read from Qloo immediately before
        # this execution. They are frozen here so both arms see identical input.
        "qloo_themes": {ENTITY_ID: THEMES},
        "coverage": "The selection resolved to the verified TV entity; the deterministic movie shortlist exists, but candidate-level thematic explanation is unavailable.",
        "recovery_trigger": (
            "The organizer explicitly values political strategy and moral conflict. "
            "Inspect verified themes first. If those themes confirm the uncertainty and the "
            "existing candidate fit remains unexplained, one focused Qloo investigation is permitted."
        ),
    }


def _transcript(outcome) -> list[dict[str, object]]:
    return [
        {"name": item.name, "arguments": item.arguments, "result": item.result}
        for item in outcome.tool_transcript
    ]


def _c0(registry: RecoveryEvidenceRegistry) -> dict[str, object]:
    """Predeclared comparator: same two reads whenever this exact gap exists."""
    started = time.monotonic()
    themes = registry.execute("inspect_qloo_themes", {"entity_id": ENTITY_ID, "media_type": "tv"})
    focused = registry.execute("query_qloo_focused", {
        "entity_id": ENTITY_ID,
        "media_type": "tv",
        "tags": ["Political", "Military strategy"],
        "question": "Does the existing movie shortlist have additional verified Qloo evidence for political strategy and moral conflict?",
    })
    return {
        "policy": "For this preregistered scenario, inspect themes then make one focused query; never alter the existing shortlist or its order.",
        "decision": "accept_existing_shortlist" if focused["candidate_titles"] else "abstain",
        "evidence_refs": ["packet:scenario", "tool:inspect_qloo_themes", "tool:query_qloo_focused"],
        "stopping_reason": "fixed_c0_two_read_policy",
        "tool_calls": [
            {"name": "inspect_qloo_themes", "arguments": {"entity_id": ENTITY_ID, "media_type": "tv"}, "result": themes},
            {"name": "query_qloo_focused", "arguments": {"entity_id": ENTITY_ID, "media_type": "tv", "tags": ["Political", "Military strategy"], "question": "Does the existing movie shortlist have additional verified Qloo evidence for political strategy and moral conflict?"}, "result": focused},
        ],
        "latency_ms": int((time.monotonic() - started) * 1000),
    }


def main() -> int:
    key = os.getenv("DEEPSEEK_API_KEY", "").strip()
    if not key:
        print("DEEPSEEK_API_KEY is absent; no live model request was made.", file=sys.stderr)
        return 2
    packet = _packet()
    adapter = QlooHttpAdapter()
    c0_registry = RecoveryEvidenceRegistry(packet, focused_query_executor=qloo_focused_executor(adapter))
    c0 = _c0(c0_registry)
    opener = BudgetedOpener()
    agent_registry = RecoveryEvidenceRegistry(packet, focused_query_executor=qloo_focused_executor(adapter))
    outcome = DeepSeekRecoveryExperiment(key, opener, max_cost_usd=CAP).run(
        organizer_objective="Determine whether the verified Code Geass TV selection has enough additional Qloo evidence to defend its immutable movie shortlist for political strategy and moral conflict.",
        attendee_reasons=["political strategy and moral conflict"],
        registry=agent_registry,
    )
    payload = {
        "experiment": "cinebridge-agentic-recovery-final-protocol-v1",
        "executed_at": datetime.now(UTC).isoformat(),
        "aggregate_cap_usd": CAP,
        "preregistration": {
            "tmdb_id": 255107,
            "tmdb_media_type": "tv",
            "qloo_entity_id": ENTITY_ID,
            "qloo_entity_type": "urn:entity:tv_show",
            "initial_shortlist": SHORTLIST,
            "verified_theme_subset": THEMES,
            "ranking_invariant": "The initial deterministic shortlist and order are immutable; Qloo provider scores and ranks are never retained or compared across queries.",
        },
        "c0": c0,
        "agent": {
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
            "tool_calls": _transcript(outcome),
            "tool_selection_model_driven": True,
            "raw_provider_responses": opener.responses,
        },
        "provider_calls": opener.calls,
        "reserved_usd": opener.reserved,
        "actual_estimated_cost_usd": outcome.estimated_cost_usd,
        "price_basis": "DeepSeek Flash peak cache-miss: input $0.30/M, output $1.20/M; estimate only.",
        "production_behavior_changed": False,
    }
    LEDGER.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps({
        "provider_calls": opener.calls,
        "reserved_usd": opener.reserved,
        "actual_estimated_cost_usd": outcome.estimated_cost_usd,
        "agent_stopping_reason": outcome.stopping_reason,
        "agent_tool_calls": len(outcome.tool_transcript),
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
