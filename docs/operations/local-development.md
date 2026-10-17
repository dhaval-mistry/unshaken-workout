# Local development runbook

1. Install Python 3.13 for source-level backend commands.
2. Copy the root `.env.example` to `.env`. Its clearly marked development-only
   placeholders work with Compose without changes; `DATABASE_URL` uses service host
   `database`, `BACKEND_CORS_ORIGINS` is JSON, and `FRONTEND_API_BASE_URL` is
   `http://localhost:8000`.
3. Run `docker compose up --build`.
4. Verify `curl http://localhost:8000/health/live` and
   `curl http://localhost:8000/health/ready`.

To reset local data, first stop the stack, then deliberately run
`docker compose down --volumes`. This permanently removes the local PostgreSQL
volume and should never be used against a shared environment.

For source-level checks, follow the commands in the frontend and backend READMEs.

## Dependency compatibility notices

React Router currently emits v7 future-flag warnings for `startTransition` and
relative splat-path behavior during frontend tests. Phase 1 has no splat routes
and no functional failure; evaluate the flags deliberately during the React
Router v7 compatibility work rather than changing routing behavior now.

The current compatible FastAPI/Starlette test stack emits a `BlockingPortal`
deprecation warning from Starlette's test client. Keep the tested dependency
versions for Phase 1 and resolve it during a compatibility-reviewed
FastAPI/Starlette upgrade, not through an unreviewed broad dependency update.
