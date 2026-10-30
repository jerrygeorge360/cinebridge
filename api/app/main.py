from __future__ import annotations

import os
import json
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from .database import get_db
from .models import (
    Attendee,
    AttendeePreference,
    Event,
    EventAccessToken,
    RecommendationCandidate,
    RecommendationRun,
    Selection,
)
from .recommendations import (
    ALGORITHM_VERSION,
    AudienceMember,
    AudiencePreference,
    CandidateRecommendation,
    ProviderCandidate,
    RecommendationResult,
    RecommendationService,
    QlooError,
    QlooHttpAdapter,
    qloo_resolution_matches_media_type,
)
from .programming import FilmProgrammingAgent, ProgrammingBrief, Source, ToolObservation
from .tmdb import TmdbClient, TmdbUnavailable, poster_url
from .rate_limit import RateLimiter
from .security import (
    TOKEN_DIGEST_VERSION,
    digest_token,
    generate_access_token,
    rate_limit_key,
    token_matches,
)
from .validation import (
    AttendeeRegistrationCreate,
    EventCreate,
    EventCreationResponse,
    EventPublicResponse,
    PrivateEventResponse,
    RecommendationCandidateResponse,
    RecommendationRequest,
    RecommendationResponse,
    ProgrammingBriefResponse,
    ProgrammingToolObservationResponse,
    ProgrammingSourceResponse,
    RegistrationResponse,
    SelectionRequest,
    SelectionResponse,
    SelectionSummaryResponse,
    TitleSearchItemResponse,
    TitleSearchResponse,
)


app = FastAPI(
    title="CineBridge API",
    summary="Backend boundary for the CineBridge product.",
    version="0.2.0",
)

REQUEST_BODY_LIMIT = 16 * 1024
MANAGEMENT_REQUEST_BODY_LIMIT = 8 * 1024
rate_limiter = RateLimiter()
recommendation_service = RecommendationService(QlooHttpAdapter())
programming_agent = FilmProgrammingAgent()
tmdb_client = TmdbClient()


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _web_base_url() -> str:
    return os.getenv("WEB_BASE_URL", "http://localhost:3000").rstrip("/")


app.add_middleware(
    CORSMiddleware,
    allow_origins=[_web_base_url()],
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type"],
)


