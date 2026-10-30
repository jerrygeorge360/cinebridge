from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Event(Base):
    __tablename__ = "events"
    __table_args__ = (
        CheckConstraint("length(name) BETWEEN 1 AND 120", name="ck_events_name_length"),
        CheckConstraint("length(theme) BETWEEN 1 AND 120", name="ck_events_theme_length"),
        CheckConstraint(
            "length(essential_details) BETWEEN 1 AND 1000",
            name="ck_events_details_length",
        ),
        Index("ix_events_screening_date", "screening_date"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    theme: Mapped[str] = mapped_column(String(120), nullable=False)
    screening_date: Mapped[date] = mapped_column(Date, nullable=False)
    essential_details: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    access_tokens: Mapped[list[EventAccessToken]] = relationship(
        back_populates="event", cascade="all, delete-orphan"
    )
    attendees: Mapped[list[Attendee]] = relationship(
        back_populates="event", cascade="all, delete-orphan"
    )
    recommendation_runs: Mapped[list[RecommendationRun]] = relationship(
        back_populates="event", cascade="all, delete-orphan"
    )
    selection: Mapped[Selection | None] = relationship(
        back_populates="event", uselist=False, cascade="all, delete-orphan"
    )


class EventAccessToken(Base):
    __tablename__ = "event_access_tokens"
    __table_args__ = (
        CheckConstraint(
            "purpose IN ('public_registration', 'private_management')",
            name="ck_event_access_tokens_purpose",
        ),
        UniqueConstraint("token_digest", name="uq_event_access_tokens_digest"),
        Index("ix_event_access_tokens_event_id", "event_id"),
        Index(
            "uq_event_access_tokens_active_purpose",
            "event_id",
            "purpose",
            unique=True,
            sqlite_where=text("revoked_at IS NULL"),
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    event_id: Mapped[str] = mapped_column(
        ForeignKey("events.id", ondelete="CASCADE"), nullable=False
    )
    purpose: Mapped[str] = mapped_column(String(32), nullable=False)
    token_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    digest_version: Mapped[str] = mapped_column(String(16), nullable=False)
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    event: Mapped[Event] = relationship(back_populates="access_tokens")


class Attendee(Base):
    __tablename__ = "attendees"
    __table_args__ = (Index("ix_attendees_event_id", "event_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    event_id: Mapped[str] = mapped_column(
        ForeignKey("events.id", ondelete="CASCADE"), nullable=False
    )
    display_name: Mapped[str] = mapped_column(String(80), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    event: Mapped[Event] = relationship(back_populates="attendees")
    preferences: Mapped[list[AttendeePreference]] = relationship(
        back_populates="attendee", cascade="all, delete-orphan"
    )


class AttendeePreference(Base):
    __tablename__ = "attendee_preferences"
    __table_args__ = (
        CheckConstraint("position BETWEEN 1 AND 3", name="ck_attendee_preferences_position"),
        UniqueConstraint("attendee_id", "position", name="uq_attendee_preferences_slot"),
        Index("ix_attendee_preferences_attendee_id", "attendee_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    attendee_id: Mapped[str] = mapped_column(
        ForeignKey("attendees.id", ondelete="CASCADE"), nullable=False
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    title_text: Mapped[str] = mapped_column(String(160), nullable=False)
    # TMDB fields are optional so registrations made before autocomplete remain
    # valid.  A TMDB id is provider-local and is never treated as a Qloo id.
    tmdb_id: Mapped[int | None] = mapped_column(Integer)
    media_type: Mapped[str | None] = mapped_column(String(12))
    release_date: Mapped[str | None] = mapped_column(String(10))
    poster_path: Mapped[str | None] = mapped_column(String(500))
    qloo_entity_id: Mapped[str | None] = mapped_column(String(160))
    qloo_entity_type: Mapped[str | None] = mapped_column(String(40))
    qloo_resolution_reason: Mapped[str | None] = mapped_column(String(160))
    qloo_resolution_status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="legacy"
    )
    enjoyed_text: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    attendee: Mapped[Attendee] = relationship(back_populates="preferences")


class RecommendationRun(Base):
    __tablename__ = "recommendation_runs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('succeeded', 'limited', 'unavailable')",
            name="ck_recommendation_runs_status",
        ),
        CheckConstraint("registered_count >= 0", name="ck_recommendation_runs_registered_count"),
        CheckConstraint(
            "usable_preference_count >= 0",
            name="ck_recommendation_runs_usable_preference_count",
        ),
        CheckConstraint(
            "represented_attendee_count >= 0",
            name="ck_recommendation_runs_represented_attendee_count",
        ),
        Index("ix_recommendation_runs_event_id", "event_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    event_id: Mapped[str] = mapped_column(
        ForeignKey("events.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    registered_count: Mapped[int] = mapped_column(Integer, nullable=False)
    usable_preference_count: Mapped[int] = mapped_column(Integer, nullable=False)
    represented_attendee_count: Mapped[int] = mapped_column(Integer, nullable=False)
    warning_code: Mapped[str | None] = mapped_column(String(64))
    failure_code: Mapped[str | None] = mapped_column(String(64))
    algorithm_version: Mapped[str] = mapped_column(String(32), nullable=False)
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    programming_brief: Mapped[str | None] = mapped_column(Text)
    agent_tools_used: Mapped[str | None] = mapped_column(String(200))
    agent_input_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    agent_output_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    agent_cost_usd_micros: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    agent_latency_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    event: Mapped[Event] = relationship(back_populates="recommendation_runs")
    candidates: Mapped[list[RecommendationCandidate]] = relationship(
        back_populates="run", cascade="all, delete-orphan"
    )


class RecommendationCandidate(Base):
    __tablename__ = "recommendation_candidates"
    __table_args__ = (
        CheckConstraint("rank BETWEEN 1 AND 3", name="ck_recommendation_candidates_rank"),
        UniqueConstraint("run_id", "rank", name="uq_recommendation_candidates_rank"),
        Index("ix_recommendation_candidates_run_id_rank", "run_id", "rank"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    run_id: Mapped[str] = mapped_column(
        ForeignKey("recommendation_runs.id", ondelete="CASCADE"), nullable=False
    )
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    provider_entity_id: Mapped[str | None] = mapped_column(String(160))
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    release_year: Mapped[int | None] = mapped_column(Integer)
    runtime_minutes: Mapped[int | None] = mapped_column(Integer)
    content_rating: Mapped[str | None] = mapped_column(String(32))
    languages: Mapped[str | None] = mapped_column(String(500))
    fit_explanation: Mapped[str] = mapped_column(String(1000), nullable=False)
    warning_text: Mapped[str | None] = mapped_column(String(500))
    # Backend-only evidence; API response models intentionally omit it.
    contributor_provenance: Mapped[str] = mapped_column(
        Text, nullable=False, default="[]"
    )
    tmdb_id: Mapped[int | None] = mapped_column(Integer)
    poster_path: Mapped[str | None] = mapped_column(String(500))
    poster_looked_up_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    run: Mapped[RecommendationRun] = relationship(back_populates="candidates")


class Selection(Base):
    __tablename__ = "selections"
    __table_args__ = (
        UniqueConstraint("event_id", name="uq_selections_event_id"),
        Index("ix_selections_event_id", "event_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    event_id: Mapped[str] = mapped_column(
        ForeignKey("events.id", ondelete="CASCADE"), nullable=False
    )
    run_id: Mapped[str] = mapped_column(
        ForeignKey("recommendation_runs.id", ondelete="CASCADE"), nullable=False
    )
    candidate_id: Mapped[str] = mapped_column(
        ForeignKey("recommendation_candidates.id", ondelete="CASCADE"), nullable=False
    )
    selected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    event: Mapped[Event] = relationship(back_populates="selection")
