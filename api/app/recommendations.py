from __future__ import annotations

import json
import os
import unicodedata
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date
from typing import Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request as UrlRequest
from urllib.request import urlopen


ALGORITHM_VERSION = "audience-rank-v1"
_ALLOWED_MEDIA_TYPES = {"film", "movie"}
_SELECTED_QLOO_ENTITY_TYPES = {
    "movie": "urn:entity:movie",
    "tv": "urn:entity:tv_show",
}


class QlooError(Exception):
    """An upstream failure that must not be exposed to the organizer."""


@dataclass(frozen=True)
class AudiencePreference:
    title_text: str
    enjoyed_text: str | None = None
    qloo_entity_id: str | None = None
    qloo_title: str | None = None
    # TMDB-backed selections carry canonical media metadata and a separately
    # persisted Qloo resolution.  Legacy free-text preferences leave these
    # fields unset and retain their existing resolution path.
    tmdb_id: int | None = None
    media_type: str | None = None
    qloo_entity_type: str | None = None
    qloo_resolution_status: str | None = None


@dataclass(frozen=True)
class AudienceMember:
    id: str
    preferences: tuple[AudiencePreference, ...]


@dataclass(frozen=True)
class ResolvedTitle:
    entity_id: str
    title: str
    # Qloo calls these entity *types*.  Keeping it on the resolved record
    # makes a cross-media substitution visible to callers instead of relying
    # on a title match alone.
    entity_type: str | None = None


@dataclass(frozen=True)
class ContributorProvenance:
    """Private evidence linking a candidate to supporting audience input."""

    attendee_id: str
    interest_entity_ids: tuple[str, ...]
    interest_titles: tuple[str, ...]


@dataclass(frozen=True)
class ProviderCandidate:
    """Provider data used internally before it is validated and persisted.

    ``raw_score`` is deliberately never read by the recommendation engine. It is
    present only to make it explicit that a provider may return a score that is
    not comparable across separate ranking queries.
    """

    entity_id: str
    title: str
    release_year: int | None = None
    runtime_minutes: int | None = None
    content_rating: str | None = None
    languages: tuple[str, ...] = ()
    media_type: str | None = None
    eligible: bool = True
    raw_score: float | None = None


class QlooAdapter(Protocol):
    """The backend-only boundary for title resolution and ranking."""

    def resolve_title(
        self,
        title_text: str,
        *,
        media_type: str | None = None,
        release_date: str | None = None,
    ) -> ResolvedTitle | None:
        ...

    def rank_for_interest(
        self, resolved_title: ResolvedTitle
    ) -> Sequence[ProviderCandidate]:
        ...


@dataclass(frozen=True)
class CandidateRecommendation:
    rank: int
    candidate: ProviderCandidate
    fit_explanation: str
    warning_text: str
    contributor_provenance: tuple[ContributorProvenance, ...] = ()


@dataclass(frozen=True)
class RecommendationResult:
    status: str
    registered_count: int
    usable_preference_count: int
    represented_attendee_count: int
    warning_code: str | None
    warning_text: str
    message: str
    failure_code: str | None
    algorithm_version: str = ALGORITHM_VERSION
    candidates: tuple[CandidateRecommendation, ...] = ()


def normalize_interest_key(title_text: str) -> str:
    return unicodedata.normalize("NFC", title_text).strip().casefold()


def qloo_entity_type_for_media_type(media_type: str | None) -> str | None:
    return _SELECTED_QLOO_ENTITY_TYPES.get(media_type or "")


def qloo_resolution_matches_media_type(
    media_type: str | None, entity_type: str | None
) -> bool:
    expected_entity_type = qloo_entity_type_for_media_type(media_type)
    return expected_entity_type is not None and entity_type == expected_entity_type