def _source_address(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _rate_limited(key: str, *, limit: int, window_seconds: int) -> Response | None:
    allowed, retry_after = rate_limiter.allow(key, limit=limit, window_seconds=window_seconds)
    if allowed:
        return None
    return JSONResponse(
        status_code=429,
        content={"detail": "Too many requests"},
        headers={"Retry-After": str(retry_after)},
    )


def _event_public_response(event: Event) -> EventPublicResponse:
    return EventPublicResponse(
        name=event.name,
        theme=event.theme,
        screening_date=event.screening_date,
        essential_details=event.essential_details,
    )


def _find_access_token(db: Session, token: str, purpose: str) -> EventAccessToken | None:
    if not token or len(token) > 128:
        return None
    presented_digest = digest_token(token, purpose)
    access_token = db.scalar(
        select(EventAccessToken).where(
            EventAccessToken.purpose == purpose,
            EventAccessToken.token_digest == presented_digest,
            EventAccessToken.revoked_at.is_(None),
        )
    )
    if access_token is None or not token_matches(token, purpose, access_token.token_digest):
        return None
    return access_token


def get_recommendation_service() -> RecommendationService:
    return recommendation_service


def _audience_for_event(db: Session, event_id: str) -> list[AudienceMember]:
    attendees = db.scalars(
        select(Attendee)
        .where(Attendee.event_id == event_id)
        .options(selectinload(Attendee.preferences))
        .order_by(Attendee.created_at, Attendee.id)
    ).all()
    return [
        AudienceMember(
            id=attendee.id,
            preferences=tuple(
                AudiencePreference(
                    title_text=preference.title_text,
                    enjoyed_text=preference.enjoyed_text,
                    qloo_entity_id=preference.qloo_entity_id,
                    tmdb_id=preference.tmdb_id,
                    media_type=preference.media_type,
                    qloo_entity_type=preference.qloo_entity_type,
                    qloo_resolution_status=preference.qloo_resolution_status,
                )
                for preference in attendee.preferences
            ),
        )
        for attendee in attendees
    ]


def _programming_evidence(
    result: RecommendationResult,
    audience: list[AudienceMember],
) -> dict[str, object]:
    """Build the agent's verified, identifier-minimized evidence packet.

    This packet contains aggregate coverage, the immutable three-candidate
    snapshot, and separately verified Qloo entity/media pairs.  It never
    contains attendee IDs, display names, or contributor provenance.
    """
    candidate_evidence: dict[str, dict[str, object]] = {}
    evidence_refs = ["packet:coverage"]
    for recommendation in result.candidates:
        candidate = recommendation.candidate
        candidate_id = str(candidate.entity_id)
        media_type = candidate.media_type if candidate.media_type in {"movie", "tv"} else "movie"
        candidate_evidence[candidate_id] = {
            "candidate_id": candidate_id,
            "media_type": media_type,
            "title": candidate.title,
            "release_year": candidate.release_year,
            "runtime_minutes": candidate.runtime_minutes,
            "content_rating": candidate.content_rating,
            "fit_explanation": recommendation.fit_explanation,
            "warning_text": recommendation.warning_text,
            "evidence_ref": f"candidate:{candidate_id}",
        }
        evidence_refs.append(f"candidate:{candidate_id}")

    qloo_entities: dict[str, dict[str, object]] = {}
    for member in audience:
        for preference in member.preferences:
            entity_id = preference.qloo_entity_id
            media_type = preference.media_type
            if not entity_id or media_type not in {"movie", "tv"}:
                continue
            if preference.qloo_resolution_status not in (None, "resolved"):
                continue
            qloo_entities.setdefault(
                str(entity_id),
                {
                    "entity_id": str(entity_id),
                    "media_type": media_type,
                    "evidence_ref": f"qloo:{entity_id}",
                },
            )
    evidence_refs.extend(f"qloo:{entity_id}" for entity_id in qloo_entities)
    return {
        "evidence_refs": evidence_refs,
        "coverage": {
            "status": result.status,
            "registered_count": result.registered_count,
            "usable_preference_count": result.usable_preference_count,
            "represented_attendee_count": result.represented_attendee_count,
            "warning_code": result.warning_code,
        },
        "candidate_evidence": candidate_evidence,
        "qloo_entities": qloo_entities,
    }


def _programming_tool_executor(
    verified_evidence: dict[str, object],
):
    """Return a read-only executor over the already-verified evidence packet."""
    coverage = verified_evidence.get("coverage")
    candidate_evidence = verified_evidence.get("candidate_evidence")
    qloo_entities = verified_evidence.get("qloo_entities")
    coverage = coverage if isinstance(coverage, dict) else {}
    candidate_evidence = candidate_evidence if isinstance(candidate_evidence, dict) else {}
    qloo_entities = qloo_entities if isinstance(qloo_entities, dict) else {}

    def execute(name: str, arguments: dict[str, object]) -> dict[str, object]:
        if name == "inspect_audience_coverage" and not arguments:
            return dict(coverage)
        if name == "inspect_candidate_evidence":
            candidate_id = arguments.get("candidate_id")
            if isinstance(candidate_id, str) and candidate_id in candidate_evidence and set(arguments) == {"candidate_id", "media_type"}:
                observation = candidate_evidence[candidate_id]
                return dict(observation) if isinstance(observation, dict) else {}
        if name == "inspect_qloo_entity":
            entity_id = arguments.get("entity_id")
            if isinstance(entity_id, str) and entity_id in qloo_entities and set(arguments) == {"entity_id", "media_type"}:
                observation = qloo_entities[entity_id]
                return dict(observation) if isinstance(observation, dict) else {}
        raise ValueError("invalid programming evidence request")

    return execute


def _resolve_selected_preferences_for_qloo(
    db: Session, event_id: str, service: RecommendationService
) -> None:
    """Cache a validated Qloo match for selected TMDB titles.

    Provider identifiers remain separate: Qloo is queried by canonical TMDB
    display metadata and only its returned entity id is stored.  A no-match is
    explicit rather than falling back to a different title.
    """
    preferences = db.scalars(
        select(AttendeePreference)
        .join(Attendee, Attendee.id == AttendeePreference.attendee_id)
        .where(
            Attendee.event_id == event_id,
            AttendeePreference.tmdb_id.is_not(None),
            AttendeePreference.qloo_entity_id.is_(None),
            AttendeePreference.qloo_resolution_status == "pending",
        )
    ).all()
    for preference in preferences:
        try:
            resolved = service.engine.adapter.resolve_title(
                preference.title_text,
                media_type=preference.media_type,
                release_date=preference.release_date,
            )
        except QlooError:
            # Keep the pending state: a transient Qloo outage must not turn
            # into a permanent unsupported-title claim.
            continue
        if resolved is None:
            preference.qloo_resolution_status = "unresolved"
            preference.qloo_resolution_reason = (
                f"No matching Qloo {preference.media_type} entity was found for the selected TMDB title"
            )
            continue
        if not qloo_resolution_matches_media_type(
            preference.media_type, resolved.entity_type
        ):
            preference.qloo_resolution_status = "unresolved"
            preference.qloo_resolution_reason = (
                f"Qloo returned an entity with the wrong type for the selected TMDB title"
            )
            continue
        preference.qloo_entity_id = resolved.entity_id
        preference.qloo_entity_type = resolved.entity_type
        preference.qloo_resolution_status = "resolved"
        preference.qloo_resolution_reason = None


def _candidate_response(
    recommendation: CandidateRecommendation,
) -> RecommendationCandidateResponse:
    candidate = recommendation.candidate
    return RecommendationCandidateResponse(
        rank=recommendation.rank,
        title=candidate.title,
        release_year=candidate.release_year,
        runtime_minutes=candidate.runtime_minutes,
        content_rating=candidate.content_rating,
        languages=list(candidate.languages),
        fit_explanation=recommendation.fit_explanation,
        warning_text=recommendation.warning_text,
        poster_url=None,
    )


def _selection_summary(db: Session, event_id: str) -> SelectionSummaryResponse | None:
    selection = db.scalar(select(Selection).where(Selection.event_id == event_id))
    if selection is None:
        return None
    candidate = db.get(RecommendationCandidate, selection.candidate_id)
    if candidate is None or candidate.rank not in {1, 2, 3}:
        return None
    return SelectionSummaryResponse(rank=candidate.rank, title=candidate.title)


def _recommendation_response(
    result: RecommendationResult,
    *,
    selection: SelectionSummaryResponse | None = None,
) -> RecommendationResponse:
    top_pick = _candidate_response(result.candidates[0]) if result.candidates else None
    alternatives = [
        _candidate_response(candidate) for candidate in result.candidates[1:]
    ]
    return RecommendationResponse(
        status=result.status,
        registered_count=result.registered_count,
        usable_preference_count=result.usable_preference_count,
        represented_attendee_count=result.represented_attendee_count,
        warning_code=result.warning_code,
        warning=result.warning_text,
        message=result.message,
        top_pick=top_pick,
        alternatives=alternatives,
        selection=selection,
    )


def _brief_response(brief: ProgrammingBrief | None) -> ProgrammingBriefResponse | None:
    if brief is None:
        return None
    return ProgrammingBriefResponse(
        status=brief.status, summary=brief.summary, tradeoffs=list(brief.tradeoffs),
        uncertainty=brief.uncertainty,
        sources=[ProgrammingSourceResponse(title=item.title, url=item.url, date=item.date) for item in brief.sources],
        tools_used=list(brief.tools_used),
        evidence_refs=list(brief.evidence_refs),
        tool_observations=[
            ProgrammingToolObservationResponse(
                name=item.name,
                arguments=item.arguments,
                observation=item.observation,
                status=item.status,
            )
            for item in brief.tool_observations
        ],
        model_turns=brief.model_turns,
        agent_activity=brief.agent_activity,
    )


def _stored_brief(run: RecommendationRun) -> ProgrammingBrief | None:
    if not run.programming_brief:
        return None
    try:
        data = json.loads(run.programming_brief)
        return ProgrammingBrief(
            status=data["status"], summary=data["summary"], tradeoffs=tuple(data.get("tradeoffs", [])),
            uncertainty=data["uncertainty"],
            sources=tuple(Source(**item) for item in data.get("sources", [])),
            tools_used=tuple(json.loads(run.agent_tools_used or "[]")),
            evidence_refs=tuple(data.get("evidence_refs", [])),
            tool_observations=tuple(
                ToolObservation(
                    name=item["name"],
                    arguments=dict(item.get("arguments", {})),
                    observation=item.get("observation"),
                    status=item.get("status", "executed"),
                )
                for item in data.get("tool_observations", [])
                if isinstance(item, dict) and isinstance(item.get("name"), str)
            ),
            model_turns=data.get("model_turns", 0),
            input_tokens=run.agent_input_tokens, output_tokens=run.agent_output_tokens,
            estimated_cost_usd=run.agent_cost_usd_micros / 1_000_000,
            latency_ms=run.agent_latency_ms,
            agent_activity=data.get(
                "agent_activity",
                # Preserve historical records that predate the more precise
                # activity label. New runs use agent_requested_shortlist.
                "agent_checked_shortlist" if "inspect_shortlist" in json.loads(run.agent_tools_used or "[]") else "deterministic_only",
            ),
        )
    except (KeyError, TypeError, ValueError):
        return None


def _private_event(
    db: Session,
    private_token: str,
) -> Event:
    access_token = _find_access_token(db, private_token, "private_management")
    if access_token is None:
        raise HTTPException(status_code=404, detail="Event not found")
    event = db.get(Event, access_token.event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="Event not found")
    return event


def _store_recommendation_run(
    db: Session,
    event_id: str,
    result: RecommendationResult,
    event_details: str,
    audience: list[AudienceMember] | None = None,
) -> RecommendationRun:
    audience = audience or []
    verified_evidence = _programming_evidence(result, audience)
    attendee_reasons = [
        preference.enjoyed_text
        for member in audience
        for preference in member.preferences
        if preference.enjoyed_text
    ]
    brief = programming_agent.create_brief(
        result=result,
        event_details=event_details,
        attendee_reasons=attendee_reasons,
        verified_evidence=verified_evidence,
        tool_executor=_programming_tool_executor(verified_evidence),
    )
    run = RecommendationRun(
        id=str(uuid4()),
        event_id=event_id,
        status=result.status,
        registered_count=result.registered_count,
        usable_preference_count=result.usable_preference_count,
        represented_attendee_count=result.represented_attendee_count,
        warning_code=result.warning_code,
        failure_code=result.failure_code,
        algorithm_version=result.algorithm_version or ALGORITHM_VERSION,
        requested_at=_utc_now(),
        completed_at=_utc_now(),
        programming_brief=json.dumps({
            "status": brief.status,
            "summary": brief.summary,
            "tradeoffs": list(brief.tradeoffs),
            "uncertainty": brief.uncertainty,
            "sources": [source.__dict__ for source in brief.sources],
            "agent_activity": brief.agent_activity,
            "evidence_refs": list(brief.evidence_refs),
            "tool_observations": [
                {
                    "name": item.name,
                    "arguments": item.arguments,
                    "observation": item.observation,
                    "status": item.status,
                }
                for item in brief.tool_observations
            ],
            "model_turns": brief.model_turns,
        }, ensure_ascii=False),
        agent_tools_used=json.dumps(list(brief.tools_used)),
        agent_input_tokens=brief.input_tokens,
        agent_output_tokens=brief.output_tokens,
        agent_cost_usd_micros=round(brief.estimated_cost_usd * 1_000_000),
        agent_latency_ms=brief.latency_ms,
    )
    for recommendation in result.candidates:
        candidate = recommendation.candidate
        poster = tmdb_client.find_movie(
            candidate.title, candidate.release_year, candidate.runtime_minutes
        )
        run.candidates.append(
            RecommendationCandidate(
                id=str(uuid4()),
                rank=recommendation.rank,
                provider_entity_id=candidate.entity_id,
                title=candidate.title,
                release_year=candidate.release_year,
                runtime_minutes=candidate.runtime_minutes,
                content_rating=candidate.content_rating,
                languages=json.dumps(list(candidate.languages), ensure_ascii=False),
                fit_explanation=recommendation.fit_explanation,
                warning_text=recommendation.warning_text,
                contributor_provenance=json.dumps(
                    [
                        {
                            "attendee_id": contributor.attendee_id,
                            "interest_entity_ids": list(
                                contributor.interest_entity_ids
                            ),
                            "interest_titles": list(contributor.interest_titles),
                        }
                        for contributor in recommendation.contributor_provenance
                    ],
                    ensure_ascii=False,
                    sort_keys=True,
                ),
                tmdb_id=poster.tmdb_id,
                poster_path=poster.poster_path,
                poster_looked_up_at=poster.looked_up_at,
            )
        )
    db.add(run)
    return run


def _run_response(db: Session, run: RecommendationRun) -> RecommendationResponse:
    candidates = sorted(run.candidates, key=lambda candidate: candidate.rank)
    selection = _selection_summary(db, run.event_id)
    if run.status in {"succeeded", "limited"} and len(candidates) != 3:
        return RecommendationResponse(
            status="unavailable",
            registered_count=run.registered_count,
            usable_preference_count=run.usable_preference_count,
            represented_attendee_count=run.represented_attendee_count,
            warning_code="invalid_result",
            warning="No candidate films are shown because a complete, provider-backed shortlist was not available.",
            message="Recommendations are temporarily unavailable. Please retry later.",
            selection=selection,
        )

    response_candidates: list[CandidateRecommendation] = []
    for candidate in candidates:
        try:
            languages = tuple(json.loads(candidate.languages or "[]"))
        except (TypeError, ValueError):
            languages = ()
        response_candidates.append(
            CandidateRecommendation(
                rank=candidate.rank,
                candidate=ProviderCandidate(
                    entity_id=candidate.provider_entity_id or "stored-candidate",
                    title=candidate.title,
                    release_year=candidate.release_year,
                    runtime_minutes=candidate.runtime_minutes,
                    content_rating=candidate.content_rating,
                    languages=languages,
                    media_type="movie",
                ),
                fit_explanation=candidate.fit_explanation,
                warning_text=candidate.warning_text
                or "Cultural similarity is a signal, not a guarantee that the audience will enjoy this film.",
            )
        )
    result = RecommendationResult(
        status=run.status,
        registered_count=run.registered_count,
        usable_preference_count=run.usable_preference_count,
        represented_attendee_count=run.represented_attendee_count,
        warning_code=run.warning_code,
        warning_text=(
            f"Limited coverage: {run.represented_attendee_count} of {run.registered_count} registered attendees had usable, supported preferences."
            if run.status == "limited"
            else "Cultural similarity is a signal, not a guarantee that the audience will enjoy a film."
        ),
        message=(
            "These films are a limited-coverage starting point for the organizer's decision."
            if run.status == "limited"
            else "These films are a starting point for the organizer's decision."
        ),
        failure_code=run.failure_code,
        algorithm_version=run.algorithm_version,
        candidates=tuple(response_candidates),
    )
    response = _recommendation_response(result, selection=selection)
    candidate_models = [candidate for candidate in [response.top_pick, *response.alternatives] if candidate]
    for candidate_model, candidate in zip(candidate_models, candidates):
        candidate_model.poster_url = poster_url(candidate.poster_path)
    response.programming_brief = _brief_response(_stored_brief(run))
    return response


@app.get(
    "/events/public/{public_token}/title-search",
    response_model=TitleSearchResponse,
    tags=["public registrations"],
)
def search_titles(
    public_token: str,
    q: str,
    request: Request,
    db: Session = Depends(get_db),
) -> TitleSearchResponse | Response:
    """Return selectable TMDB matches while retaining TMDB credentials server-side."""
    presented_digest = digest_token(public_token, "public_registration")
    source_key = rate_limit_key(_source_address(request), presented_digest)
    limited = _rate_limited(f"title-search:{source_key}", limit=40, window_seconds=60)
    if limited is not None:
        return limited
    if _find_access_token(db, public_token, "public_registration") is None:
        raise HTTPException(status_code=404, detail="Event not found")
    normalized_query = q.strip()
    if len(normalized_query) < 2 or len(normalized_query) > 100:
        raise HTTPException(status_code=422, detail="Search text must be between 2 and 100 characters")
    try:
        results = tmdb_client.search_titles(normalized_query)
    except TmdbUnavailable:
        raise HTTPException(status_code=503, detail="Title search is temporarily unavailable") from None
    return TitleSearchResponse(
        suggestion="Attack on Titan" if normalized_query.casefold() == "aot" else None,
        results=[
            TitleSearchItemResponse(
                tmdb_id=item.tmdb_id,
                media_type=item.media_type,
                title=item.title,
                release_date=item.release_date,
                release_year=int(item.release_date[:4]) if item.release_date and item.release_date[:4].isdigit() else None,
                poster_path=item.poster_path,
                poster_url=poster_url(item.poster_path),
            )
            for item in results
        ],
    )


@app.middleware("http")
async def enforce_request_contract(request: Request, call_next):
    is_registration = (
        request.method == "POST"
        and request.url.path.startswith("/events/public/")
        and request.url.path.endswith("/registrations")
    )
    is_recommendation_request = (
        request.method == "POST"
        and request.url.path.startswith("/events/private/")
        and request.url.path.endswith("/recommendations")
    )
    is_selection_request = (
        request.method == "POST"
        and request.url.path.startswith("/events/private/")
        and request.url.path.endswith("/selection")
    )
    if request.method == "POST" and (request.url.path == "/events" or is_registration):
        content_type = request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
        if content_type != "application/json":
            return JSONResponse(status_code=415, content={"detail": "JSON is required"})
        content_length = request.headers.get("content-length")
        if content_length is not None:
            try:
                if int(content_length) > REQUEST_BODY_LIMIT:
                    return JSONResponse(status_code=413, content={"detail": "Request is too large"})
            except ValueError:
                return JSONResponse(status_code=400, content={"detail": "Invalid request"})
        body = await request.body()
        if len(body) > REQUEST_BODY_LIMIT:
            return JSONResponse(status_code=413, content={"detail": "Request is too large"})
        request._body = body
    elif is_recommendation_request or is_selection_request:
        content_type = request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
        if content_type != "application/json":
            return JSONResponse(status_code=415, content={"detail": "JSON is required"})
        content_length = request.headers.get("content-length")
        if content_length is not None:
            try:
                if int(content_length) > MANAGEMENT_REQUEST_BODY_LIMIT:
                    return JSONResponse(status_code=413, content={"detail": "Request is too large"})
            except ValueError:
                return JSONResponse(status_code=400, content={"detail": "Invalid request"})
        body = await request.body()
        if len(body) > MANAGEMENT_REQUEST_BODY_LIMIT:
            return JSONResponse(status_code=413, content={"detail": "Request is too large"})
        request._body = body

    response = await call_next(request)
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    if request.url.path.startswith("/events/public/") or request.url.path.startswith("/events/private/"):
        response.headers["Cache-Control"] = "no-store"
    return response


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, _exc: RequestValidationError) -> JSONResponse:
    path = request.url.path
    if request.method == "POST" and path.startswith("/events/public/") and path.endswith("/registrations"):
        detail = "Invalid registration details"
    elif request.method == "POST" and path.startswith("/events/private/") and path.endswith("/recommendations"):
        detail = "Invalid recommendation request"
    elif request.method == "POST" and path.startswith("/events/private/") and path.endswith("/selection"):
        detail = "Invalid selection request"
    else:
        detail = "Invalid event details"
    return JSONResponse(status_code=422, content={"detail": detail})


