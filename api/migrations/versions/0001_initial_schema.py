"""Create the initial CineBridge domain schema.

Revision ID: 0001_initial_schema
Revises:
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "events",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("theme", sa.String(length=120), nullable=False),
        sa.Column("screening_date", sa.Date(), nullable=False),
        sa.Column("essential_details", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("length(name) BETWEEN 1 AND 120", name="ck_events_name_length"),
        sa.CheckConstraint("length(theme) BETWEEN 1 AND 120", name="ck_events_theme_length"),
        sa.CheckConstraint(
            "length(essential_details) BETWEEN 1 AND 1000",
            name="ck_events_details_length",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_events_screening_date", "events", ["screening_date"])

    op.create_table(
        "event_access_tokens",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("event_id", sa.String(length=36), nullable=False),
        sa.Column("purpose", sa.String(length=32), nullable=False),
        sa.Column("token_digest", sa.String(length=64), nullable=False),
        sa.Column("digest_version", sa.String(length=16), nullable=False),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "purpose IN ('public_registration', 'private_management')",
            name="ck_event_access_tokens_purpose",
        ),
        sa.ForeignKeyConstraint(["event_id"], ["events.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_digest", name="uq_event_access_tokens_digest"),
    )
    op.create_index("ix_event_access_tokens_event_id", "event_access_tokens", ["event_id"])
    op.create_index(
        "uq_event_access_tokens_active_purpose",
        "event_access_tokens",
        ["event_id", "purpose"],
        unique=True,
        sqlite_where=sa.text("revoked_at IS NULL"),
    )

    op.create_table(
        "attendees",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("event_id", sa.String(length=36), nullable=False),
        sa.Column("display_name", sa.String(length=80), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["event_id"], ["events.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_attendees_event_id", "attendees", ["event_id"])

    op.create_table(
        "attendee_preferences",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("attendee_id", sa.String(length=36), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("title_text", sa.String(length=160), nullable=False),
        sa.Column("enjoyed_text", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("position BETWEEN 1 AND 3", name="ck_attendee_preferences_position"),
        sa.ForeignKeyConstraint(["attendee_id"], ["attendees.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("attendee_id", "position", name="uq_attendee_preferences_slot"),
    )
    op.create_index(
        "ix_attendee_preferences_attendee_id", "attendee_preferences", ["attendee_id"]
    )

    op.create_table(
        "recommendation_runs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("event_id", sa.String(length=36), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("registered_count", sa.Integer(), nullable=False),
        sa.Column("usable_preference_count", sa.Integer(), nullable=False),
        sa.Column("represented_attendee_count", sa.Integer(), nullable=False),
        sa.Column("warning_code", sa.String(length=64), nullable=True),
        sa.Column("failure_code", sa.String(length=64), nullable=True),
        sa.Column("algorithm_version", sa.String(length=32), nullable=False),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('succeeded', 'limited', 'unavailable')",
            name="ck_recommendation_runs_status",
        ),
        sa.CheckConstraint("registered_count >= 0", name="ck_recommendation_runs_registered_count"),
        sa.CheckConstraint(
            "usable_preference_count >= 0",
            name="ck_recommendation_runs_usable_preference_count",
        ),
        sa.CheckConstraint(
            "represented_attendee_count >= 0",
            name="ck_recommendation_runs_represented_attendee_count",
        ),
        sa.ForeignKeyConstraint(["event_id"], ["events.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_recommendation_runs_event_id", "recommendation_runs", ["event_id"])

    op.create_table(
        "recommendation_candidates",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("run_id", sa.String(length=36), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("provider_entity_id", sa.String(length=160), nullable=True),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("release_year", sa.Integer(), nullable=True),
        sa.Column("runtime_minutes", sa.Integer(), nullable=True),
        sa.Column("content_rating", sa.String(length=32), nullable=True),
        sa.Column("languages", sa.String(length=500), nullable=True),
        sa.Column("fit_explanation", sa.String(length=1000), nullable=False),
        sa.Column("warning_text", sa.String(length=500), nullable=True),
        sa.CheckConstraint("rank BETWEEN 1 AND 3", name="ck_recommendation_candidates_rank"),
        sa.ForeignKeyConstraint(["run_id"], ["recommendation_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_id", "rank", name="uq_recommendation_candidates_rank"),
    )
    op.create_index(
        "ix_recommendation_candidates_run_id_rank",
        "recommendation_candidates",
        ["run_id", "rank"],
    )

    op.create_table(
        "selections",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("event_id", sa.String(length=36), nullable=False),
        sa.Column("run_id", sa.String(length=36), nullable=False),
        sa.Column("candidate_id", sa.String(length=36), nullable=False),
        sa.Column("selected_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["candidate_id"], ["recommendation_candidates.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["event_id"], ["events.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["run_id"], ["recommendation_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("event_id", name="uq_selections_event_id"),
    )
    op.create_index("ix_selections_event_id", "selections", ["event_id"])


def downgrade() -> None:
    op.drop_index("ix_selections_event_id", table_name="selections")
    op.drop_table("selections")
    op.drop_index("ix_recommendation_candidates_run_id_rank", table_name="recommendation_candidates")
    op.drop_table("recommendation_candidates")
    op.drop_index("ix_recommendation_runs_event_id", table_name="recommendation_runs")
    op.drop_table("recommendation_runs")
    op.drop_index("ix_attendee_preferences_attendee_id", table_name="attendee_preferences")
    op.drop_table("attendee_preferences")
    op.drop_index("ix_attendees_event_id", table_name="attendees")
    op.drop_table("attendees")
    op.drop_index("uq_event_access_tokens_active_purpose", table_name="event_access_tokens")
    op.drop_index("ix_event_access_tokens_event_id", table_name="event_access_tokens")
    op.drop_table("event_access_tokens")
    op.drop_index("ix_events_screening_date", table_name="events")
    op.drop_table("events")
