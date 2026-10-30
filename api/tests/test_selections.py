from __future__ import annotations

import os
import unittest
from datetime import date, timedelta
from urllib.parse import urlparse

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import main as main_module
from app.database import get_db
from app.models import Base, EventAccessToken, Selection
from app.rate_limit import RateLimiter
from app.recommendations import (
    DeterministicFakeQlooAdapter,
    ProviderCandidate,
    RecommendationService,
    ResolvedTitle,
)
from app.security import digest_token


def provider_candidate(entity_id: str, title: str) -> ProviderCandidate:
    return ProviderCandidate(
        entity_id=entity_id,
        title=title,
        release_year=2024,
        runtime_minutes=110,
        content_rating="PG-13",
        languages=("English",),
        media_type="movie",
    )


class SelectionApiTests(unittest.TestCase):
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
        cls.session_factory = sessionmaker(
            bind=cls.engine,
            autoflush=False,
            expire_on_commit=False,
        )

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
                "name": "Selection test event",
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

    def configure_shortlist(self) -> None:
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
        main_module.app.dependency_overrides[main_module.get_recommendation_service] = (
            lambda: RecommendationService(adapter)
        )

    def test_private_organizer_can_select_once_without_public_announcement(self) -> None:
        public_token, private_token = self.create_event()
        self.register(public_token, "Maya", [{"title_text": "Moonlight"}])
        self.configure_shortlist()

        recommendation = self.client.post(f"/events/private/{private_token}/recommendations", json={})
        self.assertEqual(recommendation.status_code, 200, recommendation.text)
        self.assertEqual(recommendation.json()["status"], "succeeded")

        selected = self.client.post(
            f"/events/private/{private_token}/selection",
            json={"rank": 2},
        )
        self.assertEqual(selected.status_code, 200, selected.text)
        self.assertEqual(selected.json()["selection"], {"rank": 2, "title": "Film two"})
        self.assertIn("No announcement was sent", selected.json()["message"])
        self.assertNotIn("screening rights", selected.text.casefold())

        public_attempt = self.client.post(
            f"/events/private/{public_token}/selection",
            json={"rank": 1},
        )
        second_attempt = self.client.post(
            f"/events/private/{private_token}/selection",
            json={"rank": 1},
        )
        self.assertEqual(public_attempt.status_code, 404)
        self.assertEqual(second_attempt.status_code, 409)

        with self.session_factory() as db:
            event_id = db.scalar(
                select(EventAccessToken.event_id).where(
                    EventAccessToken.token_digest
                    == digest_token(private_token, "private_management")
                )
            )
            self.assertEqual(
                len(db.scalars(select(Selection).where(Selection.event_id == event_id)).all()),
                1,
            )

    def test_limited_complete_shortlist_can_be_selected_by_private_token(self) -> None:
        public_token, private_token = self.create_event()
        self.register(public_token, "Supported", [{"title_text": "Moonlight"}])
        self.register(public_token, "No preferences", [])
        self.configure_shortlist()

        recommendation = self.client.post(f"/events/private/{private_token}/recommendations", json={})
        self.assertEqual(recommendation.status_code, 200, recommendation.text)
        self.assertEqual(recommendation.json()["status"], "limited")
        self.assertEqual(len(recommendation.json()["alternatives"]), 2)

        selected = self.client.post(
            f"/events/private/{private_token}/selection",
            json={"rank": 1},
        )
        self.assertEqual(selected.status_code, 200, selected.text)
        self.assertEqual(selected.json()["selection"], {"rank": 1, "title": "Film one"})

    def test_selection_requires_a_complete_private_shortlist(self) -> None:
        public_token, private_token = self.create_event()

        unavailable = self.client.post(
            f"/events/private/{private_token}/selection",
            json={"rank": 1},
        )
        invalid = self.client.post(
            f"/events/private/{private_token}/selection",
            json={"rank": 4},
        )
        public_attempt = self.client.post(
            f"/events/private/{public_token}/selection",
            json={"rank": 1},
        )

        self.assertEqual(unavailable.status_code, 409)
        self.assertEqual(invalid.status_code, 422)
        self.assertEqual(invalid.json(), {"detail": "Invalid selection request"})
        self.assertEqual(public_attempt.status_code, 404)

    def test_selection_requires_json(self) -> None:
        _, private_token = self.create_event()

        response = self.client.post(f"/events/private/{private_token}/selection")

        self.assertEqual(response.status_code, 415)
        self.assertEqual(response.json(), {"detail": "JSON is required"})


if __name__ == "__main__":
    unittest.main()