@app.get("/health", tags=["operations"])
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/events", response_model=EventCreationResponse, status_code=201, tags=["events"])
def create_event(
    payload: EventCreate,
    request: Request,
    db: Session = Depends(get_db),
) -> EventCreationResponse | Response:
    source = rate_limit_key(_source_address(request), "event-creation")
    limited = _rate_limited(f"create:{source}", limit=5, window_seconds=15 * 60)
    if limited is not None:
        return limited
    limited = _rate_limited("create:global", limit=100, window_seconds=60)
    if limited is not None:
        return limited

    public_token = generate_access_token()
    private_token = generate_access_token()
    while private_token == public_token:
        private_token = generate_access_token()

    event = Event(
        id=str(uuid4()),
        name=payload.name,
        theme=payload.theme,
        screening_date=payload.screening_date,
        essential_details=payload.essential_details,
        created_at=_utc_now(),
    )
    issued_at = _utc_now()
    event.access_tokens.extend(
        [
            EventAccessToken(
                id=str(uuid4()),
                purpose="public_registration",
                token_digest=digest_token(public_token, "public_registration"),
                digest_version=TOKEN_DIGEST_VERSION,
                issued_at=issued_at,
            ),
            EventAccessToken(
                id=str(uuid4()),
                purpose="private_management",
                token_digest=digest_token(private_token, "private_management"),
                digest_version=TOKEN_DIGEST_VERSION,
                issued_at=issued_at,
            ),
        ]
    )
    db.add(event)
    db.commit()

    public_url = f"{_web_base_url()}/join/{public_token}"
    private_url = f"{_web_base_url()}/manage/{private_token}"
    return EventCreationResponse(
        **_event_public_response(event).model_dump(),
        public_registration_url=public_url,
        private_management_url=private_url,
    )


