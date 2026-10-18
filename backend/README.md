# Backend

The FastAPI service establishes production-oriented foundations and exposes a
live ExerciseDB catalog plus a unified selectable catalog. It owns configuration, database
connectivity, structured logging, correlation IDs, liveness, and database readiness.
Alembic also defines user, custom exercise, workout plan, and workout session
tables. Private APIs support planning and logging through a temporary local-only
identity while authentication remains intentionally closed.

## Structure

- `app/api/` — HTTP routes and response schemas.
- `app/core/` — settings, structured logging, and request context.
- `app/infrastructure/db/` — SQLAlchemy async engine lifecycle.
- `migrations/` — Alembic migration history. Every future database change belongs here.
- `tests/unit/` and `tests/integration/` — focused foundation coverage.

## Configuration

`DATABASE_URL` is required and uses SQLAlchemy's async PostgreSQL form,
`postgresql+asyncpg://USER:PASSWORD@HOST:5432/DATABASE`. `CORS_ORIGINS` is a JSON
array of public frontend origins. `APP_ENVIRONMENT` is one of `development`,
`test`, `staging`, or `production`; `LOG_LEVEL` defaults to `INFO`.

Settings intentionally fail fast when `DATABASE_URL` is absent. Keep all values
in the ignored repository-root `.env` file or in the deployment environment.

### ExerciseDB live catalog

The browser calls only `/api/exercises`; FastAPI calls ExerciseDB at request time
through `app/infrastructure/exercise_db/`. Configure these deployment-environment
values only after confirming an active ExerciseDB subscription and current terms:

- `EXERCISE_DB_BASE_URL` — `https://exercisedb.p.rapidapi.com` for this subscription.
- `EXERCISE_DB_API_KEY` — provider key; never place it in source, browser variables, or logs.
- `EXERCISE_DB_HOST` — `exercisedb.p.rapidapi.com` for the `X-RapidAPI-Host` header.
- `EXERCISE_DB_MEDIA_ENABLED=true` — only when the active provider terms permit in-app media display.

When any required provider value is absent, catalog endpoints return a safe `503`
response. Place the key only in the ignored local `.env` or a deployment secret
store. The adapter sends `X-RapidAPI-Key` and `X-RapidAPI-Host` from backend settings;
React never receives the key. Browsing never stores provider records. Selecting an
exercise stores only approved normalized non-media fields; provider-specific
permission must still be confirmed before public deployment. The image proxy
is disabled by default and, when explicitly enabled, sends `Cache-Control: no-store`.
Confirm media-display and attribution rights before enabling it.

Live routes: `GET /api/exercises` (browse; optionally filter by exactly one of
`query`, `body_part`, `equipment`, or `target`), `/api/exercises/status`,
`/api/exercises/body-parts`, `/api/exercises/targets`, `/api/exercises/equipment`,
`/api/exercises/search/{name}`, `/api/exercises/target/{target}`,
`/api/exercises/body-part/{body_part}`, `/api/exercises/equipment/{equipment}`,
`/api/exercises/{id}`, and `/api/exercises/image/{id}`. List routes use bounded
`page` and `page_size` parameters. The upstream provider supports one filter per
request; combining filters returns `422` rather than silently ignoring criteria.

## Commands

Run from this directory with Python 3.13:

```sh
python -m venv .venv
.venv/Scripts/activate  # PowerShell: .venv\\Scripts\\Activate.ps1
pip install -e ".[dev]"
ruff format --check .
ruff check .
mypy app
pytest
alembic upgrade head
```

### PostgreSQL integration tests

The database integration tests are skipped unless `TEST_DATABASE_URL` points to a
dedicated disposable PostgreSQL database. Migration tests create and drop random
schemas. Workout API tests reset only a database whose name ends in `_test`, whose
host is local or the Compose `database` service, and whose database name differs
from `DATABASE_URL`. The guard refuses other targets before any reset. With a
disposable database running, use:

