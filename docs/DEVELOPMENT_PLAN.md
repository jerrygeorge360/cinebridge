# Ordered development plan

This is CineBridge's persistent execution plan. It is derived from the approved PRD, design direction, architecture, and decisions. The external AI Factory mirrors these stages and executes at most one eligible stage per run. A stage may not expand the PRD; material changes must be recorded in `docs/DECISIONS.md` and explicitly approved.

## Stage order

| # | Stage | Depends on | Execution | Human approval |
| --- | --- | --- | --- | --- |
| 1 | Research | — | Codex | No |
| 2 | Product definition | Research | Codex | No |
| 3 | Moodboard and brand | Product definition | Codex | Yes (completed) |
| 4 | Penpot organizer recommendation screen | Moodboard and brand | Factory design workflow | Yes |
| 5 | Penpot responsive core flows | Organizer recommendation screen | Factory design workflow | Yes |
| 6 | Data and security contract | Responsive core flows | Codex | Yes, material architecture gate |
| 7 | Event and access foundation | Data and security contract | Codex | No |
| 8 | Attendee registration | Event and access foundation | Codex | No |
| 9 | Qloo recommendation engine | Attendee registration | Codex | No |
| 10 | Organizer selection | Qloo recommendation engine | Codex | No |
| 11 | Integrated QA and privacy review | Organizer selection | Codex | No |
| 12 | Release candidate | Integrated QA | Codex | No |
| 13 | Production release gate | Release candidate | Manual evidence | Yes, merge and release gate |
| 14 | Film Programming Agent change review | Release candidate | Factory change task | Yes, design and material architecture review |
| 15 | Updated release candidate | Film Programming Agent change review | Codex | No |
| 16 | Production release gate (updated) | Updated release candidate | Manual evidence | Yes, merge and release gate |

## 1. Research — completed

- Objective: establish the user problem, Qloo constraints, privacy boundaries, exclusions, and unresolved questions.
- Context: `docs/PRD.md`, `docs/ARCHITECTURE.md`, `docs/DECISIONS.md`.
- Acceptance: the product problem and boundaries are explicit; no feature work is included.
- Validation: `git diff --check`; `python3 -m unittest discover -s tests -v`.
- Approval: none.

## 2. Product definition — completed

- Objective: express the three MVP flows and recommendation policy as testable requirements.
- Context: `docs/PRD.md`, `docs/ARCHITECTURE.md`, `docs/DECISIONS.md`.
- Acceptance: public/private access, optional attendee input, exactly three candidates, honest failure behavior, exclusions, and organizer choice are explicit.
- Validation: `git diff --check`; `python3 -m unittest discover -s tests -v`.
- Dependency: research.
- Approval: none.

## 3. Moodboard and brand — completed and approved

- Objective: record the approved dark, warm independent-cinema direction and its anti-goals.
- Context: `docs/DESIGN.md`, `docs/DECISIONS.md`.
- Acceptance: the visual direction, anti-goals, and Penpot source-of-truth decision are recorded without claiming a reference screen exists.
- Validation: `git diff --check`.
- Dependency: product definition.
- Approval: explicit human brand approval, already recorded.

## 4. Penpot organizer recommendation screen — current

- Objective: create desktop and mobile Penpot frames for the organizer recommendation screen described in `docs/DESIGN.md`.
- Context: `docs/DESIGN.md`, `docs/PRD.md`, `docs/DECISIONS.md`, this plan.
- Acceptance: a real Penpot URL plus non-empty `docs/design/organizer-recommendation-desktop.png` and `docs/design/organizer-recommendation-mobile.png` exports exist; the screen has one top pick, two secondary alternatives, coverage/warning language, and one dominant choice action; it is marked ready for human review, not self-approved.
- Internal steps: create editable desktop/mobile boards through Penpot Cloud MCP; review against the scoped documents; repair only recorded defects; render/export and validate evidence; await human approval. Each factory run performs at most one step under this same stage identity.
- Validation: creation, review, and repair use the matching `--phase` checkpoint validation plus `git diff --check`. Final evidence uses `python3 scripts/validate_design_checkpoint.py docs/design/organizer-recommendation.json`, repository tests, and `git diff --check`.
- Export limitation: if Penpot Cloud MCP cannot save its rendered image result to the repository, manually export only the two named PNGs and rerun the same stage. Missing exports are never fabricated or waived.
- Dependency: moodboard and brand.
- Approval: explicit human approval of the actual Penpot artifact.