@app.get(
    "/events/public/{public_token}",
    response_model=EventPublicResponse,
    tags=["public events"],
)
def read_public_event(
    public_token: str,
    request: Request,
    db: Session = Depends(get_db),
) -> EventPublicResponse | Response:
    presented_digest = digest_token(public_token, "public_registration")
    source_key = rate_limit_key(_source_address(request), presented_digest)
    limited = _rate_limited(f"public-read:{source_key}", limit=60, window_seconds=60)
    if limited is not None:
        return limited
    access_token = _find_access_token(db, public_token, "public_registration")
    if access_token is None:
        raise HTTPException(status_code=404, detail="Event not found")
    event = db.get(Event, access_token.event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="Event not found")
    return _event_public_response(event)


@app.post(
    "/events/public/{public_token}/registrations",
    response_model=RegistrationResponse,
    status_code=201,
    tags=["public registrations"],
)
def create_public_registration(
    public_token: str,
    payload: AttendeeRegistrationCreate,
    request: Request,
    db: Session = Depends(get_db),
) -> RegistrationResponse | Response:
    presented_digest = digest_token(public_token, "public_registration")
    source_key = rate_limit_key(_source_address(request), presented_digest)
    limited = _rate_limited(
        f"registration:{source_key}", limit=10, window_seconds=10 * 60
    )
    if limited is not None:
        return limited
    limited = _rate_limited(
        f"registration:event:{presented_digest}", limit=100, window_seconds=60 * 60
    )
    if limited is not None:
        return limited

    access_token = _find_access_token(db, public_token, "public_registration")
    if access_token is None:
        raise HTTPException(status_code=404, detail="Event not found")
    event = db.get(Event, access_token.event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="Event not found")

    verified_titles: dict[int, object] = {}
    for position, preference in enumerate(payload.preferences, start=1):
        if not preference.title_text or preference.tmdb_id is None or preference.media_type is None:
            continue
        try:
            verified = tmdb_client.selected_title(
                tmdb_id=preference.tmdb_id, media_type=preference.media_type
            )
        except TmdbUnavailable:
            raise HTTPException(
                status_code=503, detail="Selected title could not be verified"
            ) from None
        # Do not accept a browser-provided title under a different real TMDB
        # id.  Date and artwork are always persisted from TMDB below.
        if verified is None or verified.title != preference.title_text:
            raise HTTPException(status_code=422, detail="Selected title could not be verified")
        verified_titles[position] = verified

    attendee = Attendee(
        id=str(uuid4()),
        event_id=event.id,
        display_name=payload.display_name,
        created_at=_utc_now(),
    )
    for position, preference in enumerate(payload.preferences, start=1):
        if not preference.title_text:
            continue
        verified = verified_titles.get(position)
        attendee.preferences.append(
            AttendeePreference(
                id=str(uuid4()),
                position=position,
                title_text=verified.title if verified is not None else preference.title_text,
                tmdb_id=verified.tmdb_id if verified is not None else None,
                media_type=verified.media_type if verified is not None else None,
                release_date=verified.release_date if verified is not None else None,
                poster_path=verified.poster_path if verified is not None else None,
                # A TMDB id is not a Qloo id.  Selected records are resolved
                # against Qloo later using carefully validated title metadata.
                qloo_resolution_status=("pending" if preference.tmdb_id else "legacy"),
                enjoyed_text=preference.enjoyed_text,
                created_at=_utc_now(),
            )
        )
    db.add(attendee)
    db.commit()
    return RegistrationResponse(message="Registration received")


