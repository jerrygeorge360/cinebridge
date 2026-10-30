from __future__ import annotations

import os
import json
import unittest
from datetime import date, timedelta
from urllib.parse import urlparse
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.main as main_module
from app.database import get_db
from app.models import Attendee, AttendeePreference, Base
from app.rate_limit import RateLimiter
from app.tmdb import TmdbClient
from app.recommendations import (
    DeterministicFakeQlooAdapter,
    RecommendationEngine,
    RecommendationService,
    ResolvedTitle,
)


class StubResponse:
    def __init__(self, payload: object) -> None:
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")


class AttendeeRegistrationTests(unittest.TestCase):
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
        cls._reset_limiter()
        response = cls.client.post(
            "/events",
            json={
                "name": "Sunday Film Club",
                "theme": "Tender science fiction",
                "screening_date": (date.today() + timedelta(days=14)).isoformat(),
                "essential_details": "Doors at 18:30 · step-free venue",
            },
        )
        assert response.status_code == 201, response.text
        created = response.json()
        cls.public_token = urlparse(created["public_registration_url"]).path.rsplit("/", 1)[-1]
        cls.private_token = urlparse(created["private_management_url"]).path.rsplit("/", 1)[-1]

    @classmethod
    def tearDownClass(cls) -> None:
        main_module.app.dependency_overrides.clear()
        cls.engine.dispose()

    @classmethod
    def _reset_limiter(cls) -> None:
        main_module.rate_limiter = RateLimiter()

    def setUp(self) -> None:
        self._reset_limiter()

    def register(self, **overrides: object):
        payload: dict[str, object] = {
            "display_name": "Maya",
            "preferences": [],
        }
        payload.update(overrides)
        return self.client.post(
            f"/events/public/{self.public_token}/registrations",
            json=payload,
        )

    def test_blank_preferences_are_valid_and_success_is_generic(self) -> None:
        response = self.register(display_name="  Maya  ", preferences=[])

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json(), {"message": "Registration received"})
        self.assertNotIn("Maya", response.text)
        self.assertNotIn("preferences", response.text)

        with self.session_factory() as db:
            attendee = db.scalar(select(Attendee).where(Attendee.display_name == "Maya"))
            self.assertIsNotNone(attendee)
            self.assertEqual(attendee.preferences, [])

    def test_attendee_preferences_alias_is_accepted_without_changing_public_response(self) -> None:
        response = self.client.post(
            f"/events/public/{self.public_token}/registrations",
            json={
                "display_name": "Alias guest",
                "attendee_preferences": [
                    {"title_text": "Past Lives", "enjoyed_text": "Tender detail"}
                ],
            },
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json(), {"message": "Registration received"})
        self.assertNotIn("Past Lives", response.text)

    def test_preferences_are_stored_privately_and_not_returned_by_public_reads(self) -> None:
        response = self.register(
            preferences=[
                {"title_text": "  Moonlight ", "enjoyed_text": "Quiet, humane pacing"},
                {"title_text": "", "enjoyed_text": ""},
                {"title_text": "Arrival", "enjoyed_text": "Ideas with emotional weight"},
            ]
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(set(response.json()), {"message"})

        public_read = self.client.get(f"/events/public/{self.public_token}")
        private_read = self.client.get(f"/events/private/{self.private_token}")
        for read in (public_read, private_read):
            self.assertEqual(read.status_code, 200)
            self.assertNotIn("Maya", read.text)
            self.assertNotIn("Moonlight", read.text)
            self.assertNotIn("Arrival", read.text)
            self.assertNotIn("Quiet, humane pacing", read.text)
            self.assertNotIn("attendees", read.json())
            self.assertNotIn("preferences", read.text)

        with self.session_factory() as db:
            rows = db.scalars(
                select(AttendeePreference)
                .join(Attendee, Attendee.id == AttendeePreference.attendee_id)
                .where(Attendee.display_name == "Maya")
                .order_by(AttendeePreference.position)
            ).all()
            self.assertEqual([(row.position, row.title_text) for row in rows], [(1, "Moonlight"), (3, "Arrival")])
            self.assertEqual(rows[0].enjoyed_text, "Quiet, humane pacing")

    def test_selected_tmdb_preference_is_canonical_and_legacy_text_remains_supported(self) -> None:
        original_client = main_module.tmdb_client
        main_module.tmdb_client = TmdbClient(
            api_key="test",
            opener=lambda *_args, **_kwargs: StubResponse(
                {"id": 1429, "name": "Attack on Titan", "first_air_date": "2013-04-07", "poster_path": "/authoritative.jpg"}
            ),
        )
        try:
            response = self.register(
                display_name="Canonical guest",
                preferences=[
                    {
                        "title_text": "Attack on Titan",
                        "tmdb_id": 1429,
                        "media_type": "tv",
                        "release_date": "2013-04-07",
                        "poster_path": "/untrusted.jpg",
                        "enjoyed_text": "The momentum",
                    },
                    {"title_text": "A legacy title"},
                ],
            )
        finally:
            main_module.tmdb_client = original_client
        self.assertEqual(response.status_code, 201)
        with self.session_factory() as db:
            rows = db.scalars(
                select(AttendeePreference)
                .join(Attendee, Attendee.id == AttendeePreference.attendee_id)
                .where(Attendee.display_name == "Canonical guest")
                .order_by(AttendeePreference.position)
            ).all()
            self.assertEqual(rows[0].tmdb_id, 1429)
            self.assertEqual(rows[0].media_type, "tv")
            self.assertEqual(rows[0].qloo_resolution_status, "pending")
            self.assertEqual(rows[0].poster_path, "/authoritative.jpg")
            self.assertIsNone(rows[1].tmdb_id)
            self.assertEqual(rows[1].qloo_resolution_status, "legacy")

    def test_tampered_tmdb_selection_is_rejected(self) -> None:
        original_client = main_module.tmdb_client
        main_module.tmdb_client = TmdbClient(
            api_key="test",
            opener=lambda *_args, **_kwargs: StubResponse(
                {"id": 1429, "name": "Attack on Titan", "first_air_date": "2013-04-07"}
            ),
        )
        try:
            response = self.register(
                preferences=[
                    {"title_text": "An unrelated title", "tmdb_id": 1429, "media_type": "tv"}
                ]
            )
        finally:
            main_module.tmdb_client = original_client
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json(), {"detail": "Selected title could not be verified"})

    def test_title_search_returns_selectable_results_and_alias_suggestion(self) -> None:
        original_client = main_module.tmdb_client
        main_module.tmdb_client = TmdbClient(
            api_key="test",
            opener=lambda *_args, **_kwargs: StubResponse(
                {"results": [{"id": 1429, "media_type": "tv", "name": "Attack on Titan", "first_air_date": "2013-04-07", "poster_path": "/aot.jpg"}]}
            ),
        )
        try:
            response = self.client.get(f"/events/public/{self.public_token}/title-search?q=AOT")
        finally:
            main_module.tmdb_client = original_client
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["suggestion"], "Attack on Titan")
        self.assertEqual(response.json()["results"][0]["tmdb_id"], 1429)
        self.assertEqual(response.json()["results"][0]["poster_url"], "https://image.tmdb.org/t/p/w342/aot.jpg")

    def test_title_search_upstream_failure_is_explicit(self) -> None:
        original_client = main_module.tmdb_client
        main_module.tmdb_client = TmdbClient(api_key="test", opener=lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("down")))
        try:
            response = self.client.get(f"/events/public/{self.public_token}/title-search?q=Arrival")
        finally:
            main_module.tmdb_client = original_client
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json(), {"detail": "Title search is temporarily unavailable"})

    def test_selected_titles_resolve_against_their_tmdb_media_type_and_legacy_rows_are_unchanged(self) -> None:
        class RecordingAdapter(DeterministicFakeQlooAdapter):
            def __init__(self) -> None:
                super().__init__(resolutions={})
                self.calls: list[tuple[str, str | None, str | None]] = []

            def resolve_title(self, title_text, *, media_type=None, release_date=None):
                self.calls.append((title_text, media_type, release_date))
                if media_type == "tv":
                    return ResolvedTitle("tv-code-geass", title_text, "urn:entity:tv_show")
                return None

        adapter = RecordingAdapter()
        service = RecommendationService(adapter)
        with self.session_factory() as db:
            attendee = Attendee(
                id=str(uuid4()), event_id=self._event_id(db), display_name="Resolver test", created_at=date.today()
            )
            attendee.preferences.extend([
                AttendeePreference(
                    id=str(uuid4()), position=1, title_text="Code Geass: Rozé of the Recapture",
                    tmdb_id=255107, media_type="tv", release_date="2024-06-21",
                    qloo_resolution_status="pending", created_at=date.today(),
                ),
                AttendeePreference(
                    id=str(uuid4()), position=2, title_text="Historical free text",
                    qloo_resolution_status="legacy", created_at=date.today(),
                ),
            ])
            db.add(attendee)
            db.commit()
            main_module._resolve_selected_preferences_for_qloo(db, attendee.event_id, service)
            db.commit()
            rows = db.scalars(select(AttendeePreference).where(AttendeePreference.attendee_id == attendee.id).order_by(AttendeePreference.position)).all()

        self.assertEqual(adapter.calls, [("Code Geass: Rozé of the Recapture", "tv", "2024-06-21")])
        self.assertEqual(rows[0].qloo_entity_id, "tv-code-geass")
        self.assertEqual(rows[0].qloo_entity_type, "urn:entity:tv_show")
        self.assertEqual(rows[0].qloo_resolution_status, "resolved")
        self.assertIsNone(rows[0].qloo_resolution_reason)
        self.assertEqual(rows[1].qloo_resolution_status, "legacy")
        self.assertIsNone(rows[1].qloo_entity_id)

    def test_unmatched_selected_title_is_explicitly_unresolved(self) -> None:
        service = RecommendationService(DeterministicFakeQlooAdapter(resolutions={}))
        with self.session_factory() as db:
            attendee = Attendee(
                id=str(uuid4()), event_id=self._event_id(db), display_name="Unresolved test", created_at=date.today()
            )
            attendee.preferences.append(AttendeePreference(
                id=str(uuid4()), position=1, title_text="No reliable match", tmdb_id=1,
                media_type="movie", release_date="2025-01-01", qloo_resolution_status="pending", created_at=date.today(),
            ))
            db.add(attendee)
            db.commit()
            main_module._resolve_selected_preferences_for_qloo(db, attendee.event_id, service)
            db.commit()
            preference = db.scalar(select(AttendeePreference).where(AttendeePreference.attendee_id == attendee.id))

        self.assertEqual(preference.qloo_resolution_status, "unresolved")
        self.assertIn("movie entity", preference.qloo_resolution_reason)

    def _event_id(self, db):
        return db.scalar(select(Attendee.event_id).limit(1))

    def test_display_name_title_count_and_content_limits_are_rejected(self) -> None:
        cases = [
            ({"display_name": "   "}, "Invalid registration details"),
            ({"display_name": "x" * 81}, "Invalid registration details"),
            ({"preferences": [{"title_text": "x" * 161}]}, "Invalid registration details"),
            ({"preferences": [{"title_text": None}]}, "Invalid registration details"),
            ({"preferences": [{"title_text": "Title", "enjoyed_text": "x" * 501}]}, "Invalid registration details"),
            (
                {
                    "preferences": [
                        {"title_text": "One"},
                        {"title_text": "Two"},
                        {"title_text": "Three"},
                        {"title_text": "Four"},
                    ]
                },
                "Invalid registration details",
            ),
            ({"display_name": "bad\u0000name"}, "Invalid registration details"),
        ]
        for overrides, expected_detail in cases:
            with self.subTest(overrides=overrides):
                response = self.register(**overrides)
                self.assertEqual(response.status_code, 422)
                self.assertEqual(response.json(), {"detail": expected_detail})
                self.assertNotIn("bad", response.text)

    def test_registration_requires_json_and_bounded_body(self) -> None:
        non_json = self.client.post(
            f"/events/public/{self.public_token}/registrations",
            content="display_name=Maya",
        )
        self.assertEqual(non_json.status_code, 415)

        oversized = self.client.post(
            f"/events/public/{self.public_token}/registrations",
            content=("{" + '"display_name":"Maya","preferences":[],' + '"extra":"' + "x" * (16 * 1024) + '"}').encode(),
            headers={"content-type": "application/json"},
        )
        self.assertEqual(oversized.status_code, 413)

    def test_public_registration_is_rate_limited_per_source_and_event(self) -> None:
        for index in range(10):
            response = self.register(display_name=f"Guest {index}")
            self.assertEqual(response.status_code, 201)

        response = self.register(display_name="Guest eleven")
        self.assertEqual(response.status_code, 429)
        self.assertEqual(response.json(), {"detail": "Too many requests"})
        self.assertIn("retry-after", response.headers)

    def test_private_or_invalid_tokens_cannot_create_public_registrations(self) -> None:
        private_response = self.client.post(
            f"/events/public/{self.private_token}/registrations",
            json={"display_name": "Maya", "preferences": []},
        )
        invalid_response = self.client.post(
            "/events/public/not-a-real-token/registrations",
            json={"display_name": "Maya", "preferences": []},
        )
        self.assertEqual(private_response.status_code, 404)
        self.assertEqual(invalid_response.status_code, 404)
        self.assertEqual(private_response.json(), invalid_response.json())


if __name__ == "__main__":
    unittest.main()