## 5. Penpot responsive core flows

- Objective: design responsive event creation, attendee registration, organizer coverage, recommendation failure, and final selection states using the approved reference language.
- Context: `docs/DESIGN.md`, `docs/PRD.md`, `docs/DECISIONS.md`, this plan.
- Acceptance: a real Penpot URL plus non-empty `docs/design/core-responsive-flows-desktop.png` and `docs/design/core-responsive-flows-mobile.png` exports exist; all three MVP flows and empty/error/low-coverage states are represented; public and management contexts are visually distinct; the artifact is ready for human review.
- Internal steps: create, review, targeted repair, export/evidence validation, and human approval under one stage identity.
- Validation: phased checkpoint validation during production; final `python3 scripts/validate_design_checkpoint.py docs/design/core-responsive-flows.json`, repository tests, and `git diff --check`.
- Export limitation: the same exact manual-export fallback applies if the remote MCP result cannot be saved directly.
- Dependency: approved organizer recommendation screen.
- Approval: explicit human approval of the actual Penpot artifact.

## 6. Data and security contract

- Objective: define the domain schema, token handling, public/private API boundary, input limits, rate-limit points, retention/logging rules, Qloo failure contract, and migration approach before feature code.
- Context: `docs/PRD.md`, `docs/ARCHITECTURE.md`, `docs/DECISIONS.md`, `docs/DESIGN.md`, this plan.
- Acceptance: `docs/DATA_SECURITY_CONTRACT.md` is complete and internally consistent; no credentials or feature implementation are added; any material departure from approved architecture is called out rather than silently adopted.
- Validation: `python3 -c "from pathlib import Path; assert Path('docs/DATA_SECURITY_CONTRACT.md').is_file()"`; `python3 -m unittest discover -s tests -v`; `git diff --check`.
- Dependency: approved responsive core-flow designs.
- Approval: explicit human approval because this is the material architecture checkpoint.

## 7. Event and access foundation

- Objective: implement the first approved vertical slice: migrations and persistence for events, secure separate public/private tokens, event creation, and the corresponding responsive web flow.
- Context: PRD, architecture, decisions, design, data/security contract, and this plan.
- Acceptance: tokens are securely random and separated; public access cannot retrieve management data; inputs and logs respect the contract; API and web tests cover the slice; no attendee or recommendation work is started.
- Validation: assert `api/tests/test_events.py` exists; run all API tests; run root tests; run web typecheck; run `git diff --check`.
- Dependency: approved data and security contract.
- Approval: none unless implementation reveals a material architecture change, which stops the stage for human approval.

## 8. Attendee registration

- Objective: implement public attendee registration, optional display-name/preferences input, the three-title limit, private storage, request limits, and responsive states.
- Context: the same approved source documents plus the completed event/access slice.
- Acceptance: public responses never expose preferences or management data; limits and validation are tested; blank preferences are valid; no recommendation work is started.
- Validation: assert `api/tests/test_registrations.py` exists; run all API tests; run root tests; run web typecheck; run `git diff --check`.
- Dependency: event and access foundation.
- Approval: none unless a material architecture change is required.

## 9. Qloo recommendation engine

