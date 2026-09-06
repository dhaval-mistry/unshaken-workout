"""Shared test configuration for the API foundation."""

import os

# Importing app.main constructs the production ASGI app, so tests supply only a local URL.
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost:5432/test")
