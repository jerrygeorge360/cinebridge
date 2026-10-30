# Film Programming Agent change brief

## Scope

Add an optional, backend-only Film Programming Agent to the existing organizer recommendation flow. It may inspect the already-ranked Qloo shortlist and, only where event details require current information, call DeepSeek Search once. It produces a compact evidence-labelled programming brief; it cannot add films, modify ranks, calculate fit, verify screening rights, or expose attendee preferences.

## Boundaries and controls

- The deterministic Python engine remains authoritative for eligibility, Qloo rank normalization, aggregation, and all constraints.
- `deepseek-flash` is called through `/responses` with at most two output tool calls and 300 output tokens. The implementation permits only `inspect_shortlist` and a conditional `search_current_info`.
- DeepSeek Flash does not support the Responses built-in `web_search` tool, so current-info search uses the documented raw Search API, at most once with three results. URLs and supplied dates are persisted with the brief; search never confirms rights or availability.
- A missing or failing DeepSeek/TMDB configuration returns the deterministic result with a safe brief/placeholder. It does not make recommendation availability worse.
- Token counts, estimated model cost, tool names, and latency are stored with each run. Credentials remain backend environment variables.
- TMDB lookup is deterministic, title/year constrained, and stores the returned ID, poster path, and lookup time. Existing stored metadata is the cache record; no image is fabricated. UI includes the required “This product uses the TMDB API but is not endorsed or certified by TMDB” attribution.

## Review evidence required

Run API tests, web typecheck/test/build, compose config, a migration check, and desktop/mobile visual review against the updated Penpot artifact. Record actual model/search calls and costs only when configured; do not claim live provider validation without credentials.