def _bounded_text(value: object, maximum: int) -> str | None:
    if not isinstance(value, str):
        return None
    value = unicodedata.normalize("NFC", value).strip()
    if not value or len(value) > maximum:
        return None
    if any(unicodedata.category(character) == "Cc" for character in value):
        return None
    return value


def _validated_candidate(candidate: object) -> ProviderCandidate | None:
    if not isinstance(candidate, ProviderCandidate):
        return None
    entity_id = _bounded_text(candidate.entity_id, 160)
    title = _bounded_text(candidate.title, 200)
    if entity_id is None or title is None or candidate.eligible is not True:
        return None

    if candidate.media_type is not None:
        media_type = _bounded_text(candidate.media_type, 32)
        if media_type is None or media_type.casefold() not in _ALLOWED_MEDIA_TYPES:
            return None
    else:
        media_type = None

    release_year = candidate.release_year
    if release_year is not None and (
        isinstance(release_year, bool)
        or not isinstance(release_year, int)
        or not 1800 <= release_year <= date.today().year + 1
    ):
        return None

    runtime_minutes = candidate.runtime_minutes
    if runtime_minutes is not None and (
        isinstance(runtime_minutes, bool)
        or not isinstance(runtime_minutes, int)
        or not 1 <= runtime_minutes <= 1000
    ):
        return None

    content_rating = candidate.content_rating
    if content_rating is not None:
        content_rating = _bounded_text(content_rating, 32)
        if content_rating is None:
            return None

    if not isinstance(candidate.languages, Sequence) or isinstance(
        candidate.languages, (str, bytes)
    ) or len(candidate.languages) > 20:
        return None
    languages: list[str] = []
    for language in candidate.languages:
        normalized_language = _bounded_text(language, 40)
        if normalized_language is None:
            return None
        languages.append(normalized_language)
    if len(json.dumps(languages, ensure_ascii=False)) > 500:
        return None

    return ProviderCandidate(
        entity_id=entity_id,
        title=title,
        release_year=release_year,
        runtime_minutes=runtime_minutes,
        content_rating=content_rating,
        languages=tuple(languages),
        media_type=media_type,
        eligible=True,
        # Deliberately drop any provider score at the validation boundary.
        raw_score=None,
    )


def filter_eligible_candidates(
    candidates: Sequence[ProviderCandidate],
) -> tuple[ProviderCandidate, ...]:
    """Validate and filter one provider query before assigning positions."""

    if not isinstance(candidates, Sequence) or isinstance(candidates, (str, bytes)):
        return ()
    filtered: list[ProviderCandidate] = []
    seen_ids: set[str] = set()
    for candidate in candidates:
        validated = _validated_candidate(candidate)
        if validated is None or validated.entity_id in seen_ids:
            continue
        seen_ids.add(validated.entity_id)
        filtered.append(validated)
    return tuple(filtered)


def normalize_query_ranks(
    candidates: Sequence[ProviderCandidate],
) -> tuple[tuple[ProviderCandidate, float], ...]:
    """Normalize positions inside one query, never provider scores.

    The first eligible result receives 1.0 and the last receives 0.0. A
    one-result query receives 1.0. Eligibility and de-duplication happen before
    positions are assigned, so an ineligible result cannot consume a rank.
    """

    eligible = filter_eligible_candidates(candidates)
    if not eligible:
        return ()
    denominator = max(1, len(eligible) - 1)
    return tuple(
        (candidate, (len(eligible) - position - 1) / denominator)
        for position, candidate in enumerate(eligible)
    )


