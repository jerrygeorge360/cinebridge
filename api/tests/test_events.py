from __future__ import annotations

import os
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import urlparse

from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.main as main_module
from app.database import get_db
from app.models import Base, EventAccessToken
from app.rate_limit import RateLimiter


class EventFoundationTests(unittest.TestCase):
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
        cls.created = response.json()
        cls.public_token = urlparse(cls.created["public_registration_url"]).path.rsplit("/", 1)[-1]
        cls.private_token = urlparse(cls.created["private_management_url"]).path.rsplit("/", 1)[-1]

    @classmethod
    def tearDownClass(cls) -> None:
        main_module.app.dependency_overrides.clear()
        cls.engine.dispose()

    @classmethod
    def _reset_limiter(cls) -> None:
        main_module.rate_limiter = RateLimiter()

    def setUp(self) -> None:
        self._reset_limiter()

    def test_creation_returns_two_distinct_links_but_not_raw_token_fields(self) -> None:
        self.assertNotIn("public_token", self.created)
        self.assertNotIn("private_token", self.created)
        self.assertNotEqual(self.public_token, self.private_token)
        self.assertGreaterEqual(len(self.public_token), 43)
        self.assertGreaterEqual(len(self.private_token), 43)
        self.assertEqual(urlparse(self.created["public_registration_url"]).netloc, "cinebridge.test")
        self.assertEqual(urlparse(self.created["private_management_url"]).netloc, "cinebridge.test")

        with self.session_factory() as db:
            rows = db.query(EventAccessToken).all()
            self.assertEqual({row.purpose for row in rows}, {"public_registration", "private_management"})
            self.assertEqual(len({row.token_digest for row in rows}), 2)
            for row in rows:
                self.assertNotIn(self.public_token, row.token_digest)
                self.assertNotIn(self.private_token, row.token_digest)

    def test_public_scope_returns_only_shareable_event_metadata(self) -> None:
        response = self.client.get(f"/events/public/{self.public_token}")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["name"], "Sunday Film Club")
        self.assertNotIn("private_management_url", body)
        self.assertNotIn("registered_count", body)
        self.assertNotIn(self.private_token, response.text)
        self.assertEqual(response.headers["cache-control"], "no-store")
        self.assertEqual(response.headers["referrer-policy"], "no-referrer")

    def test_web_origin_can_preflight_event_creation(self) -> None:
        response = self.client.options(
            "/events",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["access-control-allow-origin"], "http://localhost:3000")
        self.assertIn("POST", response.headers["access-control-allow-methods"])

    def test_private_scope_returns_aggregate_overview_without_public_token(self) -> None:
        response = self.client.get(f"/events/private/{self.private_token}")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json()["registered_count"],
            0,
        )
        self.assertNotIn(self.public_token, response.text)
        self.assertNotIn("attendees", response.json())

    def test_tokens_cannot_cross_authorization_scopes(self) -> None:
        public_with_private = self.client.get(f"/events/public/{self.private_token}")
        private_with_public = self.client.get(f"/events/private/{self.public_token}")
        self.assertEqual(public_with_private.status_code, 404)
        self.assertEqual(private_with_public.status_code, 404)
        self.assertEqual(public_with_private.json(), private_with_public.json())

    def test_invalid_event_input_is_rejected_without_echoing_input(self) -> None:
        response = self.client.post(
            "/events",
            json={
                "name": "\u0000private-name",
                "theme": "Theme",
                "screening_date": date.today().isoformat(),
                "essential_details": "Details",
                "unexpected": "do not accept",
            },
        )
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json(), {"detail": "Invalid event details"})
        self.assertNotIn("private-name", response.text)
        self.assertNotIn("unexpected", response.text)

    def test_event_creation_requires_json_and_bounded_body(self) -> None:
        non_json = self.client.post("/events", content="name=event")
        self.assertEqual(non_json.status_code, 415)

        oversized = self.client.post(
            "/events",
            content=("{" + '"name":"x","theme":"y","screening_date":"2099-01-01","essential_details":"' + "x" * (16 * 1024) + '"}').encode(),
            headers={"content-type": "application/json"},
        )
        self.assertEqual(oversized.status_code, 413)

    def test_event_creation_is_rate_limited_per_source(self) -> None:
        for index in range(5):
            response = self.client.post(
                "/events",
                json={
                    "name": f"Rate limited event {index}",
                    "theme": "A bounded test",
                    "screening_date": (date.today() + timedelta(days=30 + index)).isoformat(),
                    "essential_details": "Details",
                },
            )
            self.assertEqual(response.status_code, 201)
        response = self.client.post(
            "/events",
            json={
                "name": "Rate limited event six",
                "theme": "A bounded test",
                "screening_date": (date.today() + timedelta(days=60)).isoformat(),
                "essential_details": "Details",
            },
        )
        self.assertEqual(response.status_code, 429)
        self.assertEqual(response.json(), {"detail": "Too many requests"})
        self.assertIn("retry-after", response.headers)

    def test_initial_migration_creates_all_domain_tables_and_enables_foreign_keys(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database_path = Path(directory) / "fresh.db"
            original_url = os.environ.get("DATABASE_URL")
            os.environ["DATABASE_URL"] = f"sqlite:///{database_path}"
            try:
                config = Config(str(Path(__file__).parents[1] / "alembic.ini"))
                command.upgrade(config, "head")
            finally:
                if original_url is None:
                    os.environ.pop("DATABASE_URL", None)
                else:
                    os.environ["DATABASE_URL"] = original_url

            validation_engine = create_engine(f"sqlite:///{database_path}")
            try:
                inspector = inspect(validation_engine)
                self.assertEqual(
                    set(inspector.get_table_names()) - {"alembic_version"},
                    {
                        "events",
                        "event_access_tokens",
                        "attendees",
                        "attendee_preferences",
                        "recommendation_runs",
                        "recommendation_candidates",
                        "selections",
                    },
                )
                with validation_engine.connect() as connection:
                    self.assertEqual(connection.execute(text("PRAGMA foreign_keys")).scalar(), 1)
            finally:
                validation_engine.dispose()


if __name__ == "__main__":
    unittest.main()
