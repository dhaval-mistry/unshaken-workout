# Unshaken

Unshaken is a responsive workout-planning application. This repository currently
contains its Phase 1 technical foundation only: a React client, FastAPI service,
PostgreSQL development database, quality gates, and operational documentation.
It intentionally contains no authentication, invitations, exercise-provider
integration, templates, custom exercises, reporting, or workout-session features.

## Architecture

```text
browser -> React + TypeScript -> FastAPI -> PostgreSQL
              :5173             :8000       :5432
```

The browser talks only to the API. The API owns database access and exposes a
liveness endpoint plus a database-backed readiness endpoint. Future identity and
exercise-provider integrations remain outside the frontend boundary.

## Repository layout

- `frontend/` — Vite, React, TypeScript, routing, app shell, and UI tests.
- `backend/` — FastAPI service, configuration, database lifecycle, migrations, and API tests.
- `infrastructure/` — container guidance and future provider-neutral infrastructure modules.
- `docs/` — architecture, decisions, operations, and the approved product plan.
- `compose.yaml` — local development stack.

## Local development

Prerequisites: Docker Desktop with Compose, Node.js 22+ and npm 10+ for frontend
commands, and Python 3.12–3.14 for backend commands.

1. Copy `.env.example` to `.env` and assign developer-local values. `DATABASE_URL`
   must point at the Compose database, for example using the hostname `database`.
   `BACKEND_CORS_ORIGINS` is JSON, such as `["http://localhost:5173"]`.
2. Run `docker compose up --build`.
3. Open `http://localhost:5173`. API liveness is at `http://localhost:8000/health/live`;
   readiness is at `http://localhost:8000/health/ready`.

Compose runs migrations before the API. Stop the stack with `docker compose down`.
Use `docker compose down --volumes` only when deliberately discarding local database data.

## Quality commands

Frontend commands are documented in [frontend/README.md](frontend/README.md).
Backend commands are documented in [backend/README.md](backend/README.md).
The CI workflow runs formatting, linting, type checking, tests, and a production
frontend build on every push and pull request.

## Environment variables

| Variable | Used by | Purpose |
| --- | --- | --- |
| `POSTGRES_DB` | Compose database | Local database name. |
| `POSTGRES_USER` | Compose database | Local database role. |
| `POSTGRES_PASSWORD` | Compose database | Local database password; never commit it. |
| `DATABASE_URL` | API and migrations | SQLAlchemy async PostgreSQL connection URL. |
| `BACKEND_CORS_ORIGINS` | API | JSON list of allowed browser origins. |
| `FRONTEND_API_BASE_URL` | Vite client | Public API origin, normally `http://localhost:8000`. |

See [docs/README.md](docs/README.md) for decisions, runbooks, and troubleshooting.
