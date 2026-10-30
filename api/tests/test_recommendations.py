from __future__ import annotations

import json
import os
import unittest
from datetime import date, datetime, timedelta, timezone
from urllib.parse import urlparse
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.main as main_module
from app.database import get_db
from app.models import Base, EventAccessToken, RecommendationCandidate, RecommendationRun, Selection
from app.programming import FilmProgrammingAgent
from app.rate_limit import RateLimiter
from app.recommendations import (
    AudienceMember,
    AudiencePreference,
    DeterministicFakeQlooAdapter,
    ProviderCandidate,
    QlooError,
    QlooHttpAdapter,
    RecommendationEngine,
    RecommendationService,
    ResolvedTitle,
    normalize_query_ranks,
)
from app.security import digest_token
from app.tmdb import Poster


def provider_candidate(
    entity_id: str,
    title: str,
    *,
    raw_score: float | None = None,
    eligible: bool = True,
    media_type: str | None = "movie",
) -> ProviderCandidate:
    return ProviderCandidate(
        entity_id=entity_id,
        title=title,
        release_year=2020,
        runtime_minutes=110,
        content_rating="PG-13",
        languages=("English",),
        media_type=media_type,
        eligible=eligible,
        raw_score=raw_score,
    )


class RecommendationPolicyTests(unittest.TestCase):
    def test_code_geass_tv_selection_uses_tv_entity_before_insights(self) -> None:
        """Regression for TMDB TV 255107, never substituting its movie part."""
        class StubResponse:
            def __init__(self, payload: object) -> None:
                self.payload = payload

            def __enter__(self):
                return self

            def __exit__(self, *_args) -> None:
                return None

            def read(self) -> bytes:
                import json

                return json.dumps(self.payload).encode("utf-8")

        seed_id = "code-geass-tv-255107"
        responses = [
            StubResponse(
                {
                    "results": [
                        {
                            "entity_id": seed_id,
                            "name": "Code Geass: Rozé of the Recapture",
                            "types": ["urn:entity:tv_show"],
                            "properties": {"first_air_date": "2024-06-21"},
                        }
                    ]
                }
            ),
            StubResponse(
                {
                    "success": True,
                    "results": {
                        "entities": [
                            {
                                "entity_id": "konosuba-movie",
                                "name": "KonoSuba: God's Blessing on This Wonderful World! Legend of Crimson",
                                "subtype": "urn:entity:movie",
                                "properties": {"release_year": 2025},
                            },
                            {
                                "entity_id": "danmachi-movie",
                                "name": "DanMachi: Arrow of the Orion",
                                "subtype": "urn:entity:movie",
                                "properties": {"release_year": 2025, "duration": 100},
                            },
                            {
                                "entity_id": "demon-slayer-movie",
                                "name": "Demon Slayer: Kimetsu no Yaiba - The Movie: Mugen Train",
                                "subtype": "urn:entity:movie",
                                "properties": {"release_year": 2025},
                            },
                        ]
                    },
                }
            ),
        ]

        with patch("app.recommendations.urlopen", side_effect=responses) as mocked_urlopen:
            adapter = QlooHttpAdapter(api_key="test-key", base_url="https://qloo.test")
            resolved = adapter.resolve_title(
                "Code Geass: Rozé of the Recapture",
                media_type="tv",
                release_date="2024-06-21",
            )
            self.assertEqual(
                resolved,
                ResolvedTitle(seed_id, "Code Geass: Rozé of the Recapture", "urn:entity:tv_show"),
            )
            candidates = adapter.rank_for_interest(resolved)

        self.assertEqual(
            [candidate.title for candidate in candidates],
            [
                "KonoSuba: God's Blessing on This Wonderful World! Legend of Crimson",
                "DanMachi: Arrow of the Orion",
                "Demon Slayer: Kimetsu no Yaiba - The Movie: Mugen Train",
            ],
        )
        rank_request = mocked_urlopen.call_args_list[1].args[0]
        self.assertIn(f"signal.interests.entities={seed_id}", rank_request.full_url)
        search_request = mocked_urlopen.call_args_list[0].args[0]
        self.assertIn("types=urn%3Aentity%3Atv_show", search_request.full_url)
        self.assertIn("filter.type=urn%3Aentity%3Amovie", rank_request.full_url)

        result = RecommendationEngine(adapter=DeterministicFakeQlooAdapter(
            resolutions={}, rankings={seed_id: candidates}
        )).recommend(
            [
                AudienceMember(
                    id="attendee",
                    preferences=(
                        AudiencePreference(
                            title_text="Code Geass: Rozé of the Recapture",
                            qloo_entity_id=seed_id,
                            qloo_title="Code Geass: Rozé of the Recapture",
                        ),
                    ),
                )
            ]
        )
        self.assertEqual(result.status, "succeeded")
        self.assertEqual(
            [item.candidate.title for item in result.candidates],
            [
                "KonoSuba: God's Blessing on This Wonderful World! Legend of Crimson",
                "DanMachi: Arrow of the Orion",
                "Demon Slayer: Kimetsu no Yaiba - The Movie: Mugen Train",
            ],
        )

    def test_tv_resolution_rejects_same_title_movie_entity(self) -> None:
        class StubResponse:
            def __enter__(self): return self
            def __exit__(self, *_args): return None
            def read(self) -> bytes:
                import json
                return json.dumps({"results": [{
                    "entity_id": "movie-part-one",
                    "name": "Code Geass: Rozé of the Recapture - Part 1",
                    "types": ["urn:entity:movie"],
                    "properties": {"release_year": 2024},
                }]}).encode("utf-8")

        with patch("app.recommendations.urlopen", return_value=StubResponse()):
            adapter = QlooHttpAdapter(api_key="test-key", base_url="https://qloo.test")
            self.assertIsNone(adapter.resolve_title(
                "Code Geass: Rozé of the Recapture", media_type="tv", release_date="2024-06-21"
            ))

    def test_verified_lupin_selection_uses_persisted_matching_qloo_entity(self) -> None:
        adapter = DeterministicFakeQlooAdapter(
            # A free-text lookup would be a different authority and must not
            # replace the persisted canonical selection.
            resolutions={"lupin": ResolvedTitle("wrong-lupin", "Lupin")},
            rankings={
                "lupin-tv": (
                    provider_candidate("one", "One"),
                    provider_candidate("two", "Two"),
                    provider_candidate("three", "Three"),
                )
            },
        )

        result = RecommendationEngine(adapter).recommend(
            [
                AudienceMember(
                    "lupin-attendee",
                    (
                        AudiencePreference(
                            "Lupin",
                            tmdb_id=96677,
                            media_type="tv",
                            qloo_entity_id="lupin-tv",
                            qloo_entity_type="urn:entity:tv_show",
                            qloo_resolution_status="resolved",
                        ),
                    ),
                )
            ]
        )

        self.assertEqual(result.status, "succeeded")
        self.assertEqual(adapter.resolved_queries, [])
        self.assertEqual(adapter.ranking_queries, ["lupin-tv"])

    def test_persisted_cross_media_resolution_is_not_used_for_selected_title(self) -> None:
        adapter = DeterministicFakeQlooAdapter(
            resolutions={"lupin": ResolvedTitle("wrong-lupin", "Lupin")},
            rankings={
                "lupin-movie": (
                    provider_candidate("one", "One"),
                    provider_candidate("two", "Two"),
                    provider_candidate("three", "Three"),
                )
            },
        )

        result = RecommendationEngine(adapter).recommend(
            [
                AudienceMember(
                    "lupin-attendee",
                    (
                        AudiencePreference(
                            "Lupin",
                            tmdb_id=96677,
                            media_type="tv",
                            qloo_entity_id="lupin-movie",
                            qloo_entity_type="urn:entity:movie",
                            qloo_resolution_status="resolved",
                        ),
                    ),
                )
            ]
        )

        self.assertEqual(result.status, "unavailable")
        self.assertEqual(result.failure_code, "insufficient_coverage")
        self.assertEqual(adapter.resolved_queries, [])

    def test_movie_resolution_uses_movie_entity_type_and_validates_available_year(self) -> None:
        class StubResponse:
            def __init__(self, payload: object) -> None: self.payload = payload
            def __enter__(self): return self
            def __exit__(self, *_args): return None
            def read(self) -> bytes:
                import json
                return json.dumps(self.payload).encode("utf-8")

        with patch("app.recommendations.urlopen", return_value=StubResponse({"results": [{
            "entity_id": "movie-id", "name": "Arrival", "types": ["urn:entity:movie"],
            "properties": {"release_year": 2016},
        }]})) as mocked_urlopen:
            adapter = QlooHttpAdapter(api_key="test-key", base_url="https://qloo.test")
            self.assertEqual(
                adapter.resolve_title("Arrival", media_type="movie", release_date="2016-09-01"),
                ResolvedTitle("movie-id", "Arrival", "urn:entity:movie"),
            )
        self.assertIn("types=urn%3Aentity%3Amovie", mocked_urlopen.call_args.args[0].full_url)

        with patch("app.recommendations.urlopen", return_value=StubResponse({"results": [{
            "entity_id": "wrong-year", "name": "Arrival", "types": ["urn:entity:movie"],
            "properties": {"release_year": 2017},
        }]})):
            self.assertIsNone(adapter.resolve_title("Arrival", media_type="movie", release_date="2016-09-01"))

    def test_qloo_resolution_rejects_unrelated_abbreviation_result(self) -> None:
        class StubResponse:
            def __init__(self, payload: object) -> None:
                self.payload = payload

            def __enter__(self):
                return self

            def __exit__(self, *_args) -> None:
                return None

            def read(self) -> bytes:
                import json

                return json.dumps(self.payload).encode("utf-8")

        with patch(
            "app.recommendations.urlopen",
            return_value=StubResponse({"results": [{"entity_id": "wrong", "name": "Behold a Pale Horse", "types": ["urn:entity:movie"]}]}),
        ):
            adapter = QlooHttpAdapter(api_key="test-key", base_url="https://qloo.test")
            self.assertIsNone(adapter.resolve_title("AOT"))

    def test_qloo_resolution_accepts_exact_and_subtitled_movie_titles(self) -> None:
        class StubResponse:
            def __init__(self, payload: object) -> None:
                self.payload = payload

            def __enter__(self):
                return self

            def __exit__(self, *_args) -> None:
                return None

            def read(self) -> bytes:
                import json

                return json.dumps(self.payload).encode("utf-8")

        responses = [
            StubResponse({"results": [{"entity_id": "aot", "name": "Attack on Titan", "types": ["urn:entity:movie"]}]}),
            StubResponse({"results": [{"entity_id": "demon", "name": "Demon Slayer: Kimetsu no Yaiba - The Movie: Mugen Train", "types": ["urn:entity:movie"]}]}),
        ]
        with patch("app.recommendations.urlopen", side_effect=responses):
            adapter = QlooHttpAdapter(api_key="test-key", base_url="https://qloo.test")
            self.assertEqual(adapter.resolve_title("Attack on Titan"), ResolvedTitle("aot", "Attack on Titan", "urn:entity:movie"))
            self.assertEqual(adapter.resolve_title("Demon Slayer"), ResolvedTitle("demon", "Demon Slayer: Kimetsu no Yaiba - The Movie: Mugen Train", "urn:entity:movie"))

    def test_qloo_http_adapter_uses_current_insights_endpoint_and_maps_movie_properties(self) -> None:
        class StubResponse:
            def __init__(self, payload: object) -> None:
                self.payload = payload

            def __enter__(self):
                return self

            def __exit__(self, *_args) -> None:
                return None

            def read(self) -> bytes:
                import json

                return json.dumps(self.payload).encode("utf-8")

        responses = [
            StubResponse(
                {
                    "results": [
                        {
                            "entity_id": "seed-id",
                            "name": "Seed film",
                            "types": ["urn:entity:movie"],
                        }
                    ]
                }
            ),
            StubResponse(
                {
                    "success": True,
                    "results": {
                        "entities": [
                            {
                                "entity_id": "candidate-id",
                                "name": "Candidate film",
                                "subtype": "urn:entity:movie",
                                "properties": {
                                    "release_year": 2024,
                                    "duration": 108,
                                    "content_rating": "PG-13",
                                },
                            }
                        ]
                    },
                }
            ),
        ]

        with patch("app.recommendations.urlopen", side_effect=responses) as mocked_urlopen:
            adapter = QlooHttpAdapter(api_key="test-key", base_url="https://qloo.test")
            resolved = adapter.resolve_title("Seed film")
            candidates = adapter.rank_for_interest(resolved)

        self.assertEqual(resolved, ResolvedTitle("seed-id", "Seed film", "urn:entity:movie"))
        self.assertEqual(candidates[0].title, "Candidate film")
        self.assertEqual(candidates[0].media_type, "movie")
        self.assertEqual(candidates[0].runtime_minutes, 108)
        self.assertEqual(candidates[0].content_rating, "PG-13")
        search_request = mocked_urlopen.call_args_list[0].args[0]
        rank_request = mocked_urlopen.call_args_list[1].args[0]
        self.assertEqual(search_request.get_method(), "GET")
        self.assertEqual(rank_request.get_method(), "GET")
        self.assertIn("types=urn%3Aentity%3Amovie", search_request.full_url)
        self.assertIn("filter.type=urn%3Aentity%3Amovie", rank_request.full_url)
        self.assertIn("signal.interests.entities=seed-id", rank_request.full_url)

    def test_positions_are_normalized_after_eligibility_filtering_and_scores_are_ignored(self) -> None:
        normalized = normalize_query_ranks(
            [
                provider_candidate("blocked", "Blocked", raw_score=0.99, eligible=False),
                provider_candidate("a", "Film A", raw_score=0.01),
                provider_candidate("b", "Film B", raw_score=0.98),
                provider_candidate("c", "Film C", raw_score=-10.0),
            ]
        )

        self.assertEqual([candidate.entity_id for candidate, _ in normalized], ["a", "b", "c"])
        self.assertEqual([score for _, score in normalized], [1.0, 0.5, 0.0])

        with_different_scores = normalize_query_ranks(
            [
                provider_candidate("a", "Film A", raw_score=1000.0),
                provider_candidate("b", "Film B", raw_score=-1000.0),
                provider_candidate("c", "Film C", raw_score=0.0),
            ]
        )
        self.assertEqual(
            [(candidate.entity_id, score) for candidate, score in normalized[1:]],
            [(candidate.entity_id, score) for candidate, score in with_different_scores[1:]],
        )

    def test_dissimilar_attendee_group_returns_majority_cross_audience_fit(self) -> None:
        adapter = DeterministicFakeQlooAdapter(
            resolutions={
                "majority title": ResolvedTitle("interest-majority", "Majority title"),
                "minority title": ResolvedTitle("interest-minority", "Minority title"),
            },
            rankings={
                "interest-majority": (
                    provider_candidate("film-majority", "Majority film"),
                    provider_candidate("film-third", "Third film"),
                    provider_candidate("film-shared", "Shared film"),
                ),
                "interest-minority": (
                    provider_candidate("film-shared", "Shared film"),
                    provider_candidate("film-minority", "Minority film"),
                    provider_candidate("film-third", "Third film"),
                ),
            },
        )
        engine = RecommendationEngine(adapter)

        result = engine.recommend(
            [
                AudienceMember("attendee-1", (AudiencePreference("Majority title"),)),
                AudienceMember("attendee-2", (AudiencePreference("Majority title"),)),
                AudienceMember("attendee-3", (AudiencePreference("Minority title"),)),
            ]
        )

        self.assertEqual(result.status, "succeeded")
        self.assertEqual(result.registered_count, 3)
        self.assertEqual(result.usable_preference_count, 3)
        self.assertEqual(result.represented_attendee_count, 3)
        self.assertIsNone(result.warning_code)
        self.assertEqual(len(result.candidates), 3)
        self.assertEqual(result.candidates[0].rank, 1)
        self.assertEqual(result.candidates[0].candidate.title, "Majority film")
        self.assertTrue(result.candidates[0].fit_explanation)
        self.assertIn("Cultural similarity", result.candidates[0].warning_text)
        self.assertEqual(adapter.resolved_queries, ["Majority title", "Minority title"])

    def test_similar_attendee_group_reports_both_attendees_as_candidate_support(self) -> None:
        adapter = DeterministicFakeQlooAdapter(
            resolutions={"shared title": ResolvedTitle("shared", "Shared title")},
            rankings={
                "shared": (
                    provider_candidate("shared-film", "Shared-first film"),
                    provider_candidate("second-film", "Second film"),
                    provider_candidate("third-film", "Third film"),
                )
            },
        )

        result = RecommendationEngine(adapter).recommend(
            [
                AudienceMember("attendee-1", (AudiencePreference("Shared title"),)),
                AudienceMember("attendee-2", (AudiencePreference("Shared title"),)),
            ]
        )

        self.assertEqual(result.status, "succeeded")
        self.assertEqual(result.represented_attendee_count, 2)
        self.assertEqual(result.candidates[0].candidate.title, "Shared-first film")
        self.assertIn("2 represented attendees", result.candidates[0].fit_explanation)
        self.assertEqual(
            [item.attendee_id for item in result.candidates[0].contributor_provenance],
            ["attendee-1", "attendee-2"],
        )
        self.assertEqual(
            [item.interest_entity_ids for item in result.candidates[0].contributor_provenance],
            [("shared",), ("shared",)],
        )

    def test_candidate_supported_by_one_attendee_is_distinguished_from_shared_candidate(self) -> None:
        adapter = DeterministicFakeQlooAdapter(
            resolutions={
                "first title": ResolvedTitle("first", "First title"),
                "second title": ResolvedTitle("second", "Second title"),
            },
            rankings={
                "first": (
                    provider_candidate("a-only", "A-only film"),
                    provider_candidate("shared", "Shared film"),
                    provider_candidate("a-third", "A-third film"),
                ),
                "second": (
                    provider_candidate("b-only", "B-only film"),
                    provider_candidate("shared", "Shared film"),
                    provider_candidate("b-third", "B-third film"),
                ),
            },
        )

        result = RecommendationEngine(adapter).recommend(
            [
                AudienceMember("attendee-a", (AudiencePreference("First title"),)),
                AudienceMember("attendee-b", (AudiencePreference("Second title"),)),
            ]
        )

        self.assertEqual(result.represented_attendee_count, 2)
        explanations = {
            item.candidate.title: item.fit_explanation for item in result.candidates
        }
        self.assertIn("2 represented attendees", explanations["Shared film"])
        self.assertIn("1 represented attendee", explanations["A-only film"])
        self.assertIn("1 represented attendee", explanations["B-only film"])

    def test_missing_and_unresolved_preferences_are_excluded_but_coverage_is_explicit(self) -> None:
        adapter = DeterministicFakeQlooAdapter(
            resolutions={"supported": ResolvedTitle("supported", "Supported")},
            rankings={
                "supported": (
                    provider_candidate("one", "One"),
                    provider_candidate("two", "Two"),
                    provider_candidate("three", "Three"),
                )
            },
        )

        result = RecommendationEngine(adapter).recommend(
            [
                AudienceMember("blank-attendee", ()),
                AudienceMember("unresolved-attendee", (AudiencePreference("Unknown"),)),
                AudienceMember("supported-attendee", (AudiencePreference("Supported"),)),
            ]
        )

        self.assertEqual(result.status, "limited")
        self.assertEqual(result.registered_count, 3)
        self.assertEqual(result.usable_preference_count, 2)
        self.assertEqual(result.represented_attendee_count, 1)
        self.assertIn("1 of 3", result.warning_text)
        self.assertEqual(adapter.ranking_queries, ["supported"])

    def test_unequal_interest_counts_preserve_one_unit_of_weight_per_attendee(self) -> None:
        adapter = DeterministicFakeQlooAdapter(
            resolutions={
                "one interest": ResolvedTitle("one", "One interest"),
                "first of three": ResolvedTitle("three-a", "First of three"),
                "second of three": ResolvedTitle("three-b", "Second of three"),
                "third of three": ResolvedTitle("three-c", "Third of three"),
            },
            rankings={
                "one": (
                    provider_candidate("x", "One-attendee favorite"),
                    provider_candidate("z", "Z film"),
                    provider_candidate("w", "W film"),
                    provider_candidate("v", "V film"),
                    provider_candidate("y", "Three-attendee favorite"),
                ),
                "three-a": (
                    provider_candidate("y", "Three-attendee favorite"),
                    provider_candidate("x", "One-attendee favorite"),
                ),
                "three-b": (
                    provider_candidate("y", "Three-attendee favorite"),
                    provider_candidate("x", "One-attendee favorite"),
                ),
                "three-c": (
                    provider_candidate("y", "Three-attendee favorite"),
                    provider_candidate("x", "One-attendee favorite"),
                ),
            },
        )

        result = RecommendationEngine(adapter).recommend(
            [
                AudienceMember("one-interest-attendee", (AudiencePreference("One interest"),)),
                AudienceMember(
                    "three-interest-attendee",
                    (
                        AudiencePreference("First of three"),
                        AudiencePreference("Second of three"),
                        AudiencePreference("Third of three"),
                    ),
                ),
            ]
        )

        # The second attendee's three interests are averaged into one unit of
        # weight, so the solo attendee's first-place candidate remains first.
        self.assertEqual(result.candidates[0].candidate.title, "One-attendee favorite")

    def test_unresolved_selected_title_is_not_re_resolved_from_bare_free_text(self) -> None:
        adapter = DeterministicFakeQlooAdapter(
            resolutions={"home alone": ResolvedTitle("wrong-movie", "Home Alone")},
            rankings={
                "wrong-movie": (
                    provider_candidate("one", "One"),
                    provider_candidate("two", "Two"),
                    provider_candidate("three", "Three"),
                )
            },
        )

        result = RecommendationEngine(adapter).recommend(
            [
                AudienceMember(
                    "selected-tv-attendee",
                    (
                        AudiencePreference(
                            "Home Alone",
                            tmdb_id=771305,
                            media_type="tv",
                            qloo_entity_id=None,
                            qloo_resolution_status="unresolved",
                        ),
                    ),
                )
            ]
        )

        self.assertEqual(result.status, "unavailable")
        self.assertEqual(result.failure_code, "insufficient_coverage")
        self.assertEqual(adapter.resolved_queries, [])

    def test_low_coverage_is_limited_but_still_returns_a_complete_shortlist(self) -> None:
        adapter = DeterministicFakeQlooAdapter(
            resolutions={"supported": ResolvedTitle("interest", "Supported")},
            rankings={
                "interest": (
                    provider_candidate("one", "One"),
                    provider_candidate("two", "Two"),
                    provider_candidate("three", "Three"),
                )
            },
        )
        result = RecommendationEngine(adapter).recommend(
            [
                AudienceMember("supported-attendee", (AudiencePreference("Supported"),)),
                AudienceMember("blank-attendee", ()),
            ]
        )

        self.assertEqual(result.status, "limited")
        self.assertEqual(result.warning_code, "limited_coverage")
        self.assertEqual(result.represented_attendee_count, 1)
        self.assertEqual(len(result.candidates), 3)
        self.assertIn("1 of 2", result.warning_text)

    def test_provider_failure_and_insufficient_candidates_are_unavailable_without_candidates(self) -> None:
        failure = DeterministicFakeQlooAdapter(fail_with=QlooError("secret provider detail"))
        failed = RecommendationEngine(failure).recommend(
            [AudienceMember("attendee", (AudiencePreference("Anything"),))]
        )
        self.assertEqual(failed.status, "unavailable")
        self.assertEqual(failed.warning_code, "provider_unavailable")
        self.assertEqual(failed.candidates, ())
        self.assertNotIn("secret provider detail", failed.message)

        insufficient = DeterministicFakeQlooAdapter(
            resolutions={"supported": ResolvedTitle("interest", "Supported")},
            rankings={"interest": (provider_candidate("one", "One"),)},
        )
        unavailable = RecommendationEngine(insufficient).recommend(
            [AudienceMember("attendee", (AudiencePreference("Supported"),))]
        )
        self.assertEqual(unavailable.status, "unavailable")
        self.assertEqual(unavailable.warning_code, "insufficient_coverage")
        self.assertEqual(unavailable.candidates, ())


class RecommendationApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        os.environ["TOKEN_DIGEST_SECRET"] = "test-only-token-digest-secret"
        os.environ["WEB_BASE_URL"] = "https://cinebridge.test"
        cls.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(cls.engine)
        cls.session_factory = sessionmaker(bind=cls.engine, autoflush=False, expire_on_commit=False)

        def override_get_db():
            db = cls.session_factory()
            try:
                yield db
            finally:
                db.close()

        main_module.app.dependency_overrides[get_db] = override_get_db
        cls.client = TestClient(main_module.app)

    @classmethod
    def tearDownClass(cls) -> None:
        main_module.app.dependency_overrides.clear()
        cls.engine.dispose()

    def setUp(self) -> None:
        main_module.rate_limiter = RateLimiter()
        main_module.app.dependency_overrides.pop(main_module.get_recommendation_service, None)

    def create_event(self) -> tuple[str, str]:
        response = self.client.post(
            "/events",
            json={
                "name": "Recommendation test event",
                "theme": "A bounded theme",
                "screening_date": (date.today() + timedelta(days=14)).isoformat(),
                "essential_details": "Details",
            },
        )
        self.assertEqual(response.status_code, 201, response.text)
        created = response.json()
        return (
            urlparse(created["public_registration_url"]).path.rsplit("/", 1)[-1],
            urlparse(created["private_management_url"]).path.rsplit("/", 1)[-1],
        )

    def register(self, public_token: str, display_name: str, preferences: list[dict[str, str]]) -> None:
        response = self.client.post(
            f"/events/public/{public_token}/registrations",
            json={"display_name": display_name, "preferences": preferences},
        )
        self.assertEqual(response.status_code, 201, response.text)

    def test_successful_private_request_returns_one_top_pick_and_two_alternatives(self) -> None:
        public_token, private_token = self.create_event()
        self.register(public_token, "Maya", [{"title_text": "Moonlight"}])
        self.register(public_token, "Ife", [{"title_text": "Moonlight"}])
        adapter = DeterministicFakeQlooAdapter(
            resolutions={"moonlight": ResolvedTitle("moonlight", "Moonlight")},
            rankings={
                "moonlight": (
                    provider_candidate("film-1", "Film one"),
                    provider_candidate("film-2", "Film two"),
                    provider_candidate("film-3", "Film three"),
                )
            },
        )
        main_module.app.dependency_overrides[main_module.get_recommendation_service] = lambda: RecommendationService(adapter)

        response = self.client.post(f"/events/private/{private_token}/recommendations", json={})

        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["status"], "succeeded")
        self.assertEqual(body["registered_count"], 2)
        self.assertEqual(body["represented_attendee_count"], 2)
        self.assertEqual(body["top_pick"]["rank"], 1)
        self.assertEqual(len(body["alternatives"]), 2)
        self.assertEqual(
            [body["top_pick"]["rank"], *(item["rank"] for item in body["alternatives"])],
            [1, 2, 3],
        )
        self.assertTrue(body["top_pick"]["fit_explanation"])
        self.assertTrue(body["top_pick"]["warning_text"])
        self.assertNotIn("moonlight", response.text.casefold())
        self.assertNotIn("attendee_id", response.text)
        self.assertNotIn("interest_entity_ids", response.text)
        self.assertNotIn("raw_score", response.text)
        self.assertNotIn("QLOO_API_KEY", response.text)

        with self.session_factory() as db:
            run = db.scalar(select(RecommendationRun).order_by(RecommendationRun.requested_at.desc()))
            self.assertIsNotNone(run)
            self.assertEqual(run.status, "succeeded")
            self.assertEqual(len(run.candidates), 3)
            self.assertTrue(all(candidate.provider_entity_id for candidate in run.candidates))
            for candidate in run.candidates:
                provenance = json.loads(candidate.contributor_provenance)
                self.assertEqual(len(provenance), 2)
                self.assertTrue(all(item["attendee_id"] for item in provenance))
                self.assertTrue(
                    all(item["interest_entity_ids"] == ["moonlight"] for item in provenance)
                )
                self.assertTrue(
                    all(item["interest_titles"] == ["Moonlight"] for item in provenance)
                )

    def test_staging_agent_activity_observation_and_turn_count_are_persisted_and_returned(self) -> None:
        public_token, private_token = self.create_event()
        self.register(public_token, "Maya", [{"title_text": "Moonlight", "enjoyed_text": "I like moral conflict"}])
        adapter = DeterministicFakeQlooAdapter(
            resolutions={"moonlight": ResolvedTitle("moonlight", "Moonlight")},
            rankings={
                "moonlight": (
                    provider_candidate("film-1", "Film one"),
                    provider_candidate("film-2", "Film two"),
                    provider_candidate("film-3", "Film three"),
                )
            },
        )
        main_module.app.dependency_overrides[main_module.get_recommendation_service] = lambda: RecommendationService(adapter)
        responses = iter((
            {"id": "runtime-1", "output": [{"type": "function_call", "name": "inspect_candidate_evidence", "call_id": "candidate-1", "arguments": '{"candidate_id":"film-1","media_type":"movie"}'}]},
            {"output_text": json.dumps({"status": "ready", "summary": "The verified candidate observation supports the deterministic brief.", "tradeoffs": ["Audience reasons still vary."], "uncertainty": "Rights and availability were not inspected.", "evidence_refs": ["packet:coverage", "tool:inspect_candidate_evidence"]})},
        ))

        class StubResponse:
            def __init__(self, payload: object) -> None:
                self.payload = payload
            def __enter__(self):
                return self
            def __exit__(self, *_args):
                return None
            def read(self) -> bytes:
                return json.dumps(self.payload).encode()

        previous_agent = main_module.programming_agent
        main_module.programming_agent = FilmProgrammingAgent(
            api_key="test",
            opener=lambda *_args, **_kwargs: StubResponse(next(responses)),
        )
        try:
            with patch.dict(os.environ, {"FILM_AGENT_ENABLED": "true"}):
                response = self.client.post(f"/events/private/{private_token}/recommendations", json={})
        finally:
            main_module.programming_agent = previous_agent

        self.assertEqual(response.status_code, 200, response.text)
        brief = response.json()["programming_brief"]
        self.assertEqual(brief["agent_activity"], "agent_tool_loop")
        self.assertEqual(brief["model_turns"], 2)
        self.assertEqual(brief["tools_used"], ["inspect_candidate_evidence"])
        self.assertEqual(brief["tool_observations"][0]["status"], "executed")
        self.assertEqual(brief["tool_observations"][0]["observation"]["title"], "Film one")
        self.assertIn("tool:inspect_candidate_evidence", brief["evidence_refs"])
        self.assertNotIn("attendee_id", response.text)
        with self.session_factory() as db:
            run = db.scalar(select(RecommendationRun).order_by(RecommendationRun.requested_at.desc()))
            stored_brief = json.loads(run.programming_brief)
            self.assertEqual(stored_brief["model_turns"], 2)
            self.assertEqual(stored_brief["tool_observations"][0]["name"], "inspect_candidate_evidence")
            self.assertIn("tool:inspect_candidate_evidence", stored_brief["evidence_refs"])

    def test_verified_artwork_identity_path_and_lookup_timestamp_are_persisted(self) -> None:
        public_token, private_token = self.create_event()
        self.register(public_token, "Maya", [{"title_text": "Moonlight"}])
        adapter = DeterministicFakeQlooAdapter(
            resolutions={"moonlight": ResolvedTitle("moonlight", "Moonlight")},
            rankings={
                "moonlight": (
                    provider_candidate("film-1", "Film one"),
                    provider_candidate("film-2", "Film two"),
                    provider_candidate("film-3", "Film three"),
                )
            },
        )
        main_module.app.dependency_overrides[main_module.get_recommendation_service] = lambda: RecommendationService(adapter)
        previous_tmdb_client = main_module.tmdb_client
        lookup_time = datetime.now(timezone.utc)

        class StubTmdbClient:
            def find_movie(
                self,
                title: str,
                release_year: int | None,
                runtime_minutes: int | None = None,
            ) -> Poster:
                rank = {"Film one": 1, "Film two": 2, "Film three": 3}[title]
                return Poster(900 + rank, f"/verified-{rank}.jpg", lookup_time)

        main_module.tmdb_client = StubTmdbClient()
        try:
            response = self.client.post(f"/events/private/{private_token}/recommendations", json={})
        finally:
            main_module.tmdb_client = previous_tmdb_client

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["top_pick"]["poster_url"], "https://image.tmdb.org/t/p/w342/verified-1.jpg")
        with self.session_factory() as db:
            run = db.scalar(select(RecommendationRun).order_by(RecommendationRun.requested_at.desc()))
            candidates = sorted(run.candidates, key=lambda candidate: candidate.rank)
            self.assertEqual([candidate.tmdb_id for candidate in candidates], [901, 902, 903])
            self.assertEqual([candidate.poster_path for candidate in candidates], ["/verified-1.jpg", "/verified-2.jpg", "/verified-3.jpg"])
            for candidate in candidates:
                self.assertIsNotNone(candidate.poster_looked_up_at)
                stored_time = candidate.poster_looked_up_at
                if stored_time.tzinfo is None:
                    stored_time = stored_time.replace(tzinfo=timezone.utc)
                self.assertLess(abs((stored_time - lookup_time).total_seconds()), 1)
            self.assertEqual([candidate.rank for candidate in candidates], [1, 2, 3])

    def test_qloo_failure_persists_unavailable_run_and_does_not_reuse_prior_candidates(self) -> None:
        public_token, private_token = self.create_event()
        self.register(public_token, "Maya", [{"title_text": "Unknown"}])
        adapter = DeterministicFakeQlooAdapter(fail_with=QlooError("provider payload must stay private"))
        main_module.app.dependency_overrides[main_module.get_recommendation_service] = lambda: RecommendationService(adapter)

        response = self.client.post(f"/events/private/{private_token}/recommendations", json={})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "unavailable")
        self.assertIsNone(response.json()["top_pick"])
        self.assertEqual(response.json()["alternatives"], [])
        self.assertNotIn("provider payload", response.text)

        with self.session_factory() as db:
            run = db.scalar(select(RecommendationRun).order_by(RecommendationRun.requested_at.desc()))
            self.assertEqual(run.status, "unavailable")
            self.assertEqual(run.failure_code, "qloo_unavailable")
            self.assertEqual(db.scalars(select(RecommendationCandidate).where(RecommendationCandidate.run_id == run.id)).all(), [])

    def test_low_coverage_api_response_keeps_three_candidates_and_exposes_aggregate_warning(self) -> None:
        public_token, private_token = self.create_event()
        self.register(public_token, "Supported", [{"title_text": "Supported"}])
        self.register(public_token, "No preferences", [])
        adapter = DeterministicFakeQlooAdapter(
            resolutions={"supported": ResolvedTitle("interest", "Supported")},
            rankings={
                "interest": (
                    provider_candidate("film-1", "Film one"),
                    provider_candidate("film-2", "Film two"),
                    provider_candidate("film-3", "Film three"),
                )
            },
        )
        main_module.app.dependency_overrides[main_module.get_recommendation_service] = lambda: RecommendationService(adapter)

        response = self.client.post(f"/events/private/{private_token}/recommendations", json={})

        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["status"], "limited")
        self.assertEqual(body["registered_count"], 2)
        self.assertEqual(body["represented_attendee_count"], 1)
        self.assertEqual([body["top_pick"]["rank"], *(item["rank"] for item in body["alternatives"])], [1, 2, 3])
        self.assertEqual(body["warning_code"], "limited_coverage")
        self.assertIn("1 of 2", body["warning"])

    def test_private_selection_is_token_scoped_persists_once_and_does_not_announce(self) -> None:
        public_token, private_token = self.create_event()
        self.register(public_token, "Maya", [{"title_text": "Moonlight"}])
        adapter = DeterministicFakeQlooAdapter(
            resolutions={"moonlight": ResolvedTitle("moonlight", "Moonlight")},
            rankings={
                "moonlight": (
                    provider_candidate("film-1", "Film one"),
                    provider_candidate("film-2", "Film two"),
                    provider_candidate("film-3", "Film three"),
                )
            },
        )
        main_module.app.dependency_overrides[main_module.get_recommendation_service] = lambda: RecommendationService(adapter)
        recommendation = self.client.post(f"/events/private/{private_token}/recommendations", json={})
        self.assertEqual(recommendation.status_code, 200)

        selected = self.client.post(f"/events/private/{private_token}/selection", json={"rank": 2})

        self.assertEqual(selected.status_code, 200, selected.text)
        self.assertEqual(selected.json()["selection"], {"rank": 2, "title": "Film two"})
        self.assertIn("No announcement was sent", selected.json()["message"])
        self.assertNotIn("screening rights", selected.text.casefold())

        latest = self.client.get(f"/events/private/{private_token}/recommendations")
        self.assertEqual(latest.status_code, 200)
        self.assertEqual(latest.json()["selection"], {"rank": 2, "title": "Film two"})

        second_selection = self.client.post(f"/events/private/{private_token}/selection", json={"rank": 1})
        public_selection = self.client.post(f"/events/private/{public_token}/selection", json={"rank": 1})
        self.assertEqual(second_selection.status_code, 409)
        self.assertEqual(public_selection.status_code, 404)
        self.assertEqual(second_selection.json(), {"detail": "A final film has already been selected"})
        self.assertEqual(public_selection.json(), {"detail": "Event not found"})

        with self.session_factory() as db:
            selections = db.scalars(select(Selection)).all()
            self.assertEqual(len(selections), 1)

    def test_selection_requires_a_complete_shortlist_and_rejects_invalid_body(self) -> None:
        _, private_token = self.create_event()
        unavailable = self.client.post(f"/events/private/{private_token}/selection", json={"rank": 1})
        invalid = self.client.post(f"/events/private/{private_token}/selection", json={"rank": 4})

        self.assertEqual(unavailable.status_code, 409)
        self.assertEqual(invalid.status_code, 422)
        self.assertEqual(invalid.json(), {"detail": "Invalid selection request"})

    def test_recommendation_request_rejects_unknown_body_fields(self) -> None:
        _, private_token = self.create_event()
        response = self.client.post(
            f"/events/private/{private_token}/recommendations",
            json={"unexpected": "input"},
        )
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json(), {"detail": "Invalid recommendation request"})
        self.assertNotIn("unexpected", response.text)

    def test_management_recommendation_request_requires_json(self) -> None:
        _, private_token = self.create_event()
        response = self.client.post(f"/events/private/{private_token}/recommendations")

        self.assertEqual(response.status_code, 415)
        self.assertEqual(response.json(), {"detail": "JSON is required"})

    def test_recommendation_routes_require_the_private_management_token(self) -> None:
        public_token, _ = self.create_event()

        read = self.client.get(f"/events/private/{public_token}/recommendations")
        request = self.client.post(f"/events/private/{public_token}/recommendations", json={})

        self.assertEqual(read.status_code, 404)
        self.assertEqual(request.status_code, 404)
        self.assertEqual(read.json(), request.json())

    def test_retry_failure_creates_new_unavailable_run_instead_of_serving_stale_candidates(self) -> None:
        public_token, private_token = self.create_event()
        self.register(public_token, "Maya", [{"title_text": "Moonlight"}])

        success_adapter = DeterministicFakeQlooAdapter(
            resolutions={"moonlight": ResolvedTitle("moonlight", "Moonlight")},
            rankings={
                "moonlight": (
                    provider_candidate("film-1", "Film one"),
                    provider_candidate("film-2", "Film two"),
                    provider_candidate("film-3", "Film three"),
                )
            },
        )
        main_module.app.dependency_overrides[main_module.get_recommendation_service] = lambda: RecommendationService(success_adapter)
        first = self.client.post(f"/events/private/{private_token}/recommendations", json={})
        self.assertEqual(first.status_code, 200)
        self.assertEqual(first.json()["status"], "succeeded")

        failure_adapter = DeterministicFakeQlooAdapter(fail_with=QlooError("private provider detail"))
        main_module.app.dependency_overrides[main_module.get_recommendation_service] = lambda: RecommendationService(failure_adapter)
        second = self.client.post(f"/events/private/{private_token}/recommendations", json={})
        self.assertEqual(second.status_code, 200)
        self.assertEqual(second.json()["status"], "unavailable")
        self.assertIsNone(second.json()["top_pick"])
        self.assertEqual(second.json()["alternatives"], [])

        latest = self.client.get(f"/events/private/{private_token}/recommendations")
        self.assertEqual(latest.status_code, 200)
        self.assertEqual(latest.json()["status"], "unavailable")
        self.assertIsNone(latest.json()["top_pick"])

        with self.session_factory() as db:
            event_id = db.scalar(
                select(EventAccessToken.event_id).where(
                    EventAccessToken.token_digest == digest_token(private_token, "private_management")
                )
            )
            runs = db.scalars(
                select(RecommendationRun)
                .where(RecommendationRun.event_id == event_id)
                .order_by(RecommendationRun.requested_at)
            ).all()
            self.assertEqual(len(runs), 2)
            self.assertEqual([len(run.candidates) for run in runs], [3, 0])


if __name__ == "__main__":
    unittest.main()
