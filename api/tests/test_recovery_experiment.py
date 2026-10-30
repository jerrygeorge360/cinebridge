from __future__ import annotations

import copy
import json
import unittest
from unittest.mock import patch
from pathlib import Path

from app.recovery_experiment import DeepSeekRecoveryExperiment, RecoveryEvidenceRegistry, deterministic_recovery, qloo_focused_executor
from app.recommendations import QlooHttpAdapter


FIXTURE_PATH = Path(__file__).parent / "fixtures" / "deepseek_value_experiment_v1.json"
RECOVERY_FIXTURE_PATH = Path(__file__).parent / "fixtures" / "recovery_experiment_v1.json"


class StubResponse:
    def __init__(self, payload: object) -> None:
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def read(self) -> bytes:
        return json.dumps(self.payload).encode()


def _packet(scenario_id: str = "code-geass-politics-v1") -> dict[str, object]:
    fixture = json.loads(FIXTURE_PATH.read_text())
    packet = copy.deepcopy(next(item for item in fixture["scenarios"] if item["id"] == scenario_id))
    if scenario_id == "code-geass-politics-v1":
        packet["qloo_themes"] = {"fixture-code-geass-tv": ["political conflict", "strategy"]}
        packet["candidate_evidence"] = {
            "Fixture KonoSuba": {"year": 2019, "media_type": "movie"},
            "Fixture DanMachi": {"year": 2019, "media_type": "movie"},
            "Fixture Demon Slayer": {"year": 2020, "media_type": "movie"},
        }
        packet["focused_query_results"] = {
            "fixture-code-geass-tv|strategy": {"candidate_titles": ["Fixture KonoSuba"], "evidence": "Fixture-only thematic trace."}
        }
    return packet


def _call(name: str, arguments: dict[str, object], call_id: str = "call-1") -> dict[str, object]:
    return {
        "output": [{"type": "function_call", "name": name, "call_id": call_id, "arguments": json.dumps(arguments)}],
        "usage": {"input_tokens": 10, "output_tokens": 2},
    }


def _final(decision: str = "accept_existing_shortlist", refs: list[str] | None = None) -> dict[str, object]:
    return {
        "output_text": json.dumps({
            "decision": decision,
            "observation": "Only verified fixture evidence was considered.",
            "uncertainty": "The deterministic shortlist remains unchanged.",
            "evidence_refs": refs or ["packet:scenario"],
            "stopping_reason": "The available evidence does not justify another lookup.",
        }),
        "usage": {"input_tokens": 12, "output_tokens": 3},
    }


