# Architecture

The current architecture has three explicit runtime concerns:

```text
React browser shell -> FastAPI HTTP boundary -> PostgreSQL
                              -> ExerciseDB (live only)
```

The browser is configured with only a public API origin. It queries API liveness
for a non-blocking connection indicator. FastAPI centrally validates settings,
creates an async SQLAlchemy engine, returns correlation identifiers, and exposes
dependency-free liveness plus database-backed readiness.

React calls FastAPI only. FastAPI's ExerciseDB adapter normalizes live provider
responses, applies bounded pagination and timeouts, and never persists provider
text or media. Provider configuration and credentials remain API-only. Future
authentication, authorization, account data, and training plans are intentionally
absent. Their later implementation must keep the browser-to-API boundary and
introduce database state only through Alembic.
