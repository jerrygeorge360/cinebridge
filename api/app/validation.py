from __future__ import annotations

import re
import unicodedata
from datetime import date, datetime, timezone
from typing import Literal

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator, model_validator


_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def normalize_text(value: object, *, field_name: str, maximum: int) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be text")
    normalized = unicodedata.normalize("NFC", value.strip())
    if not normalized:
        raise ValueError(f"{field_name} is required")
    if any(unicodedata.category(character) == "Cc" for character in normalized):
        raise ValueError(f"{field_name} contains unsupported characters")
    if len(normalized) > maximum:
        raise ValueError(f"{field_name} is too long")
    return normalized


def normalize_optional_text(value: object, *, field_name: str, maximum: int) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be text")
    normalized = unicodedata.normalize("NFC", value.strip())
    if any(unicodedata.category(character) == "Cc" for character in normalized):
        raise ValueError(f"{field_name} contains unsupported characters")
    if len(normalized) > maximum:
        raise ValueError(f"{field_name} is too long")
    return normalized or None


class EventCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(max_length=120)
    theme: str = Field(max_length=120)
    screening_date: date
    essential_details: str = Field(max_length=1000)

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        return normalize_text(value, field_name="name", maximum=120)

    @field_validator("theme")
    @classmethod
    def validate_theme(cls, value: str) -> str:
        return normalize_text(value, field_name="theme", maximum=120)

    @field_validator("essential_details")
    @classmethod
    def validate_essential_details(cls, value: str) -> str:
        return normalize_text(value, field_name="essential_details", maximum=1000)

    @field_validator("screening_date", mode="before")
    @classmethod
    def validate_screening_date(cls, value: object) -> date:
        if not isinstance(value, str) or not _ISO_DATE.fullmatch(value):
            raise ValueError("screening_date must use YYYY-MM-DD")
        try:
            parsed = date.fromisoformat(value)
        except ValueError as error:
            raise ValueError("screening_date must be a real calendar date") from error
        if parsed <= datetime.now(timezone.utc).date():
            raise ValueError("screening_date must be in the future")
        return parsed


class AttendeePreferenceCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title_text: str = Field(max_length=160)
    tmdb_id: int | None = Field(default=None, ge=1)
    media_type: Literal["movie", "tv"] | None = None
    release_date: str | None = Field(default=None, max_length=10)
    poster_path: str | None = Field(default=None, max_length=500)
    enjoyed_text: str | None = Field(default=None, max_length=500)

    @field_validator("title_text", mode="before")
    @classmethod
    def validate_title_text(cls, value: object) -> str:
        if value is None:
            raise ValueError("title_text must be text")
        return normalize_optional_text(value, field_name="title_text", maximum=160) or ""

    @field_validator("enjoyed_text", mode="before")
    @classmethod
    def validate_enjoyed_text(cls, value: object) -> str | None:
        return normalize_optional_text(value, field_name="enjoyed_text", maximum=500)

    @field_validator("release_date", mode="before")
    @classmethod
    def validate_release_date(cls, value: object) -> str | None:
        value = normalize_optional_text(value, field_name="release_date", maximum=10)
        if value is not None and (not _ISO_DATE.fullmatch(value)):
            raise ValueError("release_date must use YYYY-MM-DD")
        if value is not None:
            try:
                date.fromisoformat(value)
            except ValueError as error:
                raise ValueError("release_date must be a real calendar date") from error
        return value

    @field_validator("poster_path", mode="before")
    @classmethod
    def validate_poster_path(cls, value: object) -> str | None:
        value = normalize_optional_text(value, field_name="poster_path", maximum=500)
        if value is not None and not value.startswith("/"):
            raise ValueError("poster_path must be a TMDB image path")
        return value

    @model_validator(mode="after")
    def validate_used_slot(self) -> "AttendeePreferenceCreate":
        if not self.title_text and self.enjoyed_text:
            raise ValueError("A favorite title is required when an explanation is provided")
        selected_fields = (self.tmdb_id, self.media_type)
        if any(value is not None for value in selected_fields) and any(
            value is None for value in selected_fields
        ):
            raise ValueError("A selected title requires its TMDB id and media type")
        return self