- Objective: implement backend-only title resolution, eligibility filtering, within-query rank normalization, audience weighting, explanation/warning data, and honest unavailable/limited outcomes.
- Context: approved source documents, data/security contract, and completed registration slice.
- Acceptance: credentials remain server-side; incomparable raw scores are never mixed; success returns exactly one top pick and two alternatives; Qloo failures and insufficient coverage never fabricate films; deterministic fakes cover tests.
- Validation: assert `api/tests/test_recommendations.py` exists; run all API tests; run root tests; run `git diff --check`.
- Dependency: attendee registration.
- Approval: none unless Qloo evidence requires a policy or architecture change.

## 10. Organizer selection

- Objective: implement the private organizer coverage/recommendation experience, explanation path, warning states, and final film selection using the approved Penpot designs.
- Context: all approved product/design/architecture documents and completed backend slices.
- Acceptance: private-token access is enforced; one top pick and two alternatives follow the approved hierarchy; only the organizer can select; no automatic announcement or screening-rights promise is added; API and responsive UI tests cover the flow.
- Validation: assert `api/tests/test_selections.py` exists; run all API tests; run root tests; run web typecheck and production build; run `git diff --check`.
- Dependency: Qloo recommendation engine.
- Approval: none unless a material approved decision must change.

## 11. Integrated QA and privacy review

- Objective: exercise all MVP flows, access boundaries, failure modes, responsive behavior, and sensitive-data handling; fix only in-scope defects.
- Context: all approved documents and completed implementation slices.
- Acceptance: configured API, repository, web, and Compose checks pass; public/private isolation, input limits, Qloo failures, responsive states, and sensitive logging are reviewed; unresolved defects are recorded as blockers.
- Validation: run all API and root tests; run web typecheck and production build; run `docker compose config --quiet`; run `git diff --check`.
- Dependency: organizer selection.
- Approval: none; failures block progression.

## 12. Release candidate

- Objective: produce concise release evidence for the exact tested revision without merging, pushing, deploying, or expanding scope.
- Context: all approved documents, test results, and this plan.
- Acceptance: `docs/RELEASE_CANDIDATE.md` identifies the revision, commands and actual results, known limitations, rollback notes, privacy checks, and deployment prerequisites; all deterministic checks pass.
- Validation: assert the release-candidate document exists; run all API and root tests; run web typecheck and build; run Compose configuration; run `git diff --check`.
- Dependency: integrated QA and privacy review.
- Approval: none; preparation alone does not authorize merge or release.

## 13. Production release gate

- Objective: revalidate the release candidate and present it for a human merge/release decision; the factory does not merge, push, or deploy.
- Context: `docs/RELEASE_CANDIDATE.md`, `docs/DECISIONS.md`, and this plan.
- Acceptance: the release evidence names the intended revision and all configured checks pass immediately before review.
- Validation: run all API and root tests; run web typecheck and build; run Compose configuration; run `git diff --check`.
- Dependency: release candidate.
- Approval: explicit human approval is required for merge and production release; operational merge/deploy remains a separate human-authorized action.

## 14. Film Programming Agent change review

- Objective: review the bounded DeepSeek, Search, TMDB, persistence, and cinematic UI change against `docs/FILM_PROGRAMMING_AGENT_CHANGE_BRIEF.md`.
- Acceptance: the agent cannot alter deterministic Qloo results; no provider key reaches the browser; optional providers fail safely; TMDB attribution, responsive evidence disclosure, and the significant Penpot update are present.
- Validation: API tests including `test_programming.py`; web typecheck/test/build; migration upgrade; Compose configuration; `git diff --check`.
- Approval: explicit human approval of the Penpot design change and any material architecture decision. Production release remains pending.

## 15. Updated release candidate

- Objective: refresh release evidence only after the Film Programming Agent change review is approved.
- Acceptance: evidence records actual validation results, configuration prerequisites, model/search costs if exercised, and known limitations without claiming provider calls that did not occur.
- Validation: repeat the stage 14 validation suite.
- Approval: none; this does not authorize production.
