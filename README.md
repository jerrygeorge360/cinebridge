# CineBridge

CineBridge helps independent film clubs and themed-screening organizers choose one film for an audience with different interests. Attendees can privately share optional favorites; the organizer receives one recommendation and two alternatives with plain-language explanations, then makes the final choice.

The product exists to make group film selection more thoughtful without pretending that cultural similarity guarantees personal enjoyment. The MVP has no organizer accounts, payments, ticketing, automatic announcements, or screening-rights verification.

## Architecture

- `web/`: Next.js + TypeScript user interface.
- `api/`: FastAPI backend; the only future boundary for Qloo credentials and requests.
- SQLite + SQLAlchemy: intentional persistence choice for one application instance. Migrations begin when the first schema is introduced.
- `docs/`: approved requirements, design direction, architecture, decisions, ordered development plan, and milestone log.
- `tests/`: repository-level independence checks.

The repository is standalone. It has no runtime, test, build, or deployment dependency on the development factory that registered it.

## Run locally

Web application:

```bash
cd web
npm ci
npm run dev
```

API in a separate terminal:

```bash
cd api
python3 -m venv .venv
.venv/bin/pip install -e '.[dev]'
.venv/bin/python -m app.start
```

The web setup flow is served at `http://localhost:3000`; the API health check is `http://localhost:8000/health`.

The first schema is applied before the API serves traffic. For a local API run, set
`TOKEN_DIGEST_SECRET` to a deployment-persistent random value and run
`cd api && .venv/bin/alembic upgrade head` before starting Uvicorn. The API keeps only
HMAC-SHA-256 token digests in SQLite; the raw public and private values are returned once,
inside the two creation links.

## Verify

```bash
cd web && npm run typecheck && npm run build
cd web && npm run test
cd api && .venv/bin/python -m unittest discover -s tests -v
python3 -m unittest discover -s tests -v
```

## Containers

`docker compose up --build` builds the independent web and API containers. The Compose file reserves a persistent volume at `/data` for the future SQLite database and is suitable as a starting point for a single-instance Coolify deployment. No deployment has been performed.

## Current checkpoint

The dark cinematic direction is approved. The first high-fidelity reference screen—the organizer movie recommendation screen—is queued for production through the factory's Penpot Cloud MCP workflow and is not approved. See `docs/DESIGN.md` for its phased evidence and approval contract.

The persistent stage sequence, acceptance criteria, dependencies, checks, and approval gates are in `docs/DEVELOPMENT_PLAN.md`. The external factory can continue one eligible stage per invocation without replacing that plan.
