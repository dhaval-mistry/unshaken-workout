# Infrastructure

This area contains deployment-facing assets that must remain separate from the
application's domain code. The current foundation provides container definitions
in `frontend/Dockerfile` and `backend/Dockerfile`, while `compose.yaml` at the
repository root orchestrates local development.

## Local containers

The Compose stack runs PostgreSQL, an Alembic one-shot migration service, FastAPI,
and Vite. The migration service waits for PostgreSQL health before applying the
current migration head; the API starts only if migration succeeds.

Prepare the ignored `.env` file as described in the root README, then run:

```sh
docker compose config
docker compose up --build
```

If PostgreSQL fails to become healthy, inspect `docker compose logs database` and
verify `POSTGRES_DB`, `POSTGRES_USER`, and `POSTGRES_PASSWORD` are populated.
If migrations fail, inspect `docker compose logs migrations` and ensure
`DATABASE_URL` uses host `database`, not `localhost`.

## Future cloud infrastructure

The approved plan identifies Azure Container Apps, PostgreSQL Flexible Server,
Key Vault, Azure Container Registry, and Azure Monitor as a recommendation only.
No cloud resources, deployment templates, identity settings, or secrets are
created by this foundation. Add provider-neutral modules under `azure/` only after
the required owner decisions and deployment scope are explicitly approved.
