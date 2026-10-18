# Unshaken

Unshaken is a responsive workout-planning application. This repository currently
contains its Phase 1 technical foundation plus live standard-exercise browsing and
details: a React client, FastAPI service, PostgreSQL development database, quality
gates, and operational documentation. FastAPI now supports user profile details,
private custom exercises, reusable workout plans, planned sets, workout sessions,
and actual set results. Authentication, invitations, UI workflows, and reporting
are not implemented.

## Architecture

```text
browser -> React + TypeScript -> FastAPI -> PostgreSQL
              :5173             :8000       :5432
```

The browser talks only to the API. The API owns database access and exposes a
liveness endpoint plus a database-backed readiness endpoint. FastAPI alone calls
the catalog provider. Browsing does not persist vendor content; selecting an
ExerciseDB exercise stores only minimum normalized non-media display fields.

## Workout data schema

Alembic revision `0002_workout_plans_and_sessions` adds `users`,
`custom_exercises`, `workout_plans`, `plan_exercises`, `plan_sets`,
`workout_sessions`, `session_exercises`, and `session_sets`. A workout plan holds
ordered exercises and planned sets. A workout session holds a performed workout,
either started from a plan or assembled without one. Exercise-level notes belong
to plan/session exercise rows; each set has its own rep count and optional weight.
Weight is stored in kilograms; a future UI can display the user's preferred unit.
Revision `0003_session_version` adds optimistic concurrency to sessions. Revision
`0004_exercise_catalog` adds controlled taxonomy, selected external records,
trusted snapshots, reps-or-duration sets, per-set rest, and one active session.
Plan and
session mutations use quoted `If-Match` versions so stale browser writes cannot
silently overwrite newer work.

Custom exercises contain only user-authored details. ExerciseDB descriptions,
instructions, raw responses, and media are not stored. Provider-specific
permission for retaining selected-record fields must be confirmed before public
deployment. See
[backend/README.md](backend/README.md) for constraints and verification results.

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
3. Seed the local-only user with `docker compose exec backend python -m app.seed_development_user`.
4. Open `http://localhost:5173`. API liveness is at `http://localhost:8000/health/live`;
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
| `DEVELOPMENT_USER_ID` | API | UUID for the temporary local-only identity; rejected outside development. |
| `DEVELOPMENT_USER_EMAIL` | Seed command | Local profile email; not a login credential. |
| `DEVELOPMENT_USER_DISPLAY_NAME` | Seed command | Local profile display name. |

See [docs/README.md](docs/README.md) for decisions, runbooks, and troubleshooting.