@app.get(
    "/events/private/{private_token}",
    response_model=PrivateEventResponse,
    tags=["private events"],
)
def read_private_event(
    private_token: str,
    request: Request,
    db: Session = Depends(get_db),
) -> PrivateEventResponse | Response:
    presented_digest = digest_token(private_token, "private_management")
    source_key = rate_limit_key(_source_address(request), presented_digest)
    limited = _rate_limited(f"private-read:{source_key}", limit=60, window_seconds=60)
    if limited is not None:
        return limited
    access_token = _find_access_token(db, private_token, "private_management")
    if access_token is None:
        raise HTTPException(status_code=404, detail="Event not found")
    event = db.get(Event, access_token.event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="Event not found")

    registered_count = db.scalar(
        select(func.count(Attendee.id)).where(Attendee.event_id == event.id)
    ) or 0
    usable_preference_count = db.scalar(
        select(func.count(func.distinct(AttendeePreference.attendee_id)))
        .join(Attendee, Attendee.id == AttendeePreference.attendee_id)
        .where(Attendee.event_id == event.id)
    ) or 0
    return PrivateEventResponse(
        **_event_public_response(event).model_dump(),
        registered_count=registered_count,
        usable_preference_count=usable_preference_count,
        represented_attendee_count=0,
        selection=_selection_summary(db, event.id),
    )


