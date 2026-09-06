# Documentation

This directory is the source of record for product constraints, architecture,
decisions, and operational guidance.

- `phase-1-product-and-technical-plan.md` — approved planning context and decisions
  that still need owner confirmation.
- `architecture/` — current technical boundaries and interfaces.
- `decisions/` — concise Architecture Decision Records (ADRs).
- `operations/` — local runbooks and troubleshooting guidance.

## Setup and troubleshooting

Use the root [README](../README.md) to create `.env` and start Docker Compose.
Common failures:

| Symptom | Likely cause | Resolution |
| --- | --- | --- |
| API readiness is `503` | PostgreSQL is not ready or `DATABASE_URL` is wrong. | Check `docker compose logs database` and use `database` as the Compose hostname. |
| Browser says service unavailable | API is stopped or `FRONTEND_API_BASE_URL` is incorrect. | Check API logs and use `http://localhost:8000` for local browser access. |
| CORS request is blocked | The browser origin is absent from `BACKEND_CORS_ORIGINS`. | Set it to a JSON array containing the Vite origin. |
| Migration cannot connect | A host-oriented URL was used from the migration container. | Use the Compose service hostname rather than `localhost`. |

Do not paste production credentials into issues, logs, screenshots, or documentation.
