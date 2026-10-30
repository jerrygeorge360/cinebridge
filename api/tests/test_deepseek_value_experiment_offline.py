from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path

from app.programming import BoundedDeepSeekExperiment
from app.recommendations import CandidateRecommendation, ProviderCandidate, RecommendationResult


FIXTURE_PATH = Path(__file__).parent / "fixtures" / "deepseek_value_experiment_v1.json"


def _result(titles: list[str]) -> RecommendationResult:
    candidates = tuple(
        CandidateRecommendation(
            rank=index,
            candidate=ProviderCandidate(f"fixture-candidate-{index}", title, 2024, 100, "PG", ("English",), "movie"),
            fit_explanation=f"Fixture fit {index}",
            warning_text="Fixture evidence only",
        )
        for index, title in enumerate(titles, 1)
    )
    return RecommendationResult("succeeded", 40, 40, 40, None, "Fixture warning", "Fixture result", None, candidates=candidates)


class StubResponse:
    def __init__(self, payload: object) -> None:
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def read(self) -> bytes:
        return json.dumps(self.payload).encode()


class OfflineValueExperimentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.fixture = json.loads(FIXTURE_PATH.read_text())

    def test_all_seven_packets_are_redacted_and_digestable(self) -> None:
        scenarios = self.fixture["scenarios"]
        self.assertEqual(len(scenarios), 7)
        self.assertEqual(len({item["id"] for item in scenarios}), 7)
        encoded = json.dumps(self.fixture, sort_keys=True, separators=(",", ":")).encode()
        self.assertEqual(len(hashlib.sha256(encoded).hexdigest()), 64)
        self.assertNotIn("sk-", json.dumps(self.fixture).casefold())

    def test_offline_a_b_c0_c_controls_preserve_authoritative_shortlists(self) -> None:
        """Fixture-model outputs test the harness only; they are not DeepSeek results."""
        for scenario in self.fixture["scenarios"]:
            with self.subTest(scenario=scenario["id"]):
                result = _result(scenario["shortlist"])
                # A: the deterministic baseline remains the unchanged source of rank.
                baseline = BoundedDeepSeekExperiment._fallback(result)
                self.assertEqual(baseline.agent_activity, "deterministic_only")
                self.assertEqual([item.candidate.title for item in result.candidates], scenario["shortlist"])

                status = {"brief": "ready", "clarification_needed": "clarification_needed", "abstain": "abstain"}[scenario["expected"]]
                output = json.dumps({
                    "status": status,
                    "summary": "Fixture-only evidence interpretation; no candidate is selected.",
                    "tradeoffs": ["Fixture trade-off is explicitly bounded by the evidence packet."],
                    "uncertainty": "This offline control makes no claim beyond packet evidence.",
                    "evidence_refs": ["packet:scenario"],
                })
                # Offline fixture responses intentionally name no candidate and
                # contain no ordinal or numeric score.  This lets the harness
                # verify that its advisory prose cannot change the frozen order.
                for title in scenario["shortlist"]:
                    self.assertNotIn(title.casefold(), output.casefold())
                self.assertNotIn("#", output)
                self.assertNotIn("score", output.casefold())
                evidence = {"packet:scenario": scenario, "qloo_entity_ids": [mapping["qloo_entity_id"] for mapping in scenario.get("mappings", []) if mapping.get("qloo_entity_id")]}

                # B and C0 are same-evidence, no-tool controls. They use a local
                # fixture response, so this proves validation—not model quality.
                for condition in ("B", "C0"):
                    validated = BoundedDeepSeekExperiment._validated_brief(output, baseline, set(evidence))
                    self.assertIsNotNone(validated, condition)
                    assert validated is not None
                    self.assertEqual(validated.status, status)
                    self.assertEqual(validated.tools_used, ())
                    self.assertNotIn("fixture-candidate", validated.summary.casefold())

                # C requests exactly one permitted fixture lookup only where tags
                # exist; other scenarios finish without a tool request.
                responses = []
                tool_calls: list[tuple[str, dict[str, object]]] = []
                if scenario.get("qloo_tags"):
                    responses.extend((
                        {"output": [{"type": "function_call", "name": "inspect_movie_metadata", "call_id": "fixture-call", "arguments": '{"candidate_id":"fixture-candidate-1"}'}], "usage": {"input_tokens": 10, "output_tokens": 2}},
                        {"output_text": output, "usage": {"input_tokens": 10, "output_tokens": 2}},
                    ))
                else:
                    responses.append({"output_text": output, "usage": {"input_tokens": 10, "output_tokens": 2}})

                def opener(*_args, **_kwargs):
                    return StubResponse(responses.pop(0))

                def tool(name: str, arguments: dict[str, object]) -> dict[str, object]:
                    tool_calls.append((name, arguments))
                    return {"fixture_tags": scenario.get("qloo_tags", [])}

                brief = BoundedDeepSeekExperiment(api_key="offline-fixture", opener=opener).run(
                    result=result,
                    attendee_reasons=scenario["attendee_reasons"],
                    verified_evidence=evidence,
                    tool_executor=tool,
                )
                self.assertEqual(brief.status, status)
                self.assertLess(brief.estimated_cost_usd, 0.15)
                self.assertLessEqual(len(tool_calls), 1)
                if scenario.get("qloo_tags"):
                    self.assertEqual(tool_calls[0][0], "inspect_movie_metadata")
                    self.assertEqual(brief.tools_used, ("inspect_movie_metadata",))
                else:
                    self.assertEqual(tool_calls, [])
                    self.assertEqual(brief.tools_used, ())

    def test_unqualified_brief_is_not_used_for_weak_or_contradictory_packets(self) -> None:
        for scenario in self.fixture["scenarios"]:
            if scenario["id"] not in {"weak-coverage-v1", "contradictory-preferences-v1", "ambiguous-title-v1"}:
                continue
            with self.subTest(scenario=scenario["id"]):
                self.assertIn(scenario["expected"], {"abstain", "clarification_needed"})

    def test_code_geass_packet_preserves_the_correct_tv_mapping_and_shortlist_trace(self) -> None:
        scenario = next(item for item in self.fixture["scenarios"] if item["id"] == "code-geass-politics-v1")
        mapping = scenario["mappings"][0]
        self.assertEqual(mapping["tmdb_id"], 255107)
        self.assertEqual(mapping["tmdb_media_type"], "tv")
        self.assertEqual(mapping["qloo_request_type"], "urn:entity:tv_show")
        self.assertEqual(mapping["qloo_type"], "urn:entity:tv_show")
        self.assertEqual(scenario["insights_request"]["signal_entity_id"], mapping["qloo_entity_id"])
        self.assertEqual(scenario["raw_candidates"], scenario["shortlist"])

    def test_ambiguous_aot_packet_keeps_legacy_text_separate_from_verified_tv_selection(self) -> None:
        scenario = next(item for item in self.fixture["scenarios"] if item["id"] == "ambiguous-title-v1")
        legacy, verified = scenario["mappings"]
        self.assertEqual(legacy["tmdb_title"], "AOT")
        self.assertIn("unresolved", legacy["resolution"])
        self.assertEqual(verified["tmdb_media_type"], "tv")
        self.assertEqual(verified["qloo_type"], "urn:entity:tv_show")