@app.post(
    "/events/private/{private_token}/recommendations",
    response_model=RecommendationResponse,
    tags=["private recommendations"],
)
def request_recommendations(
    private_token: str,
    request: Request,
    payload: RecommendationRequest,
    db: Session = Depends(get_db),
    service: RecommendationService = Depends(get_recommendation_service),
) -> RecommendationResponse | Response:
    presented_digest = digest_token(private_token, "private_management")
    limited = _rate_limited(
        f"recommendation:{presented_digest}", limit=3, window_seconds=10 * 60
    )
    if limited is not None:
        return limited

    event = _private_event(db, private_token)
    _resolve_selected_preferences_for_qloo(db, event.id, service)
    audience = _audience_for_event(db, event.id)
    result = service.recommend(audience)
    run = _store_recommendation_run(db, event.id, result, event.essential_details, audience)
    db.commit()
    return _run_response(db, run)


@app.get(
    "/events/private/{private_token}/recommendations",
    response_model=RecommendationResponse,
    tags=["private recommendations"],
)
def read_recommendations(
    private_token: str,
    request: Request,
    db: Session = Depends(get_db),
) -> RecommendationResponse | Response:
    presented_digest = digest_token(private_token, "private_management")
    limited = _rate_limited(f"private-read:{presented_digest}", limit=60, window_seconds=60)
    if limited is not None:
        return limited

    event = _private_event(db, private_token)
    run = db.scalar(
        select(RecommendationRun)
        .where(RecommendationRun.event_id == event.id)
        .options(selectinload(RecommendationRun.candidates))
        .order_by(RecommendationRun.requested_at.desc(), RecommendationRun.id.desc())
    )
    if run is None:
        return RecommendationResponse(
            status="unavailable",
            registered_count=db.scalar(
                select(func.count(Attendee.id)).where(Attendee.event_id == event.id)
            )
            or 0,
            usable_preference_count=db.scalar(
                select(func.count(func.distinct(AttendeePreference.attendee_id)))
                .join(Attendee, Attendee.id == AttendeePreference.attendee_id)
                .where(Attendee.event_id == event.id)
            )
            or 0,
            represented_attendee_count=0,
            warning_code="not_requested",
            warning="No candidate films are shown until a complete, provider-backed shortlist is available.",
            message="Recommendations have not been requested yet.",
            selection=_selection_summary(db, event.id),
        )
    return _run_response(db, run)


