# ADR 0001: establish portable technical boundaries

## Status

Accepted for the technical foundation.

## Decision

Use a React 18 + TypeScript client built with Vite, a FastAPI service using
SQLAlchemy 2 async access, PostgreSQL, and Alembic migrations. Containers use
Docker Compose locally. API readiness depends only on PostgreSQL; external
providers are not contacted by health probes.

## Consequences

The frontend cannot hold database or provider credentials. FastAPI remains the
single policy and integration boundary. Alembic starts with a baseline revision
but no product tables, because database entities require separately approved user
story implementation.
