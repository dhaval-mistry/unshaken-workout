# Architecture

The current architecture has three explicit runtime concerns:

```text
React browser shell -> FastAPI HTTP boundary -> PostgreSQL
```

The browser is configured with only a public API origin. It queries API liveness
for a non-blocking connection indicator. FastAPI centrally validates settings,
creates an async SQLAlchemy engine, returns correlation identifiers, and exposes
dependency-free liveness plus database-backed readiness.

Future authentication, authorization, account data, exercise-provider adapters,
and training plans are intentionally absent. Their later implementation must keep
the browser-to-API boundary and introduce database state only through Alembic.
