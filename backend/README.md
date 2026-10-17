# Backend

The FastAPI service establishes production-oriented foundations and exposes a
live, non-persistent standard ExerciseDB catalog. It owns configuration, database
connectivity, structured logging, correlation IDs, liveness, and database readiness.

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

- `EXERCISE_DB_BASE_URL` — the subscription's documented API origin (without a trailing slash).
- `EXERCISE_DB_API_KEY` — provider key; never place it in source, browser variables, or logs.
- `EXERCISE_DB_HOST` — the provider host required by the subscription gateway.
- `EXERCISE_DB_MEDIA_ENABLED=true` — only when the active provider terms permit in-app media display.

When any required provider value is absent, catalog endpoints return a safe `503`
response. ExerciseDB's current API terms prohibit persistent storage of its text,
metadata, and media, so this adapter has no cache, database table, downloader, or
bulk import. It references provider media only when explicitly enabled; no media is
downloaded or stored. Re-check provider terms and attribution requirements before
each production launch.

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
dedicated disposable PostgreSQL database. They create and drop a random schema,
but must never target a shared, staging, or developer database. With a disposable
database running, use:

```sh
TEST_DATABASE_URL=postgresql+asyncpg://unshaken_test:test-only@localhost:5432/unshaken_test pytest tests/integration/test_database_foundation.py
```

Alembic uses the synchronous `psycopg` driver for migrations while application
requests use `asyncpg`. Both target the same PostgreSQL database. Create a new
migration with `alembic revision -m "describe change"`; review it before applying.

## Health and logs

- `GET /health/live` confirms the process can serve requests.
- `GET /health/ready` runs `SELECT 1` against PostgreSQL and returns `503` when it fails.

Every response includes `X-Correlation-ID`; valid client values are retained and
invalid values are replaced. Logs are JSON and redact credential-shaped extra
fields such as authorization, token, password, secret, cookie, and code. Uvicorn's
raw access logger is disabled; application middleware emits method, query-free path,
status, duration, and correlation identifier instead.