class RecoveryEvidenceRegistryTests(unittest.TestCase):
    def test_c0_runs_all_seven_frozen_recovery_scenarios(self) -> None:
        fixture = json.loads(RECOVERY_FIXTURE_PATH.read_text())
        self.assertEqual(len(fixture["scenarios"]), 7)
        for packet in fixture["scenarios"]:
            with self.subTest(scenario=packet["id"]):
                outcome = deterministic_recovery(RecoveryEvidenceRegistry(packet))
                expected = packet["expected_outcome"]
                self.assertEqual(
                    outcome.decision,
                    {"accept": "accept_existing_shortlist", "abstain": "abstain", "clarification_needed": "clarification_needed"}[expected],
                )
                self.assertLessEqual(len(outcome.tool_transcript), 2)
                self.assertEqual(tuple(RecoveryEvidenceRegistry(packet).shortlist), tuple(packet["shortlist"]))

    def test_theme_registry_requires_verified_entity_and_matching_media_type(self) -> None:
        registry = RecoveryEvidenceRegistry(_packet())
        self.assertEqual(
            registry.execute("inspect_qloo_themes", {"entity_id": "fixture-code-geass-tv", "media_type": "tv"})["tags"],
            ["political conflict", "strategy"],
        )
        with self.assertRaises(ValueError):
            registry.execute("inspect_qloo_themes", {"entity_id": "fixture-code-geass-tv", "media_type": "movie"})
        with self.assertRaises(ValueError):
            registry.execute("inspect_qloo_themes", {"entity_id": "invented", "media_type": "tv"})

    def test_focused_query_rejects_unverified_tags_new_candidates_and_ranking_data(self) -> None:
        registry = RecoveryEvidenceRegistry(_packet())
        with self.assertRaises(ValueError):
            registry.execute("query_qloo_focused", {"entity_id": "fixture-code-geass-tv", "media_type": "tv", "tags": ["invented"], "question": "Check themes"})
        packet = _packet()
        packet["focused_query_results"] = {"fixture-code-geass-tv|strategy": {"candidate_titles": ["New Film"]}}
        with self.assertRaises(ValueError):
            RecoveryEvidenceRegistry(packet).execute("query_qloo_focused", {"entity_id": "fixture-code-geass-tv", "media_type": "tv", "tags": ["strategy"], "question": "Check themes"})

    def test_live_focused_executor_filters_to_existing_shortlist_and_drops_scores(self) -> None:
        adapter = QlooHttpAdapter(api_key="test")
        provider_items = {"results": [
            {"entity_id": "one", "title": "Fixture KonoSuba", "subtype": "urn:entity:movie", "score": 0.99},
            {"entity_id": "new", "title": "Unrelated Film", "subtype": "urn:entity:movie", "score": 0.98},
        ]}
        with patch.object(adapter, "_request_json", return_value=provider_items):
            result = qloo_focused_executor(adapter)("fixture-code-geass-tv", "tv", ["strategy"], "Check themes", ("Fixture KonoSuba", "Fixture DanMachi"))
        self.assertEqual(result["candidate_titles"], ["Fixture KonoSuba"])
        self.assertNotIn("score", result)
        self.assertNotIn("rank", result)
        packet = _packet()
        packet["focused_query_results"] = {"fixture-code-geass-tv|strategy": {"candidate_titles": ["Fixture KonoSuba"], "raw_score": 99}}
        with self.assertRaises(ValueError):
            RecoveryEvidenceRegistry(packet).execute("query_qloo_focused", {"entity_id": "fixture-code-geass-tv", "media_type": "tv", "tags": ["strategy"], "question": "Check themes"})

    def test_live_focused_executor_is_advertised_without_fixture_results(self) -> None:
        registry = RecoveryEvidenceRegistry(_packet(), focused_query_executor=lambda *_args: {"candidate_titles": []})
        self.assertTrue(registry.available_evidence()["focused_query_registered"])

    def test_deterministic_recovery_abstains_for_frozen_low_coverage_without_model_use(self) -> None:
        outcome = deterministic_recovery(RecoveryEvidenceRegistry(_packet("weak-coverage-v1")))
        self.assertEqual(outcome.decision, "abstain")
        self.assertEqual(outcome.model_turns, 0)
        self.assertEqual(outcome.tool_transcript[0].name, "inspect_audience_coverage")


