# Backend

The FastAPI service establishes production-oriented foundations without exposing
any product feature endpoints. It owns configuration, database connectivity,
structured logging, correlation IDs, liveness, and database readiness.

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

## Commands

Run from this directory:

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

Alembic uses the synchronous `psycopg` driver for migrations while application
requests use `asyncpg`. Both target the same PostgreSQL database. Create a new
migration with `alembic revision -m "describe change"`; review it before applying.

## Health and logs

- `GET /health/live` confirms the process can serve requests.
- `GET /health/ready` runs `SELECT 1` against PostgreSQL and returns `503` when it fails.

Every response includes `X-Correlation-ID`; valid client values are retained and
invalid values are replaced. Logs are JSON and redact credential-shaped extra
fields such as authorization, token, password, secret, cookie, and code.