class TitleSearchItemResponse(BaseModel):
    tmdb_id: int
    media_type: Literal["movie", "tv"]
    title: str
    release_date: str | None = None
    release_year: int | None = None
    poster_path: str | None = None
    poster_url: str | None = None


class TitleSearchResponse(BaseModel):
    results: list[TitleSearchItemResponse] = Field(default_factory=list)
    suggestion: str | None = None


class AttendeeRegistrationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    display_name: str = Field(max_length=80)
    preferences: list[AttendeePreferenceCreate] = Field(
        default_factory=list,
        max_length=3,
        validation_alias=AliasChoices("preferences", "attendee_preferences"),
    )

    @field_validator("display_name")
    @classmethod
    def validate_display_name(cls, value: str) -> str:
        return normalize_text(value, field_name="display_name", maximum=80)


class RegistrationResponse(BaseModel):
    message: str


class EventPublicResponse(BaseModel):
    name: str
    theme: str
    screening_date: date
    essential_details: str


class EventCreationResponse(EventPublicResponse):
    public_registration_url: str
    private_management_url: str


class SelectionSummaryResponse(BaseModel):
    rank: Literal[1, 2, 3]
    title: str


class PrivateEventResponse(EventPublicResponse):
    registered_count: int
    usable_preference_count: int
    represented_attendee_count: int
    selection: SelectionSummaryResponse | None = None


class RecommendationCandidateResponse(BaseModel):
    rank: Literal[1, 2, 3]
    title: str
    release_year: int | None = None
    runtime_minutes: int | None = None
    content_rating: str | None = None
    languages: list[str] = Field(default_factory=list)
    fit_explanation: str
    warning_text: str
    poster_url: str | None = None


class ProgrammingSourceResponse(BaseModel):
    title: str
    url: str
    date: str | None = None


class ProgrammingToolObservationResponse(BaseModel):
    name: Literal["inspect_audience_coverage", "inspect_candidate_evidence", "inspect_qloo_entity"]
    arguments: dict[str, object] = Field(default_factory=dict)
    observation: dict[str, object] | None = None
    status: Literal["executed", "rejected"] = "executed"


class ProgrammingBriefResponse(BaseModel):
    status: Literal["ready", "clarification_needed", "unavailable"]
    summary: str
    tradeoffs: list[str] = Field(default_factory=list)
    uncertainty: str
    sources: list[ProgrammingSourceResponse] = Field(default_factory=list)
    tools_used: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)
    tool_observations: list[ProgrammingToolObservationResponse] = Field(default_factory=list)
    model_turns: int = Field(default=0, ge=0, le=2)
    agent_activity: Literal["deterministic_only", "agent_requested_shortlist", "agent_checked_shortlist", "agent_no_action", "agent_tool_loop", "agent_provider_unavailable", "agent_rejected_output", "agent_limits_exceeded"] = "deterministic_only"


class RecommendationResponse(BaseModel):
    status: Literal["succeeded", "limited", "unavailable"]
    registered_count: int
    usable_preference_count: int
    represented_attendee_count: int
    warning_code: str | None = None
    warning: str
    message: str
    top_pick: RecommendationCandidateResponse | None = None
    alternatives: list[RecommendationCandidateResponse] = Field(default_factory=list)
    selection: SelectionSummaryResponse | None = None
    programming_brief: ProgrammingBriefResponse | None = None


class RecommendationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SelectionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rank: Literal[1, 2, 3]


class SelectionResponse(BaseModel):
    message: str
    selection: SelectionSummaryResponse


__all__ = [
    "EventCreate",
    "EventCreationResponse",
    "EventPublicResponse",
    "PrivateEventResponse",
    "AttendeePreferenceCreate",
    "AttendeeRegistrationCreate",
    "TitleSearchItemResponse",
    "TitleSearchResponse",
    "RegistrationResponse",
    "normalize_text",
    "normalize_optional_text",
    "RecommendationCandidateResponse",
    "RecommendationRequest",
    "RecommendationResponse",
    "ProgrammingBriefResponse",
    "ProgrammingToolObservationResponse",
    "ProgrammingSourceResponse",
    "SelectionRequest",
    "SelectionResponse",
    "SelectionSummaryResponse",
]