class RecommendationEngine:
    def __init__(self, adapter: QlooAdapter) -> None:
        self.adapter = adapter

    @staticmethod
    def _persisted_resolution(preference: AudiencePreference) -> ResolvedTitle | None:
        """Return only a trustworthy persisted resolution for one preference."""
        is_selected_tmdb_preference = (
            preference.tmdb_id is not None or preference.media_type is not None
        )
        if is_selected_tmdb_preference:
            if (
                preference.qloo_resolution_status not in (None, "resolved")
                or not qloo_resolution_matches_media_type(
                    preference.media_type, preference.qloo_entity_type
                )
            ):
                return None
        if not preference.qloo_entity_id:
            return None
        return ResolvedTitle(
            preference.qloo_entity_id,
            preference.qloo_title or preference.title_text,
            preference.qloo_entity_type,
        )

    def recommend(self, audience: Sequence[AudienceMember]) -> RecommendationResult:
        registered_count = len(audience)
        usable_members = tuple(
            member
            for member in audience
            if any(preference.title_text.strip() for preference in member.preferences)
        )
        usable_preference_count = len(usable_members)

        if not usable_members:
            return self._unavailable(
                registered_count=registered_count,
                usable_preference_count=0,
                represented_attendee_count=0,
                warning_code="insufficient_coverage",
                failure_code="insufficient_coverage",
                message=(
                    "Recommendations are unavailable because there is not enough "
                    "supported audience input yet."
                ),
            )

        # Resolve each preference independently.  Legacy text is still cached
        # by normalized title, but selected TMDB records are authoritative and
        # must never inherit a different preference's free-text resolution.
        legacy_resolved_by_key: dict[str, ResolvedTitle | None] = {}
        resolved_by_preference: dict[tuple[str, int], ResolvedTitle | None] = {}
        try:
            for member in usable_members:
                for position, preference in enumerate(member.preferences):
                    if not preference.title_text.strip():
                        continue
                    is_selected_tmdb_preference = (
                        preference.tmdb_id is not None
                        or preference.media_type is not None
                    )
                    if is_selected_tmdb_preference:
                        # An unresolved or cross-media persisted selection is
                        # intentionally unsupported until its canonical Qloo
                        # resolution is available.
                        resolved = self._persisted_resolution(preference)
                    else:
                        key = normalize_interest_key(preference.title_text)
                        if key not in legacy_resolved_by_key:
                            resolved = self._persisted_resolution(preference)
                            if resolved is None:
                                resolved = self.adapter.resolve_title(
                                    preference.title_text
                                )
                            legacy_resolved_by_key[key] = resolved
                        resolved = legacy_resolved_by_key[key]
                    if isinstance(resolved, ResolvedTitle):
                        entity_id = _bounded_text(resolved.entity_id, 160)
                        title = _bounded_text(resolved.title, 200)
                        if entity_id is not None and title is not None:
                            resolved = ResolvedTitle(
                                entity_id, title, resolved.entity_type
                            )
                        else:
                            resolved = None
                    else:
                        resolved = None
                    resolved_by_preference[(member.id, position)] = resolved
        except QlooError:
            return self._unavailable(
                registered_count=registered_count,
                usable_preference_count=usable_preference_count,
                represented_attendee_count=0,
                warning_code="provider_unavailable",
                failure_code="qloo_unavailable",
                message="Recommendations are temporarily unavailable. Please retry later.",
            )

        represented_members = tuple(
            member
            for member in usable_members
            if any(
                resolved_by_preference.get((member.id, position)) is not None
                for position, preference in enumerate(member.preferences)
                if preference.title_text.strip()
            )
        )
        represented_attendee_count = len(represented_members)
        if not represented_members:
            return self._unavailable(
                registered_count=registered_count,
                usable_preference_count=usable_preference_count,
                represented_attendee_count=0,
                warning_code="insufficient_coverage",
                failure_code="insufficient_coverage",
                message=(
                    "Recommendations are unavailable because none of the submitted "
                    "titles could be supported."
                ),
            )

        unique_resolved: dict[str, ResolvedTitle] = {}
        for resolved in resolved_by_preference.values():
            if resolved is not None:
                unique_resolved.setdefault(resolved.entity_id, resolved)

        normalized_rankings: dict[str, tuple[tuple[ProviderCandidate, float], ...]] = {}
        try:
            for entity_id, resolved in unique_resolved.items():
                ranked = self.adapter.rank_for_interest(resolved)
                normalized_rankings[entity_id] = normalize_query_ranks(ranked)
        except QlooError:
            return self._unavailable(
                registered_count=registered_count,
                usable_preference_count=usable_preference_count,
                represented_attendee_count=represented_attendee_count,
                warning_code="provider_unavailable",
                failure_code="qloo_unavailable",
                message="Recommendations are temporarily unavailable. Please retry later.",
            )

        weighted_positions: defaultdict[str, float] = defaultdict(float)
        contributors: defaultdict[str, set[str]] = defaultdict(set)
        contributor_interests: dict[str, dict[str, dict[str, set[str]]]] = defaultdict(dict)
        candidate_by_id: dict[str, ProviderCandidate] = {}

        for member in represented_members:
            interest_ids: list[str] = []
            interest_preferences: dict[str, list[AudiencePreference]] = defaultdict(list)
            for position, preference in enumerate(member.preferences):
                resolved = resolved_by_preference.get((member.id, position))
                if resolved is not None and resolved.entity_id not in interest_ids:
                    interest_ids.append(resolved.entity_id)
                if resolved is not None:
                    interest_preferences[resolved.entity_id].append(preference)
            if not interest_ids:
                continue

            # Each represented attendee contributes one unit of weight. A guest
            # who names multiple titles gets an equal share across those titles.
            member_weight = 1.0 / len(interest_ids)
            for entity_id in interest_ids:
                for candidate, normalized_position in normalized_rankings.get(entity_id, ()):
                    candidate_by_id.setdefault(candidate.entity_id, candidate)
                    weighted_positions[candidate.entity_id] += (
                        normalized_position * member_weight
                    )
                    contributors[candidate.entity_id].add(member.id)
                    evidence = contributor_interests[candidate.entity_id].setdefault(
                        member.id,
                        {"interest_entity_ids": set(), "interest_titles": set()},
                    )
                    evidence["interest_entity_ids"].add(entity_id)
                    evidence["interest_titles"].update(
                        preference.title_text
                        for preference in interest_preferences[entity_id]
                    )

        ranked_ids = sorted(
            candidate_by_id,
            key=lambda entity_id: (
                -weighted_positions[entity_id],
                -len(contributors[entity_id]),
                candidate_by_id[entity_id].title.casefold(),
                entity_id,
            ),
        )
        if len(ranked_ids) < 3:
            return self._unavailable(
                registered_count=registered_count,
                usable_preference_count=usable_preference_count,
                represented_attendee_count=represented_attendee_count,
                warning_code="insufficient_coverage",
                failure_code="insufficient_candidates",
                message=(
                    "Recommendations are unavailable because fewer than three "
                    "eligible films were returned. Please retry or add more input."
                ),
            )

        limited = represented_attendee_count < registered_count
        warning_code = "limited_coverage" if limited else None
        coverage_warning = (
            f"Limited coverage: {represented_attendee_count} of {registered_count} "
            "registered attendees had a supported title."
            if limited
            else ""
        )
        general_warning = (
            "Cultural similarity is a signal, not a guarantee that the audience "
            "will enjoy this film. Confirm screening rights separately."
        )
        warning_text = f"{coverage_warning} {general_warning}".strip()

        recommendations: list[CandidateRecommendation] = []
        for rank, entity_id in enumerate(ranked_ids[:3], start=1):
            candidate = candidate_by_id[entity_id]
            support_count = len(contributors[entity_id])
            provenance = tuple(
                ContributorProvenance(
                    attendee_id=attendee_id,
                    interest_entity_ids=tuple(
                        sorted(evidence["interest_entity_ids"])
                    ),
                    interest_titles=tuple(
                        sorted(
                            evidence["interest_titles"],
                            key=normalize_interest_key,
                        )
                    ),
                )
                for attendee_id, evidence in sorted(
                    contributor_interests[entity_id].items()
                )
            )
            if rank == 1:
                explanation = (
                    "Top cross-audience fit: strongest combined within-query "
                    f"position across {support_count} represented attendee"
                    f"{'s' if support_count != 1 else ''}."
                )
            else:
                explanation = (
                    "Alternative cross-audience fit: a real eligible film with "
                    f"support from {support_count} represented attendee"
                    f"{'s' if support_count != 1 else ''}."
                )
            recommendations.append(
                CandidateRecommendation(
                    rank=rank,
                    candidate=candidate,
                    fit_explanation=explanation,
                    warning_text=warning_text,
                    contributor_provenance=provenance,
                )
            )

        return RecommendationResult(
            status="limited" if limited else "succeeded",
            registered_count=registered_count,
            usable_preference_count=usable_preference_count,
            represented_attendee_count=represented_attendee_count,
            warning_code=warning_code,
            warning_text=warning_text,
            message=(
                "These films are a starting point for the organizer's decision."
                if not limited
                else "These films are a limited-coverage starting point for the organizer's decision."
            ),
            failure_code=None,
            candidates=tuple(recommendations),
        )

    @staticmethod
    def _unavailable(
        *,
        registered_count: int,
        usable_preference_count: int,
        represented_attendee_count: int,
        warning_code: str,
        failure_code: str,
        message: str,
    ) -> RecommendationResult:
        warning_text = (
            "No candidate films are shown because a complete, provider-backed "
            "shortlist was not available."
        )
        return RecommendationResult(
            status="unavailable",
            registered_count=registered_count,
            usable_preference_count=usable_preference_count,
            represented_attendee_count=represented_attendee_count,
            warning_code=warning_code,
            warning_text=warning_text,
            message=message,
            failure_code=failure_code,
        )


