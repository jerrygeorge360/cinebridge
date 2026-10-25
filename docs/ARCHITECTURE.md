# Architecture

```text
Browser
  └─ Next.js web (`web/`)
       └─ HTTPS/JSON
            └─ FastAPI (`api/`)
                 ├─ SQLAlchemy → SQLite on persistent storage
                 └─ Qloo API (backend credentials only)
```

The product is one independently deployable repository with two application processes. The browser never talks to Qloo and never receives its credentials. FastAPI owns input validation, access-token checks, recommendation policy, private preference access, rate limits, and persistence. Next.js owns responsive presentation and calls only the product API.

SQLite is intentional for the MVP: deploy one API instance and mount persistent storage for the database file. SQLAlchemy provides the persistence boundary. Introduce schema migrations when the first domain schema is added; no schema or migration is part of the setup checkpoint.

## Planned security boundaries

- Generate separate, high-entropy public registration and private management tokens; store safe representations where practical.
- Never expose attendee preferences through public access.
- Keep Qloo credentials in backend environment secrets and redact sensitive values from logs.
- Validate and limit public input; add request throttling before exposing registration endpoints.
- Collect minimal personal data and state that organizers remain responsible for screening rights.

## Deployment boundary

`compose.yaml` provides Docker-compatible web and API services and persistent `/data` storage. A single-instance Coolify deployment can build directly from this repository. Scaling the API horizontally would require an approved persistence change and is outside the MVP architecture.

The neighboring development factory may read and modify this repository during development, but CineBridge contains no imports, scripts, symlinks, submodules, tests, or deployment references that require the factory.