class DeepSeekRecoveryExperimentTests(unittest.TestCase):
    def _run(self, responses: list[dict[str, object]], packet: dict[str, object] | None = None):
        seen = []
        def opener(request, timeout=8):
            seen.append(request)
            return StubResponse(responses.pop(0))
        result = DeepSeekRecoveryExperiment(api_key="fixture-key", opener=opener).run(
            organizer_objective="Assess a frozen shortlist.",
            attendee_reasons=["political strategy and moral conflict"],
            registry=RecoveryEvidenceRegistry(packet or _packet()),
        )
        return result, seen

    def test_valid_two_lookup_recovery_and_final_abstention_are_recorded(self) -> None:
        responses = [
            _call("inspect_qloo_themes", {"entity_id": "fixture-code-geass-tv", "media_type": "tv"}, "themes"),
            _call("inspect_movie_evidence", {"candidate_title": "Fixture KonoSuba"}, "movie"),
            _final("abstain", ["packet:scenario", "tool:inspect_qloo_themes", "tool:inspect_movie_evidence"]),
        ]
        outcome, calls = self._run(responses)
        self.assertEqual(len(calls), 3)
        self.assertEqual(outcome.decision, "abstain")
        self.assertEqual(outcome.model_turns, 3)
        self.assertEqual([item.name for item in outcome.tool_transcript], ["inspect_qloo_themes", "inspect_movie_evidence"])
        self.assertEqual(outcome.stopping_reason, "The available evidence does not justify another lookup.")

    def test_low_coverage_agent_checks_coverage_then_abstains(self) -> None:
        packet = _packet("weak-coverage-v1")
        outcome, calls = self._run(
            [_call("inspect_audience_coverage", {}, "coverage"), _final("abstain", ["packet:scenario", "tool:inspect_audience_coverage"])],
            packet,
        )
        self.assertEqual(len(calls), 2)
        self.assertEqual(outcome.decision, "abstain")
        self.assertEqual([entry.name for entry in outcome.tool_transcript], ["inspect_audience_coverage"])

    def test_model_and_lookup_limits_stop_a_third_tool_call(self) -> None:
        responses = [
            _call("inspect_qloo_themes", {"entity_id": "fixture-code-geass-tv", "media_type": "tv"}, "one"),
            _call("inspect_movie_evidence", {"candidate_title": "Fixture KonoSuba"}, "two"),
            _call("inspect_movie_evidence", {"candidate_title": "Fixture DanMachi"}, "three"),
        ]
        outcome, calls = self._run(responses)
        self.assertEqual(len(calls), 3)
        self.assertEqual(outcome.stopping_reason, "lookup_limit_reached")
        self.assertEqual(outcome.model_turns, 3)
        self.assertEqual(len(outcome.tool_transcript), 2)

    def test_only_one_focused_qloo_query_is_permitted(self) -> None:
        responses = [
            _call("query_qloo_focused", {"entity_id": "fixture-code-geass-tv", "media_type": "tv", "tags": ["strategy"], "question": "Does stored evidence support strategy?"}, "focused-one"),
            _call("query_qloo_focused", {"entity_id": "fixture-code-geass-tv", "media_type": "tv", "tags": ["strategy"], "question": "Repeat the query?"}, "focused-two"),
        ]
        outcome, calls = self._run(responses)
        self.assertEqual(len(calls), 2)
        self.assertEqual(outcome.stopping_reason, "focused_query_limit_reached")
        self.assertEqual([item.name for item in outcome.tool_transcript], ["query_qloo_focused"])

    def test_invalid_or_unverified_tool_request_abstains_without_executing_tool(self) -> None:
        outcome, calls = self._run([_call("inspect_qloo_themes", {"entity_id": "fiction", "media_type": "tv"})])
        self.assertEqual(len(calls), 1)
        self.assertEqual(outcome.decision, "abstain")
        self.assertEqual(outcome.stopping_reason, "invalid_tool_arguments")
        self.assertEqual(outcome.tool_transcript, ())

    def test_candidate_and_rank_invariance_rejects_model_override(self) -> None:
        packet = _packet()
        original_shortlist = copy.deepcopy(packet["shortlist"])
        invalid = _final()
        invalid["output_text"] = json.dumps({
            "decision": "accept_existing_shortlist", "observation": "A candidate must move to first place.",
            "uncertainty": "Fixture uncertainty.", "evidence_refs": ["packet:scenario"],
            "stopping_reason": "ranked it", "rank": 1,
        })
        outcome, _calls = self._run([invalid], packet)
        self.assertEqual(outcome.decision, "abstain")
        self.assertEqual(outcome.stopping_reason, "invalid_final_response")
        self.assertEqual(packet["shortlist"], original_shortlist)
        self.assertEqual(tuple(RecoveryEvidenceRegistry(packet).shortlist), tuple(original_shortlist))

    def test_provider_request_enforces_required_json_schema(self) -> None:
        outcome, calls = self._run([_final()])
        self.assertEqual(outcome.decision, "accept_existing_shortlist")
        payload = json.loads(calls[0].data.decode())
        output_format = payload["text"]["format"]
        self.assertEqual(output_format["type"], "json_schema")
        self.assertEqual(output_format["name"], "recovery_outcome")
        self.assertEqual(output_format["schema"]["required"], ["decision", "observation", "uncertainty", "evidence_refs", "stopping_reason"])
        self.assertEqual(output_format["schema"]["properties"]["evidence_refs"]["minItems"], 1)


if __name__ == "__main__":
    unittest.main()
