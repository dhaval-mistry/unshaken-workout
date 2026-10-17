# Unshaken

Unshaken is a responsive workout-planning application. This repository currently
contains its Phase 1 technical foundation plus live standard-exercise browsing and
details: a React client, FastAPI service, PostgreSQL development database, quality
gates, and operational documentation. It intentionally contains no authentication,
invitations, custom exercises, templates, workout tracking, reporting, or
workout-session features.

## Architecture

```text
browser -> React + TypeScript -> FastAPI -> PostgreSQL
              :5173             :8000       :5432
```

The browser talks only to the API. The API owns database access and exposes a
liveness endpoint plus a database-backed readiness endpoint. The catalog provider
is called only by FastAPI and is never stored in PostgreSQL or browser code.

## Repository layout

- `frontend/` — Vite, React, TypeScript, routing, app shell, and UI tests.
- `backend/` — FastAPI service, configuration, database lifecycle, migrations, and API tests.
- `infrastructure/` — container guidance and future provider-neutral infrastructure modules.
- `docs/` — architecture, decisions, operations, and the approved product plan.
- `compose.yaml` — local development stack.

## Local development

Prerequisites: Docker Desktop with Compose, Node.js 22+ and npm 10+ for frontend
commands, and Python 3.13 for backend commands.

1. Copy `.env.example` to `.env`. It contains safe, clearly marked local-only
   placeholder values that start the stack as-is. `DATABASE_URL` targets the
   Compose `database` hostname and `BACKEND_CORS_ORIGINS` is JSON.
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
| `EXERCISE_DB_BASE_URL` | API | Subscription-specific ExerciseDB API origin; optional until catalog is configured. |
| `EXERCISE_DB_API_KEY` | API | ExerciseDB secret key; deployment environment only. |
| `EXERCISE_DB_HOST` | API | Gateway host required by the provider subscription. |
| `EXERCISE_DB_MEDIA_ENABLED` | API | Enable only when the provider terms permit in-app media display. |

See [docs/README.md](docs/README.md) for decisions, runbooks, and troubleshooting.
