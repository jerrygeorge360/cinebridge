# CineBridge release candidate

Date: 2026-10-26
Stage: 12 — Release candidate
Status: Revalidated; not approved for merge or production release.

## Exact tested revision

- Committed base: `01072eac44586d109e6d80096a29a0f2cdd92c3a` (`Add phased Penpot design evidence`).
- The checkout was dirty during validation. No commit was created; the candidate is the working tree at that base, including the existing integrated-QA changes.
- Working-tree fingerprint: `462ce10546a8d639d17327a8ad47154f8fcf4e3a153bf8c92633e0c49ab664e5`.
- Fingerprint method: SHA-256 of the binary patch from `HEAD` plus SHA-256 entries for all untracked, non-ignored files, excluding this evidence document. Do not release a different tree without rerunning this evidence.

## Validation results

All final deterministic checks passed on the revision above.

| Check | Result |
| --- | --- |
| `api/.venv/bin/python -m unittest discover -s api/tests -v` | PASS — 36 tests, 12.774s |
| `/home/jerry/agency/dev-workspace/ai-factory/.venv/bin/python -m unittest discover -s /home/jerry/agency/dev-workspace/ai-factory/tests -v` | PASS — 29 tests, 24.571s |
| `web/node_modules/.bin/vitest run` | PASS — 14 tests in 3 files |
| `web/node_modules/.bin/tsc --noEmit` | PASS — exit 0 |
| `DOCKER_BUILDKIT=0 docker compose --env-file .env build api web` | PASS — API image and Next production build completed |
| `docker compose --env-file .env config --quiet` | PASS — exit 0 |
| `git diff --check` | PASS — no whitespace errors |

Live smoke checks also passed: `GET /health` returned `{"status":"ok"}`, the browser-origin CORS preflight returned `200` with `access-control-allow-origin: http://localhost:3000`, and the configured Qloo adapter resolved a title and returned three candidates without exposing credentials.

The API suite was run with the repository's `api/.venv` environment. The host system Python environment initially lacked those dependencies; that environment setup failure was not treated as a product result.

## Privacy and security checks

- API tests passed for public/private token separation, public responses without attendee preferences, private aggregate access, private preference storage, rate limiting, and rejection of cross-scope tokens.
- `rg -n -i 'qloo|qloo_api_key' web/src web/package.json` passed with no matches.
- Qloo credential and provider access were found only in `api/app/recommendations.py`; credentials remain backend-only.
- `rg` found no `print(`, `logging`, or `logger` calls under `api/app`.
- No live Qloo credentials or attendee preference values were added to this evidence.

## Known limitations

- Live Qloo access was verified for one title and one recommendation query; credentials, quota behavior, and broad ranking quality were not exhaustively exercised. Provider failure and low-coverage behavior remain covered as unavailable/limited outcomes.
- The approved MVP remains a single API instance with persistent SQLite storage. Horizontal scaling is outside scope.
- Screening-rights verification, payments, organizer accounts, analytics, automatic announcements, and other excluded PRD features are not included.
- The Penpot design source of truth and any pending human design/release approvals remain unchanged. This document does not self-approve them.

## Rollback notes

- No merge, push, deployment, or external infrastructure change occurred, so no rollback was executed.
- If released after the required human gate, preserve and back up the persistent `/data/cinebridge.db` before replacing the application revision.
- Roll back the web and API services together to the previously approved revision. Restore the database backup with the application revision if a schema-compatible rollback cannot be established.

## Deployment prerequisites

- Human approval at the production release gate is required before merge or release.
- Deploy the exact tested working tree identified above; rerun this validation if the tree changes.
- Provide `QLOO_API_KEY` and `TOKEN_DIGEST_SECRET` only to the API runtime. Configure `DATABASE_URL` for persistent `/data`, plus the approved `WEB_BASE_URL` and `NEXT_PUBLIC_API_BASE_URL` values.
- Use the Docker-compatible `compose.yaml` with a persistent `cinebridge-data` volume and one API instance.
- Confirm the deployment configuration again with `docker compose config --quiet`; deployment itself is not part of this stage.