```sh
TEST_DATABASE_URL=postgresql+asyncpg://unshaken_test:test-only@localhost:5432/unshaken_test pytest tests/integration/test_database_foundation.py
```

Alembic uses the synchronous `psycopg` driver for migrations while application
requests use `asyncpg`. Both target the same PostgreSQL database. Create a new
migration with `alembic revision -m "describe change"`; review it before applying.

### Workout schema

Revisions `0002` through `0004_exercise_catalog` provide the workout schema:

| Table | Data held |
| --- | --- |
| `users` | Basic profile and preferred weight unit; no login credentials. |
| `custom_exercises` | Private details with one equipment, body part, and reps/duration measurement type. |
| `external_exercises` | Minimum normalized display fields for selected ExerciseDB records. |
| `workout_plans` | Named, reusable plans owned by a user. |
| `plan_exercises` | Ordered exercises and exercise-level notes in a plan. |
| `plan_sets` | Per-set target reps or duration, optional weight, and planned rest. |
| `workout_sessions` | Started/finished workouts, optional source plan, and elapsed time. |
| `session_exercises` | Ordered exercises and exercise-level notes in a performed workout. |
| `session_sets` | Copied targets/rest and actual reps or duration with optional weight. |

The database permits exactly one custom or external source per plan/session
exercise. Composite foreign keys prevent referencing another user's custom
exercise or plan. Order, status, and nonnegative measures have database checks.
Plans and sessions are separate so later plan edits cannot rewrite completed
workouts. Selected ExerciseDB rows store only provider ID, normalized display
fields, attribution, and validation timestamps. They never store media,
instructions, or raw responses. Confirm provider-specific permission before
public deployment.

### Private workout APIs

Set `DEVELOPMENT_USER_ID` to a UUID, then run the idempotent local seed command:

```sh
python -m app.seed_development_user
```

The command and private routes fail closed outside `development`. There is no
public user-creation route and clients cannot provide an owner ID. This mechanism
must be replaced by approved authentication before deployment or invited-user use.

The API provides `/api/exercise-options`, cursor-based `/api/exercise-catalog`,
`/api/exercise-performance/latest`, `GET/PATCH /api/me`; owner-only management under
`/api/custom-exercises`; versioned plan, exercise, and planned-set operations under
`/api/workout-plans`; and versioned session, exercise, actual-set, finish, and
abandon operations under `/api/workout-sessions`. `GET /current` restores the only
active session and `DELETE /{session_id}` permanently cancels an active session.
Swagger lists the full contract and common journeys at `/docs`.

Plan and session responses include `ETag: "N"`. Later mutations send that value in
`If-Match`; missing preconditions return `428` and stale writes return `409`.
Starting from a plan atomically copies exercise snapshots, notes, measurement
types, planned sets, and rest. A database partial unique index permits one active
session per user. Terminal sessions are immutable. Finish requires at least one
exercise and set and requires every set to be completed or skipped.

The PostgreSQL tests use isolated schemas and a guarded disposable database. The
current verified suite is **59 passed, 0 skipped**, with one third-party Starlette
deprecation warning. `ruff format --check .`, `ruff check app tests migrations`,
and `mypy app` pass. Fresh upgrade, downgrade to `0003_session_version`, and
re-upgrade reach `0004_exercise_catalog`. Manual loopback checks returned `200`
for exercise options and OpenAPI, and the expected `404 no_active_session` when no
workout was active.

## Health and logs

- `GET /health/live` confirms the process can serve requests.
- `GET /health/ready` runs `SELECT 1` against PostgreSQL and returns `503` when it fails.

Every response includes `X-Correlation-ID`; valid client values are retained and
invalid values are replaced. Logs are JSON and redact credential-shaped extra
fields such as authorization, token, password, secret, cookie, and code. Uvicorn's
raw access logger is disabled; application middleware emits method, query-free path,
status, duration, and correlation identifier instead.
