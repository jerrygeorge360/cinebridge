# TMDB autocomplete and movie artwork change brief

## Objective

Replace attendee free-text title entry with backend-backed TMDB search and an
explicit selection, while retaining the optional enjoyment note and the
existing deterministic Qloo recommendation policy.

## Boundaries

- The browser never receives a TMDB or Qloo credential.
- A selected preference stores TMDB ID, media type, canonical display title,
  release year, and the optional enjoyment note. TMDB and Qloo identifiers are
  separate fields and are never treated as interchangeable.
- Existing free-text preferences remain readable and are resolved only through
  the existing carefully validated title path.
- Qloo eligibility, rank normalization, weighting, organizer selection, and
  the Film Programming Agent are out of scope.
- TMDB posters for recommendation candidates remain deterministic,
  title/year-checked, cached in the recommendation record, and attributed in
  the interface.

## Acceptance criteria

1. Attendees can search movies and TV series, see poster/year/type, navigate
   results by keyboard, explicitly select up to the existing three preferences,
   add an optional note, and submit on desktop or mobile.
2. Debounced search exposes loading, empty, and safe failure states without
   blocking the registration form.
3. The API validates submitted canonical TMDB metadata, persists it safely,
   and never silently substitutes a Qloo entity for an ambiguous title.
4. Missing TMDB artwork and TMDB/Qloo outages fail safely; saved free-text
   records continue to work.
5. Tests cover ambiguity, mismatches, missing artwork, unresolved Qloo
   entities, TMDB failures, and the attendee-to-recommendation journey.

## Approval and release

The existing Film Programming Agent review stage remains the current factory
stage and production release remains pending. No DeepSeek or web-search changes
are authorized by this brief.
