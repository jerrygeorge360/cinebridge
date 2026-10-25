# CineBridge repository rules

- Treat `docs/PRD.md`, `docs/ARCHITECTURE.md`, and `docs/DECISIONS.md` as the product source of truth.
- This repository must build, test, and deploy without the neighboring development-factory repository.
- Keep Next.js application code in `web/` and FastAPI application code in `api/`.
- Keep Qloo credentials and calls in the backend. Never expose attendee preferences in public responses or logs.
- Preserve the intentional single-instance SQLite architecture until an approved requirement changes it.
- Do not implement recommendations, event management, registration, or other product features before the relevant design and scope stage is approved.
- Penpot is the design source of truth. Figma drafts are reference material only.
- Keep changes scoped, add proportionate tests, and record only meaningful milestones in `docs/DEVLOG.md`.
- Do not push, deploy, merge to `main`, or change external infrastructure without explicit human approval.
