from __future__ import annotations

import json
import os
import unittest
from datetime import timezone
from urllib.error import HTTPError
from unittest.mock import patch

from app.programming import BoundedDeepSeekExperiment, FilmProgrammingAgent
from app.recommendations import CandidateRecommendation, ProviderCandidate, RecommendationResult
from app.tmdb import TmdbClient, poster_url


def result() -> RecommendationResult:
    candidates = tuple(CandidateRecommendation(rank=index, candidate=ProviderCandidate(str(index), title, 2020, 100, "PG", ("English",), "movie"), fit_explanation=f"Fit {index}", warning_text="Signal only") for index, title in enumerate(("One", "Two", "Three"), 1))
    return RecommendationResult("succeeded", 3, 3, 3, None, "Signal only", "Starting point", None, candidates=candidates)


class StubResponse:
    def __init__(self, payload: object) -> None: self.payload = payload
    def __enter__(self): return self
    def __exit__(self, *_args): return None
    def read(self) -> bytes: return json.dumps(self.payload).encode()


class ProgrammingTests(unittest.TestCase):
    def test_experimental_loop_returns_validated_second_turn_after_one_permitted_lookup(self) -> None:
        responses = iter((
            {"output": [{"type": "function_call", "name": "inspect_qloo_tags", "call_id": "tag_1", "arguments": '{"entity_id":"qloo-tv-1"}'}], "usage": {"input_tokens": 100, "output_tokens": 20}},
            {"output_text": json.dumps({"status": "ready", "summary": "The verified tags support a strategic-conflict reading.", "tradeoffs": ["Audience reasons still differ."], "uncertainty": "No screening-rights evidence was inspected.", "evidence_refs": ["qloo_entity_ids", "tool:inspect_qloo_tags"]}), "usage": {"input_tokens": 110, "output_tokens": 30}},
        ))
        seen = []
        def opener(*_args, **_kwargs): return StubResponse(next(responses))
        def tool(name, arguments):
            seen.append((name, arguments))
            return {"tags": ["political conflict", "strategy"]}
        brief = BoundedDeepSeekExperiment(api_key="test", opener=opener).run(
            result=result(), attendee_reasons=["I enjoy moral conflict"],
            verified_evidence={"qloo_entity_ids": ["qloo-tv-1"], "tmdb": {"id": 255107, "media_type": "tv"}}, tool_executor=tool,
        )
        self.assertEqual(seen, [("inspect_qloo_tags", {"entity_id": "qloo-tv-1"})])
        self.assertEqual(brief.tools_used, ("inspect_qloo_tags",))
        self.assertEqual(brief.input_tokens, 210)
        self.assertEqual(brief.output_tokens, 50)
        self.assertEqual(brief.agent_activity, "experimental_tool_loop")

    def test_experimental_loop_rejects_unpermitted_or_unverified_tool_request(self) -> None:
        def opener(*_args, **_kwargs):
            return StubResponse({"output": [{"type": "function_call", "name": "inspect_qloo_tags", "call_id": "tag_1", "arguments": '{"entity_id":"unknown"}'}]})
        def tool(*_args):
            self.fail("unverified entity must never reach the evidence executor")
        brief = BoundedDeepSeekExperiment(api_key="test", opener=opener).run(
            result=result(), attendee_reasons=[], verified_evidence={"qloo_entity_ids": ["known"]}, tool_executor=tool,
        )
        self.assertEqual(brief.agent_activity, "deterministic_only")
        self.assertEqual(brief.tools_used, ())

    def test_experimental_loop_stops_before_second_turn_at_cost_cap(self) -> None:
        calls = []
        def opener(*_args, **_kwargs):
            calls.append("model")
            return StubResponse({"output": [{"type": "function_call", "name": "inspect_qloo_tags", "call_id": "tag_1", "arguments": '{"entity_id":"known"}'}], "usage": {"input_tokens": 600000, "output_tokens": 0}})
        def tool(*_args):
            self.fail("cost cap must stop before the evidence lookup")
        brief = BoundedDeepSeekExperiment(api_key="test", opener=opener).run(
            result=result(), attendee_reasons=[], verified_evidence={"qloo_entity_ids": ["known"]}, tool_executor=tool,
        )
        self.assertEqual(calls, ["model"])
        self.assertEqual(brief.agent_activity, "deterministic_only")

    def test_experimental_loop_rejects_a_final_answer_that_selects_or_ranks_a_movie(self) -> None:
        responses = iter((
            {"output": [{"type": "function_call", "name": "inspect_movie_metadata", "call_id": "movie_1", "arguments": '{"candidate_id":"1"}'}]},
            {"output_text": json.dumps({"status": "ready", "summary": "Pick an unrelated film.", "tradeoffs": [], "uncertainty": "", "evidence_refs": ["tool:inspect_movie_metadata"], "rank": 1})},
        ))
        def opener(*_args, **_kwargs): return StubResponse(next(responses))
        brief = BoundedDeepSeekExperiment(api_key="test", opener=opener).run(
            result=result(), attendee_reasons=[], verified_evidence={"qloo_entity_ids": []}, tool_executor=lambda *_args: {"year": 2020},
        )
        self.assertEqual(brief.agent_activity, "deterministic_only")
    def test_no_key_preserves_deterministic_shortlist_without_spending(self) -> None:
        brief = FilmProgrammingAgent(api_key="").create_brief(result=result(), event_details="A club night")
        self.assertEqual(brief.status, "ready")
        self.assertEqual(brief.tools_used, ())
        self.assertIn("One", brief.summary)

    def test_agent_is_disabled_by_default_even_when_a_key_exists(self) -> None:
        def opener(*_args, **_kwargs):
            self.fail("the disabled agent must not make a provider request")

        with patch.dict(os.environ, {"FILM_AGENT_ENABLED": "false"}):
            brief = FilmProgrammingAgent(api_key="test", opener=opener).create_brief(
                result=result(), event_details="A club night"
            )
        self.assertEqual(brief.tools_used, ())
        self.assertEqual(brief.agent_activity, "deterministic_only")

    def _verified_evidence(self) -> dict[str, object]:
        return {
            "evidence_refs": ["packet:coverage", "candidate:1"],
            "coverage": {"registered_count": 3, "represented_attendee_count": 3},
            "candidate_evidence": {"1": {"candidate_id": "1", "media_type": "movie", "title": "One"}},
            "qloo_entities": {},
        }

    def test_runtime_agent_completes_a_two_turn_tool_exchange_with_actual_observation(self) -> None:
        responses = iter((
            {"id": "response-1", "output": [{"type": "function_call", "name": "inspect_candidate_evidence", "call_id": "candidate-1", "arguments": '{"candidate_id":"1","media_type":"movie"}'}], "usage": {"input_tokens": 100, "output_tokens": 20}},
            {"output_text": json.dumps({"status": "ready", "summary": "The verified candidate evidence supports the deterministic brief.", "tradeoffs": ["Audience reasons still vary."], "uncertainty": "Rights and availability were not inspected.", "evidence_refs": ["packet:coverage", "tool:inspect_candidate_evidence"]}), "usage": {"input_tokens": 110, "output_tokens": 30}},
        ))
        requests = []
        seen = []

        def opener(request, timeout=8):
            requests.append(json.loads(request.data.decode()))
            return StubResponse(next(responses))

        def tool(name, arguments):
            seen.append((name, arguments))
            return {"candidate_id": "1", "media_type": "movie", "title": "One", "evidence_ref": "candidate:1"}

        with patch.dict(os.environ, {"FILM_AGENT_ENABLED": "true"}):
            brief = FilmProgrammingAgent(api_key="test", opener=opener).create_brief(
                result=result(), event_details="A club night", attendee_reasons=["I enjoy moral conflict"],
                verified_evidence=self._verified_evidence(), tool_executor=tool,
            )

        self.assertEqual(seen, [("inspect_candidate_evidence", {"candidate_id": "1", "media_type": "movie"})])
        self.assertEqual(len(requests), 2)
        self.assertEqual(brief.tools_used, ("inspect_candidate_evidence",))
        self.assertEqual(brief.agent_activity, "agent_tool_loop")
        self.assertEqual(brief.model_turns, 2)
        self.assertEqual(brief.evidence_refs, ("packet:coverage", "tool:inspect_candidate_evidence"))
        self.assertEqual(brief.tool_observations[0].observation["title"], "One")
        for request in requests:
            self.assertNotIn("response_format", request)
            self.assertEqual(request["text"]["format"]["type"], "json_schema")
            self.assertNotIn("json_schema", request["text"]["format"])
        self.assertEqual(requests[1]["input"][0], {"role": "user", "content": requests[0]["input"]})
        self.assertEqual(
            requests[1]["input"][1],
            {"type": "function_call", "name": "inspect_candidate_evidence", "call_id": "candidate-1", "arguments": '{"candidate_id":"1","media_type":"movie"}'},
        )
        self.assertEqual(requests[1]["input"][2]["type"], "function_call_output")
        self.assertEqual(requests[1]["input"][2]["call_id"], "candidate-1")
        self.assertIn('"title": "One"', requests[1]["input"][2]["output"])
        self.assertNotIn("previous_response_id", requests[1])

    def test_runtime_agent_accepts_a_valid_no_action_final_without_fabricating_a_tool_trace(self) -> None:
        def opener(*_args, **_kwargs):
            return StubResponse({"output_text": json.dumps({"status": "clarification_needed", "summary": "The deterministic evidence is sufficient for an organizer review.", "tradeoffs": [], "uncertainty": "No additional observation was requested.", "evidence_refs": ["packet:coverage"]}), "usage": {"input_tokens": 80, "output_tokens": 20}})

        with patch.dict(os.environ, {"FILM_AGENT_ENABLED": "true"}):
            brief = FilmProgrammingAgent(api_key="test", opener=opener).create_brief(
                result=result(), event_details="A club night", verified_evidence=self._verified_evidence(), tool_executor=lambda *_args: self.fail("no-action response must not execute a tool"),
            )

        self.assertEqual(brief.agent_activity, "agent_no_action")
        self.assertEqual(brief.model_turns, 1)
        self.assertEqual(brief.tools_used, ())
        self.assertEqual(brief.tool_observations, ())

    def test_runtime_agent_rejects_invalid_tool_arguments_without_execution(self) -> None:
        def opener(*_args, **_kwargs):
            return StubResponse({"output": [{"type": "function_call", "name": "inspect_candidate_evidence", "call_id": "candidate-1", "arguments": '{"candidate_id":"unknown","media_type":"movie"}'}]})

        with patch.dict(os.environ, {"FILM_AGENT_ENABLED": "true"}):
            brief = FilmProgrammingAgent(api_key="test", opener=opener).create_brief(
                result=result(), event_details="A club night", verified_evidence=self._verified_evidence(), tool_executor=lambda *_args: self.fail("invalid arguments must not reach the executor"),
            )

        self.assertEqual(brief.agent_activity, "agent_rejected_output")
        self.assertEqual(brief.tool_observations[0].status, "rejected")
        self.assertEqual(brief.tool_observations[0].observation, {"reason": "invalid_arguments"})

    def test_runtime_agent_rejects_invalid_evidence_references_after_tool_observation(self) -> None:
        responses = iter((
            {"output": [{"type": "function_call", "name": "inspect_audience_coverage", "call_id": "coverage-1", "arguments": "{}"}]},
            {"output_text": json.dumps({"status": "ready", "summary": "Unsupported conclusion.", "tradeoffs": [], "uncertainty": "", "evidence_refs": ["invented:evidence"]})},
        ))

        with patch.dict(os.environ, {"FILM_AGENT_ENABLED": "true"}):
            brief = FilmProgrammingAgent(api_key="test", opener=lambda *_args, **_kwargs: StubResponse(next(responses))).create_brief(
                result=result(), event_details="A club night", verified_evidence=self._verified_evidence(), tool_executor=lambda *_args: {"registered_count": 3, "evidence_ref": "packet:coverage"},
            )

        self.assertEqual(brief.agent_activity, "agent_rejected_output")
        self.assertEqual(brief.tools_used, ("inspect_audience_coverage",))
        self.assertEqual(brief.tool_observations[0].observation["evidence_ref"], "packet:coverage")

    def test_runtime_agent_reports_provider_failure_without_a_fake_tool_call(self) -> None:
        def opener(*_args, **_kwargs):
            raise OSError("provider down")

        with patch.dict(os.environ, {"FILM_AGENT_ENABLED": "true"}):
            brief = FilmProgrammingAgent(api_key="test", opener=opener).create_brief(
                result=result(), event_details="A club night", verified_evidence=self._verified_evidence(), tool_executor=lambda *_args: self.fail("provider failure must not execute a tool"),
            )

        self.assertEqual(brief.agent_activity, "agent_provider_unavailable")
        self.assertEqual(brief.model_turns, 1)
        self.assertEqual(brief.tools_used, ())
        self.assertEqual(brief.tool_observations, ())

    def test_runtime_agent_enforces_aggregate_token_and_cost_limits_before_tool_execution(self) -> None:
        def opener(*_args, **_kwargs):
            return StubResponse({"output": [{"type": "function_call", "name": "inspect_audience_coverage", "call_id": "coverage-1", "arguments": "{}"}], "usage": {"input_tokens": 100001, "output_tokens": 0}})

        with patch.dict(os.environ, {"FILM_AGENT_ENABLED": "true"}):
            brief = FilmProgrammingAgent(api_key="test", opener=opener).create_brief(
                result=result(), event_details="A club night", verified_evidence=self._verified_evidence(), tool_executor=lambda *_args: self.fail("token limit must stop before tool execution"),
            )

        self.assertEqual(brief.agent_activity, "agent_limits_exceeded")
        self.assertEqual(brief.model_turns, 1)

    def test_runtime_agent_falls_back_on_truncated_model_output_without_tool_activity(self) -> None:
        def opener(*_args, **_kwargs):
            return StubResponse({"output": [{"type": "function_call", "name": "inspect_audience_coverage", "call_id": "coverage-1", "arguments": "{}"}], "usage": {"input_tokens": 100, "output_tokens": 1201}})

        with patch.dict(os.environ, {"FILM_AGENT_ENABLED": "true"}):
            brief = FilmProgrammingAgent(api_key="test", opener=opener).create_brief(
                result=result(), event_details="A club night", verified_evidence=self._verified_evidence(), tool_executor=lambda *_args: self.fail("truncated output must stop before tool execution"),
            )

        self.assertEqual(brief.agent_activity, "agent_limits_exceeded")
        self.assertEqual(brief.model_turns, 1)
        self.assertEqual(brief.tool_observations, ())

    def test_runtime_agent_honors_cost_limit_without_fabricating_tool_activity(self) -> None:
        def opener(*_args, **_kwargs):
            return StubResponse({"output": [{"type": "function_call", "name": "inspect_audience_coverage", "call_id": "coverage-1", "arguments": "{}"}], "usage": {"input_tokens": 100, "output_tokens": 20}})

        with patch.dict(os.environ, {"FILM_AGENT_ENABLED": "true"}), patch.object(FilmProgrammingAgent, "max_cost_usd", 0.00001):
            brief = FilmProgrammingAgent(api_key="test", opener=opener).create_brief(
                result=result(), event_details="A club night", verified_evidence=self._verified_evidence(), tool_executor=lambda *_args: self.fail("cost limit must stop before tool execution"),
            )

        self.assertEqual(brief.agent_activity, "agent_limits_exceeded")
        self.assertEqual(brief.model_turns, 1)
        self.assertEqual(brief.tool_observations, ())

    def test_runtime_agent_redacts_attendee_identifiers_from_provider_context(self) -> None:
        requests = []

        def opener(request, timeout=8):
            requests.append(request.data.decode())
            return StubResponse({"output_text": json.dumps({"status": "ready", "summary": "Verified evidence is available.", "tradeoffs": [], "uncertainty": "", "evidence_refs": ["packet:coverage"]})})

        with patch.dict(os.environ, {"FILM_AGENT_ENABLED": "true"}):
            FilmProgrammingAgent(api_key="test", opener=opener).create_brief(
                result=result(), event_details="A club night", attendee_reasons=["attendee id=secret-123 Alice loves this; alice@example.com"],
                verified_evidence=self._verified_evidence(), tool_executor=lambda *_args: {},
            )

        self.assertEqual(len(requests), 1)
        self.assertNotIn("secret-123", requests[0])
        self.assertNotIn("alice@example.com", requests[0])
        self.assertIn("redacted", requests[0])

    def test_malformed_search_arguments_fail_safe_without_changing_the_brief(self) -> None:
        def opener(request, timeout=8):
            return StubResponse({"output": [{"type": "function_call", "name": "search_current_info", "call_id": "call_1", "arguments": None}], "usage": {"input_tokens": "bad", "output_tokens": -1}})

        with patch.dict(os.environ, {"FILM_AGENT_ENABLED": "true"}):
            brief = FilmProgrammingAgent(api_key="test", opener=opener).create_brief(
                result=result(), event_details="latest releases", verified_evidence=self._verified_evidence(), tool_executor=lambda *_args: self.fail("malformed arguments must not reach the executor"),
            )
        self.assertEqual(brief.agent_activity, "agent_rejected_output")
        self.assertEqual(brief.status, "ready")
        self.assertEqual(brief.tools_used, ())
        self.assertIn("One", brief.summary)
        self.assertEqual(brief.input_tokens, 0)
        self.assertEqual(brief.output_tokens, 0)

    def test_tmdb_year_mismatch_does_not_attach_wrong_artwork(self) -> None:
        client = TmdbClient(api_key="test", opener=lambda *_args, **_kwargs: StubResponse({"results": [{"id": 9, "release_date": "1999-01-01", "poster_path": "/wrong.jpg"}]}))
        poster = client.find_movie("A film", 2020)
        self.assertIsNone(poster.tmdb_id)
        self.assertIsNone(poster_url(poster.poster_path))

    def test_tmdb_accepts_an_unambiguous_exact_title_within_one_year(self) -> None:
        client = TmdbClient(
            api_key="test",
            opener=lambda *_args, **_kwargs: StubResponse(
                {"results": [{"id": 9, "title": "The requested film", "release_date": "2021-01-01", "poster_path": "/right.jpg"}]}
            ),
        )

        poster = client.find_movie("The requested film", 2020)

        self.assertEqual(poster.tmdb_id, 9)
        self.assertEqual(poster.poster_path, "/right.jpg")

    def test_tmdb_uses_stable_fallback_for_equally_nearby_exact_title_matches(self) -> None:
        client = TmdbClient(
            api_key="test",
            opener=lambda *_args, **_kwargs: StubResponse(
                {"results": [
                    {"id": 9, "title": "The requested film", "release_date": "2019-01-01", "poster_path": "/one.jpg"},
                    {"id": 10, "title": "The requested film", "release_date": "2021-01-01", "poster_path": "/two.jpg"},
                ]}
            ),
        )

        poster = client.find_movie("The requested film", 2020)

        self.assertEqual(poster.tmdb_id, 9)
        self.assertEqual(poster.poster_path, "/one.jpg")

    def test_tmdb_title_mismatch_does_not_attach_same_year_artwork(self) -> None:
        client = TmdbClient(api_key="test", opener=lambda *_args, **_kwargs: StubResponse({"results": [{"id": 9, "title": "A different film", "release_date": "2020-01-01", "poster_path": "/wrong.jpg"}]}))
        poster = client.find_movie("The requested film", 2020)
        self.assertIsNone(poster.tmdb_id)
        self.assertIsNone(poster.poster_path)

    def test_tmdb_malformed_search_results_fail_safe(self) -> None:
        client = TmdbClient(api_key="test", opener=lambda *_args, **_kwargs: StubResponse({"results": None}))
        poster = client.find_movie("The requested film", 2020)
        self.assertIsNone(poster.tmdb_id)
        self.assertIsNone(poster.poster_path)
        self.assertEqual(poster.looked_up_at.tzinfo, timezone.utc)

    def test_tmdb_accepts_normalized_exact_title_and_year(self) -> None:
        client = TmdbClient(api_key="test", opener=lambda *_args, **_kwargs: StubResponse({"results": [{"id": 9, "title": "  THE REQUESTED FILM ", "release_date": "2020-01-01", "poster_path": "/right.jpg"}]}))
        poster = client.find_movie("The requested film", 2020)
        self.assertEqual(poster.tmdb_id, 9)
        self.assertEqual(poster_url(poster.poster_path), "https://image.tmdb.org/t/p/w342/right.jpg")

    def test_tmdb_accepts_collapsed_title_whitespace_without_relaxing_title_matching(self) -> None:
        client = TmdbClient(
            api_key="test",
            opener=lambda *_args, **_kwargs: StubResponse(
                {
                    "results": [
                        {
                            "id": 9,
                            "title": "The   requested film",
                            "release_date": "2020-01-01",
                            "poster_path": "/right.jpg",
                        }
                    ]
                }
            ),
        )

        poster = client.find_movie("The requested\u00a0film", 2020)

        self.assertEqual(poster.tmdb_id, 9)
        self.assertEqual(poster.poster_path, "/right.jpg")

    def test_tmdb_invalid_lookup_metadata_keeps_the_placeholder(self) -> None:
        client = TmdbClient(
            api_key="test",
            opener=lambda *_args, **_kwargs: self.fail("invalid metadata must not call TMDB"),
        )

        for title, release_year in ((None, 2020), ("The requested film", True), ("", None)):
            with self.subTest(title=title, release_year=release_year):
                poster = client.find_movie(title, release_year)
                self.assertIsNone(poster.tmdb_id)
                self.assertIsNone(poster.poster_path)
                self.assertIsNotNone(poster.looked_up_at)

    def test_tmdb_rejects_a_title_plus_subtitle_as_a_different_movie(self) -> None:
        client = TmdbClient(api_key="test", opener=lambda *_args, **_kwargs: StubResponse({"results": [{"id": 9, "title": "The requested film: Part II", "release_date": "2020-01-01", "poster_path": "/wrong.jpg"}]}))
        poster = client.find_movie("The requested film", 2020)
        self.assertIsNone(poster.tmdb_id)
        self.assertIsNone(poster.poster_path)

    def test_tmdb_uses_stable_fallback_for_ambiguous_exact_title_and_year_matches(self) -> None:
        client = TmdbClient(
            api_key="test",
            opener=lambda *_args, **_kwargs: StubResponse(
                {
                    "results": [
                        {"id": 9, "title": "The requested film", "release_date": "2020-01-01", "poster_path": "/one.jpg"},
                        {"id": 10, "title": "THE REQUESTED FILM", "release_date": "2020-06-01", "poster_path": "/two.jpg"},
                    ]
                }
            ),
        )
        poster = client.find_movie("The requested film", 2020)
        self.assertEqual(poster.tmdb_id, 9)
        self.assertEqual(poster.poster_path, "/one.jpg")

    def test_tmdb_uses_verified_runtime_to_break_an_exact_title_year_tie(self) -> None:
        def opener(request, timeout=5):
            if "/search/movie?" in request.full_url:
                return StubResponse(
                    {"results": [
                        {"id": 9, "title": "The requested film", "release_date": "2021-01-01", "poster_path": None},
                        {"id": 10, "title": "The requested film", "release_date": "2021-05-01", "poster_path": None},
                    ]}
                )
            if "/movie/9?" in request.full_url:
                return StubResponse({"id": 9, "runtime": 138})
            if "/movie/10?" in request.full_url:
                return StubResponse({"id": 10, "runtime": 78})
            return StubResponse({"id": 10, "posters": []})

        poster = TmdbClient(api_key="test", opener=opener).find_movie(
            "The requested film", 2020, 81
        )

        self.assertEqual(poster.tmdb_id, 10)
        self.assertIsNone(poster.poster_path)

    def test_tmdb_uses_stable_fallback_for_ambiguous_exact_title_with_unknown_year(self) -> None:
        client = TmdbClient(
            api_key="test",
            opener=lambda *_args, **_kwargs: StubResponse(
                {
                    "results": [
                        {"id": 9, "title": "The requested film", "release_date": "2020-01-01", "poster_path": "/one.jpg"},
                        {"id": 10, "title": "The requested film", "release_date": "2021-01-01", "poster_path": "/two.jpg"},
                    ]
                }
            ),
        )
        poster = client.find_movie("The requested film", None)
        self.assertEqual(poster.tmdb_id, 9)
        self.assertEqual(poster.poster_path, "/one.jpg")

    def test_tmdb_prefers_popularity_before_stable_id_for_an_unresolved_tie(self) -> None:
        client = TmdbClient(
            api_key="test",
            opener=lambda *_args, **_kwargs: StubResponse(
                {"results": [
                    {"id": 9, "title": "The requested film", "release_date": "2021-01-01", "popularity": 2.0, "poster_path": None},
                    {"id": 10, "title": "The requested film", "release_date": "2021-02-01", "popularity": 5.0, "poster_path": None},
                ]}
            ),
        )

        poster = client.find_movie("The requested film", 2020)

        self.assertEqual(poster.tmdb_id, 10)

    def test_tmdb_rejects_a_tv_payload_even_when_title_and_year_match(self) -> None:
        client = TmdbClient(
            api_key="test",
            opener=lambda *_args, **_kwargs: StubResponse(
                {
                    "results": [
                        {
                            "id": 9,
                            "media_type": "tv",
                            "name": "The requested film",
                            "first_air_date": "2020-01-01",
                            "poster_path": "/wrong-medium.jpg",
                        }
                    ]
                }
            ),
        )
        poster = client.find_movie("The requested film", 2020)
        self.assertIsNone(poster.tmdb_id)
        self.assertIsNone(poster.poster_path)

    def test_tmdb_malformed_media_and_language_fields_fail_safe(self) -> None:
        def opener(request, timeout=5):
            if "/search/movie?" in request.full_url:
                return StubResponse(
                    {
                        "results": [
                            {
                                "id": 9,
                                "media_type": "movie",
                                "title": "The requested film",
                                "release_date": "2020-01-01",
                                "poster_path": None,
                            }
                        ]
                    }
                )
            return StubResponse(
                {
                    "id": 9,
                    "posters": [
                        {"iso_639_1": {"language": "en"}, "file_path": "/wrong.jpg"}
                    ],
                }
            )

        poster = TmdbClient(api_key="test", opener=opener).find_movie(
            "The requested film", 2020
        )

        self.assertEqual(poster.tmdb_id, 9)
        self.assertIsNone(poster.poster_path)
        self.assertIsNone(poster_url({"path": "/wrong.jpg"}))

    def test_tmdb_uses_unfiltered_same_movie_art_when_language_filter_has_no_images(self) -> None:
        requests: list[str] = []

        def opener(request, timeout=5):
            requests.append(request.full_url)
            if "/search/movie?" in request.full_url:
                return StubResponse(
                    {
                        "results": [
                            {
                                "id": 9,
                                "title": "The requested film",
                                "release_date": "2020-01-01",
                                "poster_path": None,
                            }
                        ]
                    }
                )
            if "/movie/9/images?" in request.full_url and "include_image_language" in request.full_url:
                return StubResponse({"id": 9, "posters": []})
            if "/movie/9/images?" in request.full_url:
                return StubResponse(
                    {
                        "id": 9,
                        "posters": [{"iso_639_1": "fr", "file_path": "/same-film-fr.jpg"}],
                    }
                )
            return StubResponse({})

        poster = TmdbClient(api_key="test", opener=opener).find_movie("The requested film", 2020)

        self.assertEqual(poster.tmdb_id, 9)
        self.assertEqual(poster.poster_path, "/same-film-fr.jpg")
        self.assertIsNotNone(poster.looked_up_at.tzinfo)
        self.assertEqual(poster.looked_up_at.tzinfo, timezone.utc)
        self.assertTrue(any("include_image_language=en%2Cnull" in request for request in requests))
        self.assertTrue(any(request.endswith("/movie/9/images?api_key=test") for request in requests))

    def test_tmdb_does_not_accept_a_non_preferred_language_from_the_filtered_response(self) -> None:
        requests: list[str] = []

        def opener(request, timeout=5):
            requests.append(request.full_url)
            if "/search/movie?" in request.full_url:
                return StubResponse(
                    {
                        "results": [
                            {
                                "id": 9,
                                "title": "The requested film",
                                "release_date": "2020-01-01",
                                "poster_path": None,
                            }
                        ]
                    }
                )
            if "include_image_language" in request.full_url:
                return StubResponse(
                    {"id": 9, "posters": [{"iso_639_1": "fr", "file_path": "/filtered-fr.jpg"}]}
                )
            return StubResponse(
                {"id": 9, "posters": [{"iso_639_1": "fr", "file_path": "/fallback-fr.jpg"}]}
            )

        poster = TmdbClient(api_key="test", opener=opener).find_movie("The requested film", 2020)

        self.assertEqual(poster.poster_path, "/fallback-fr.jpg")
        self.assertTrue(any(request.endswith("/movie/9/images?api_key=test") for request in requests))

    def test_tmdb_repairs_a_broken_path_without_changing_the_movie_id(self) -> None:
        requests: list[str] = []

        def opener(request, timeout=5):
            requests.append(request.full_url)
            if "/search/movie?" in request.full_url:
                return StubResponse(
                    {
                        "results": [
                            {
                                "id": 9,
                                "title": "The requested film",
                                "release_date": "2020-01-01",
                                "poster_path": "/broken.jpg",
                            }
                        ]
                    }
                )
            if request.full_url.endswith("/broken.jpg"):
                raise HTTPError(request.full_url, 404, "missing", {}, None)
            if "/movie/9/images?" in request.full_url:
                return StubResponse(
                    {
                        "id": 9,
                        "posters": [{"iso_639_1": "en", "file_path": "/verified-alternative.jpg"}],
                    }
                )
            return StubResponse({})

        poster = TmdbClient(api_key="test", opener=opener).find_movie("The requested film", 2020)

        self.assertEqual(poster.tmdb_id, 9)
        self.assertEqual(poster.poster_path, "/verified-alternative.jpg")
        self.assertNotIn("/broken.jpg", poster.poster_path)

    def test_tmdb_replaces_a_non_image_response_with_same_movie_artwork(self) -> None:
        class ImageResponse:
            def __init__(self, content_type: str) -> None:
                self.status = 200
                self.headers = {"content-type": content_type}

            def __enter__(self): return self
            def __exit__(self, *_args): return None

        def opener(request, timeout=5):
            if "/search/movie?" in request.full_url:
                return StubResponse(
                    {
                        "results": [
                            {
                                "id": 9,
                                "title": "The requested film",
                                "release_date": "2020-01-01",
                                "poster_path": "/html-error.jpg",
                            }
                        ]
                    }
                )
            if request.full_url.endswith("/html-error.jpg"):
                return ImageResponse("text/html")
            if "/movie/9/images?" in request.full_url:
                return StubResponse(
                    {
                        "id": 9,
                        "posters": [{"iso_639_1": "en", "file_path": "/same-film.jpg"}],
                    }
                )
            if request.full_url.endswith("/same-film.jpg"):
                return ImageResponse("image/jpeg; charset=utf-8")
            return StubResponse({})

        poster = TmdbClient(api_key="test", opener=opener).find_movie("The requested film", 2020)

        self.assertEqual(poster.tmdb_id, 9)
        self.assertEqual(poster.poster_path, "/same-film.jpg")

    def test_tmdb_rejects_an_unverified_images_payload_without_changing_movie_identity(self) -> None:
        requests: list[str] = []

        def opener(request, timeout=5):
            requests.append(request.full_url)
            if "/search/movie?" in request.full_url:
                return StubResponse(
                    {
                        "results": [
                            {
                                "id": 9,
                                "title": "The requested film",
                                "release_date": "2020-01-01",
                                "poster_path": None,
                            }
                        ]
                    }
                )
            if "include_image_language" in request.full_url:
                return StubResponse({"posters": [{"file_path": "/unverified.jpg"}]})
            return StubResponse({"id": 999, "posters": [{"file_path": "/wrong-film.jpg"}]})

        poster = TmdbClient(api_key="test", opener=opener).find_movie("The requested film", 2020)

        self.assertEqual(poster.tmdb_id, 9)
        self.assertIsNone(poster.poster_path)
        self.assertNotIn("/unverified.jpg", requests)

    def test_tmdb_keeps_the_verified_id_and_uses_placeholder_when_no_artwork_is_available(self) -> None:
        def opener(request, timeout=5):
            if "/search/movie?" in request.full_url:
                return StubResponse(
                    {
                        "results": [
                            {
                                "id": 9,
                                "title": "The requested film",
                                "release_date": "2020-01-01",
                                "poster_path": None,
                            }
                        ]
                    }
                )
            return StubResponse({"id": 9, "posters": []})

        poster = TmdbClient(api_key="test", opener=opener).find_movie("The requested film", 2020)

        self.assertEqual(poster.tmdb_id, 9)
        self.assertIsNone(poster.poster_path)
        self.assertIsNotNone(poster.looked_up_at)


if __name__ == "__main__":
    unittest.main()
