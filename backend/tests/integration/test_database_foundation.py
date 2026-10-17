"""PostgreSQL-backed health and migration verification for the technical foundation."""

import os
import uuid
from argparse import Namespace
from collections.abc import Iterator
from pathlib import Path

import psycopg
import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from psycopg import sql
from sqlalchemy.engine import make_url

from app.core.settings import Settings, get_settings
from app.main import create_app

_TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    _TEST_DATABASE_URL is None,
    reason="TEST_DATABASE_URL is required for PostgreSQL integration tests",
)


def _require_test_database_url() -> str:
    """Narrow the optional environment value after pytest's module-level skip guard."""

    assert _TEST_DATABASE_URL is not None
    return _TEST_DATABASE_URL


def _sync_database_url(database_url: str) -> str:
    """Alembic and test-schema cleanup use psycopg's synchronous driver."""

    return make_url(database_url).set(drivername="postgresql").render_as_string(hide_password=False)


@pytest.fixture
def isolated_test_schema() -> Iterator[str]:
    """Create and remove a random schema so migration tests cannot touch developer data."""

    schema = f"foundation_test_{uuid.uuid4().hex}"
    with psycopg.connect(_sync_database_url(_require_test_database_url()), autocommit=True) as db:
        db.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
        try:
            yield schema
        finally:
            db.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))


def test_readiness_uses_available_postgresql() -> None:
    """Readiness must perform a real connection probe against the isolated test database."""

    app = create_app(Settings(database_url=_require_test_database_url()))
    with TestClient(app) as client:
        response = client.get("/health/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_readiness_reports_unreachable_postgresql() -> None:
    """A refused local port proves readiness does not report success without PostgreSQL."""

    unavailable_url = make_url(_require_test_database_url()).set(host="127.0.0.1", port=1)
    app = create_app(Settings(database_url=str(unavailable_url)))
    with TestClient(app) as client:
        response = client.get("/health/ready")

    assert response.status_code == 503
    assert response.json() == {"status": "unavailable"}


def test_alembic_migrates_an_isolated_test_schema(
    isolated_test_schema: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Apply the migration history to an empty disposable schema and verify its revision."""

    monkeypatch.setenv("DATABASE_URL", _require_test_database_url())
    get_settings.cache_clear()
    config = Config(str(Path(__file__).parents[2] / "alembic.ini"))
    config.cmd_opts = Namespace(x=[f"test_schema={isolated_test_schema}"])

    try:
        command.upgrade(config, "head")
    finally:
        get_settings.cache_clear()

    with psycopg.connect(_sync_database_url(_require_test_database_url())) as db:
        row = db.execute(
            sql.SQL("SELECT version_num FROM {}.alembic_version").format(
                sql.Identifier(isolated_test_schema)
            )
        ).fetchone()

    assert row == ("0001_database_foundation",)