class RecommendationService:
    def __init__(self, adapter: QlooAdapter) -> None:
        self.engine = RecommendationEngine(adapter)

    def recommend(self, audience: Sequence[AudienceMember]) -> RecommendationResult:
        return self.engine.recommend(audience)


@dataclass
class DeterministicFakeQlooAdapter:
    """Deterministic provider double for API and policy tests."""

    resolutions: Mapping[str, ResolvedTitle | None] = field(default_factory=dict)
    rankings: Mapping[str, Sequence[ProviderCandidate]] = field(default_factory=dict)
    fail_with: QlooError | None = None
    resolved_queries: list[str] = field(default_factory=list)
    ranking_queries: list[str] = field(default_factory=list)

    def resolve_title(
        self,
        title_text: str,
        *,
        media_type: str | None = None,
        release_date: str | None = None,
    ) -> ResolvedTitle | None:
        if self.fail_with is not None:
            raise self.fail_with
        self.resolved_queries.append(title_text)
        return self.resolutions.get(normalize_interest_key(title_text))

    def rank_for_interest(
        self, resolved_title: ResolvedTitle
    ) -> Sequence[ProviderCandidate]:
        if self.fail_with is not None:
            raise self.fail_with
        self.ranking_queries.append(resolved_title.entity_id)
        return self.rankings.get(resolved_title.entity_id, ())


