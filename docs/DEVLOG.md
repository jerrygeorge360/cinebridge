# Development log

## 2026-10-25 — Repository foundation

- Created an independent Git repository with `main` and `staging` branches.
- Added standalone Next.js and FastAPI skeletons, Docker-compatible deployment files, and compact product documentation.
- Recorded the approved dark-cinema direction and prepared the manual Penpot handoff.
- Verification: 13 factory tests, API health test, repository-independence test, TypeScript check, Next.js production build, and Docker Compose configuration all passed. The API container image built; the full Compose image build was canceled during a slow web dependency download, so it is not claimed as complete.
- Next: create the organizer recommendation screen in Penpot and obtain explicit human design approval before feature implementation.

## 2026-10-25 — Persistent factory plan

- Added the ordered development plan and deterministic Penpot evidence check; no product features were implemented.
- The factory now carries stage objectives, context, acceptance criteria, validation, dependencies, resume state, and approval requirements between runs.
- Verification: 21 factory tests, 5 repository tests, the API health test, web typecheck/build, and Compose configuration passed.
- Next: validate and approve the real Penpot organizer recommendation artifact.

## 2026-10-25 — Automated Penpot design workflow

- Replaced the manual-first design gate with resumable create, review, targeted repair, export/evidence, and human-approval steps under the existing stage identity.
- Kept credentials outside the repository and kept final PNG evidence mandatory; remote-export limitations now stop with a two-file manual fallback.
- Verification: 29 factory tests, 9 repository tests, the API health test, web typecheck/build, Compose configuration, and both repositories' diff checks passed.
- No CineBridge product features were implemented.

## 2026-10-26 — Event and access foundation

- Added the first Alembic migration and SQLAlchemy persistence boundary for the seven approved domain tables, with SQLite foreign-key enforcement and migration-before-serve container startup.
- Implemented event creation, future-date and bounded-input validation, separate 32-byte public/private bearer tokens stored only as purpose-bound HMAC digests, public metadata reads, private aggregate overview reads, and process-local request limits.
- Added the responsive organizer setup and link-handoff flow plus public/private access shells; attendee registration and recommendation behavior remain out of scope for this stage.
- Verification: 9 API tests, 4 web flow tests, web typecheck, web production build, 9 repository tests, Compose configuration, and `git diff --check` passed.

## 2026-10-26 — Attendee registration

- Added public attendee registration with normalized display names, optional zero-to-three favorite titles and explanations, private persistence, generic success responses, bounded JSON bodies, and public-token registration throttles.
- Added registration validation and privacy tests plus the responsive attendee form with three-title guidance, private-input copy, and saving/error/success states; recommendation behavior remains out of scope.
- Verification: registration API tests, registration web flow tests, and web typecheck passed.

## 2026-10-26 — Organizer recommendation and selection

- Added the private organizer recommendation screen with Penpot-aligned coverage messaging, one dominant top pick, two secondary alternatives, explanation details, low-coverage/provider warnings, unavailable recovery, and responsive mobile layout.
- Added private-token selection for any complete shortlist candidate, one-selection persistence, selection status on subsequent reads, and explicit no-announcement/no-screening-rights language.
- Verification: 12 focused recommendation API/policy tests, 14 web flow tests, web typecheck, Python compile checks, and `git diff --check` passed. The production build compiled and type-checked but timed out during Next.js file tracing in this environment.

## 2026-10-26 — Integrated QA and privacy review

- Reviewed all MVP flows and boundaries: separate public/private tokens, generic wrong-scope failures, aggregate-only management reads, private preference storage, bounded inputs and JSON bodies, request throttles, missing-credential Qloo failure, low coverage, complete shortlist selection, no announcement, no screening-rights promise, and responsive recommendation states.
- Fixed only in-scope defects found during review: file-backed SQLite migration connection configuration, mandatory JSON for management writes, bounded active rate-limit keys, bounded serialized provider languages, and the mobile explanation path being hidden after “Why this movie?” is activated.
- Verification: API suite 34/34 passed; repository tests 9/9 passed; web tests 14/14 passed; web typecheck passed; Next.js production build passed; `docker compose config --quiet` passed; `git diff --check` passed. A manual TestClient probe also passed event creation, public/private isolation, registration privacy, unavailable Qloo behavior, JSON enforcement, and selection refusal without a complete shortlist.
- Additional `docker compose build api web` evidence was not obtainable because the host Docker BuildKit temporary path is read-only; this is an environment limitation, not a product assertion. No material application blocker remains from the configured Stage 11 checks.