@app.post(
    "/events/private/{private_token}/selection",
    response_model=SelectionResponse,
    tags=["private selection"],
)
def select_final_film(
    private_token: str,
    payload: SelectionRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> SelectionResponse | Response:
    presented_digest = digest_token(private_token, "private_management")
    limited = _rate_limited(
        f"selection:{presented_digest}", limit=10, window_seconds=60
    )
    if limited is not None:
        return limited

    event = _private_event(db, private_token)
    if db.scalar(select(Selection).where(Selection.event_id == event.id)) is not None:
        raise HTTPException(status_code=409, detail="A final film has already been selected")

    run = db.scalar(
        select(RecommendationRun)
        .where(RecommendationRun.event_id == event.id)
        .options(selectinload(RecommendationRun.candidates))
        .order_by(RecommendationRun.requested_at.desc(), RecommendationRun.id.desc())
    )
    if run is None or run.status not in {"succeeded", "limited"}:
        raise HTTPException(
            status_code=409,
            detail="A complete recommendation shortlist is required before selection",
        )

    candidates = sorted(run.candidates, key=lambda candidate: candidate.rank)
    candidate = next((item for item in candidates if item.rank == payload.rank), None)
    if len(candidates) != 3 or candidate is None or not candidate.provider_entity_id:
        raise HTTPException(
            status_code=409,
            detail="That recommendation is no longer available for selection",
        )

    selection = Selection(
        id=str(uuid4()),
        event_id=event.id,
        run_id=run.id,
        candidate_id=candidate.id,
        selected_at=_utc_now(),
    )
    db.add(selection)
    try:
        db.commit()
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(status_code=409, detail="A final film has already been selected") from error

    return SelectionResponse(
        message="Final film selected for this private workspace. No announcement was sent.",
        selection=SelectionSummaryResponse(rank=candidate.rank, title=candidate.title),
    )
