# Local development runbook

1. Copy the root `.env.example` to `.env`.
2. Assign unique developer-local PostgreSQL values. Set `DATABASE_URL` to a
   `postgresql+asyncpg` URL using service host `database`; set the frontend origin
   in `BACKEND_CORS_ORIGINS` as JSON and `FRONTEND_API_BASE_URL` to
   `http://localhost:8000`.
3. Run `docker compose up --build`.
4. Verify `curl http://localhost:8000/health/live` and
   `curl http://localhost:8000/health/ready`.

To reset local data, first stop the stack, then deliberately run
`docker compose down --volumes`. This permanently removes the local PostgreSQL
volume and should never be used against a shared environment.

For source-level checks, follow the commands in the frontend and backend READMEs.