FakeQlooAdapter = DeterministicFakeQlooAdapter


@dataclass
class QlooHttpAdapter:
    """Minimal backend HTTP adapter with credentials kept in process memory."""

    api_key: str | None = None
    base_url: str | None = None
    resolve_path: str | None = None
    ranking_path: str | None = None
    timeout_seconds: float = 5.0

    def __post_init__(self) -> None:
        if self.api_key is None:
            self.api_key = os.getenv("QLOO_API_KEY") or None
        if self.base_url is None:
            self.base_url = os.getenv("QLOO_API_URL") or "https://hackathon.api.qloo.com"
        if self.resolve_path is None:
            self.resolve_path = os.getenv("QLOO_RESOLVE_PATH") or "/search"
        if self.ranking_path is None:
            # Qloo's current API exposes recommendation insights as a
            # parameterized GET endpoint.  The old POST /recommendations
            # route is not available on the hackathon API host.
            self.ranking_path = os.getenv("QLOO_RANK_PATH") or "/v2/insights"

    def resolve_title(
        self,
        title_text: str,
        *,
        media_type: str | None = None,
        release_date: str | None = None,
    ) -> ResolvedTitle | None:
        entity_type = self._entity_type_for_media_type(media_type)
        data = self._request_json(
            self.resolve_path or "/search",
            query={
                "query": title_text,
                "types": entity_type,
                "take": "12",
            },
        )
        for item in self._items(data):
            resolved = self._resolved_title(item)
            if resolved is not None and self._matches_submitted_title(
                title_text, resolved.title
            ) and self._matches_selected_metadata(
                item, expected_entity_type=entity_type, release_date=release_date
            ):
                return resolved
        return None

    @staticmethod
    def _entity_type_for_media_type(media_type: str | None) -> str:
        """Map verified TMDB media types to their Qloo equivalents.

        Legacy free-text preferences did not carry TMDB metadata and retain
        the historic movie-only behaviour.  A selected TV title never does.
        """
        if media_type == "tv":
            return "urn:entity:tv_show"
        return "urn:entity:movie"

    @staticmethod
    def _matches_submitted_title(submitted_title: str, provider_title: str) -> bool:
        """Accept only an exact title or an unambiguous title-plus-subtitle match.

        Qloo search can return unrelated films for abbreviations.  The
        deterministic engine has no approved alias catalogue, so it must not
        silently turn an abbreviation such as ``AOT`` into a different film.
        A submitted base title such as ``Demon Slayer`` may still resolve to a
        provider's colon- or dash-qualified movie title.
        """

        submitted = normalize_interest_key(submitted_title)
        candidate = normalize_interest_key(provider_title)
        if submitted == candidate:
            return True
        if not candidate.startswith(submitted):
            return False
        suffix = candidate[len(submitted) :]
        return suffix.startswith((" ", ":", "-", "–", "—", "("))

    @staticmethod
    def _matches_selected_metadata(
        item: object, *, expected_entity_type: str, release_date: str | None
    ) -> bool:
        """Require Qloo's actual type and reject conflicting known years.

        Search responses are not guaranteed to include release metadata.  If
        it is present, it must agree with the canonical TMDB date; if absent,
        the verified title plus the exact entity type remains the evidence.
        """
        if not isinstance(item, Mapping):
            return False
        types = item.get("types")
        subtype = item.get("subtype")
        item_types = set(types) if isinstance(types, list) else set()
        if isinstance(subtype, str):
            item_types.add(subtype)
        if expected_entity_type not in item_types:
            return False

        if not release_date or len(release_date) < 4:
            return True
        properties = item.get("properties")
        if not isinstance(properties, Mapping):
            properties = {}
        release_value = (
            item.get("release_date")
            or item.get("first_air_date")
            or item.get("release_year")
            or properties.get("release_date")
            or properties.get("first_air_date")
            or properties.get("release_year")
        )
        if release_value is None:
            return True
        return str(release_value)[:4] == release_date[:4]

    def rank_for_interest(
        self, resolved_title: ResolvedTitle
    ) -> Sequence[ProviderCandidate]:
        data = self._request_json(
            self.ranking_path or "/v2/insights",
            query={
                "filter.type": "urn:entity:movie",
                "signal.interests.entities": resolved_title.entity_id,
                "take": "3",
            },
        )
        candidates: list[ProviderCandidate] = []
        for item in self._items(data):
            candidate = self._candidate(item)
            if candidate is not None:
                candidates.append(candidate)
        return candidates

    def _request_json(
        self,
        path: str,
        *,
        query: Mapping[str, str] | None = None,
        payload: Mapping[str, object] | None = None,
    ) -> object:
        api_key = self.api_key if self.api_key is not None else os.getenv("QLOO_API_KEY")
        if not api_key or not self.base_url:
            raise QlooError("provider unavailable")
        url = f"{self.base_url.rstrip('/')}/{path.lstrip('/')}"
        if query:
            url = f"{url}?{urlencode(query)}"
        body = None if payload is None else json.dumps(payload).encode("utf-8")
        request = UrlRequest(
            url,
            data=body,
            method="POST" if body is not None else "GET",
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
                "X-Api-Key": api_key,
            },
        )
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                return json.loads(response.read())
        except (HTTPError, URLError, TimeoutError, OSError, ValueError) as error:
            raise QlooError("provider unavailable") from error

    @staticmethod
    def _items(data: object) -> Sequence[object]:
        if isinstance(data, list):
            return data
        if not isinstance(data, Mapping):
            raise QlooError("invalid provider response")
        for key in ("results", "entities", "recommendations", "data"):
            value = data.get(key)
            if isinstance(value, list):
                return value
            if isinstance(value, Mapping):
                nested = QlooHttpAdapter._items(value)
                if nested:
                    return nested
        raise QlooError("invalid provider response")

    @staticmethod
    def _resolved_title(item: object) -> ResolvedTitle | None:
        if not isinstance(item, Mapping):
            return None
        entity_id = item.get("entity_id") or item.get("id")
        title = item.get("title") or item.get("name")
        if not isinstance(entity_id, str) or not isinstance(title, str):
            return None
        entity_type = item.get("subtype")
        if not isinstance(entity_type, str):
            types = item.get("types")
            entity_type = types[0] if isinstance(types, list) and types and isinstance(types[0], str) else None
        return ResolvedTitle(entity_id=entity_id, title=title, entity_type=entity_type)

    @staticmethod
    def _candidate(item: object) -> ProviderCandidate | None:
        if not isinstance(item, Mapping):
            return None
        properties = item.get("properties")
        if not isinstance(properties, Mapping):
            properties = {}

        def value(name: str) -> object:
            return item.get(name) if item.get(name) is not None else properties.get(name)

        entity_id = item.get("entity_id") or item.get("id")
        title = item.get("title") or item.get("name")
        languages = value("languages")
        if isinstance(languages, list):
            languages = tuple(language for language in languages if isinstance(language, str))
        elif isinstance(languages, tuple):
            pass
        else:
            languages = ()
        if not isinstance(entity_id, str) or not isinstance(title, str):
            return None
        eligible = item.get("eligible", True)
        if not isinstance(eligible, bool):
            return None
        media_type = value("media_type")
        if media_type is None:
            subtype = item.get("subtype")
            if isinstance(subtype, str):
                media_type = subtype.rsplit(":", 1)[-1]
        return ProviderCandidate(
            entity_id=entity_id,
            title=title,
            release_year=value("release_year"),
            runtime_minutes=value("runtime_minutes") or value("duration"),
            content_rating=value("content_rating"),
            languages=languages,
            media_type=media_type,
            eligible=eligible,
            # The provider score is intentionally ignored by the policy.
            raw_score=item.get("score") if isinstance(item.get("score"), (int, float)) else None,
        )


__all__ = [
    "ALGORITHM_VERSION",
    "AudienceMember",
    "AudiencePreference",
    "CandidateRecommendation",
    "ContributorProvenance",
    "DeterministicFakeQlooAdapter",
    "FakeQlooAdapter",
    "ProviderCandidate",
    "QlooAdapter",
    "QlooError",
    "QlooHttpAdapter",
    "RecommendationEngine",
    "RecommendationResult",
    "RecommendationService",
    "ResolvedTitle",
    "filter_eligible_candidates",
    "normalize_interest_key",
    "normalize_query_ranks",
    "qloo_entity_type_for_media_type",
    "qloo_resolution_matches_media_type",
]
