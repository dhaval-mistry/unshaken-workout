# ruff: noqa: E501
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

    assert row == ("0004_exercise_catalog",)

    # A rollback removes only the domain schema and leaves the baseline revision.
    command.downgrade(config, "0001_database_foundation")
    with psycopg.connect(_sync_database_url(_require_test_database_url())) as db:
        revision = db.execute(
            sql.SQL("SELECT version_num FROM {}.alembic_version").format(
                sql.Identifier(isolated_test_schema)
            )
        ).fetchone()
        tables = db.execute(
            """SELECT count(*) FROM information_schema.tables
            WHERE table_schema = %s AND table_name IN
            ('users', 'custom_exercises', 'workout_plans', 'plan_exercises',
             'plan_sets', 'workout_sessions', 'session_exercises', 'session_sets')""",
            (isolated_test_schema,),
        ).fetchone()
    assert revision == ("0001_database_foundation",)
    assert tables == (0,)


def test_workout_schema_supports_plans_sessions_and_owner_isolation(
    isolated_test_schema: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Exercise the migrated schema with a plan, a logged workout, and a second owner."""
    monkeypatch.setenv("DATABASE_URL", _require_test_database_url())
    get_settings.cache_clear()
    config = Config(str(Path(__file__).parents[2] / "alembic.ini"))
    config.cmd_opts = Namespace(x=[f"test_schema={isolated_test_schema}"])
    try:
        command.upgrade(config, "head")
    finally:
        get_settings.cache_clear()

    with psycopg.connect(_sync_database_url(_require_test_database_url())) as db:
        db.execute(sql.SQL("SET search_path TO {}").format(sql.Identifier(isolated_test_schema)))
        first_user = db.execute(
            "INSERT INTO users (display_name, email) VALUES (%s, %s) RETURNING id",
            ("First", "first@example.com"),
        ).fetchone()[0]
        second_user = db.execute(
            "INSERT INTO users (display_name, email) VALUES (%s, %s) RETURNING id",
            ("Second", "second@example.com"),
        ).fetchone()[0]
        custom_exercise = db.execute(
            """INSERT INTO custom_exercises
            (owner_user_id, name, training_type, equipment, body_part, measurement_type)
            VALUES (%s, 'Band Row', 'strength', 'resistance_band', 'back', 'reps') RETURNING id""",
            (first_user,),
        ).fetchone()[0]
        plan = db.execute(
            """INSERT INTO workout_plans (owner_user_id, name)
            VALUES (%s, 'Upper Body') RETURNING id""",
            (first_user,),
        ).fetchone()[0]
        plan_exercise = db.execute(
            """INSERT INTO plan_exercises
            (plan_id,owner_user_id,exercise_order,source_kind,custom_exercise_id,note,
             exercise_name,body_part,equipment,measurement_type)
            VALUES (%s,%s,1,'custom',%s,'Keep shoulders down','Band Row','back','resistance_band','reps') RETURNING id""",
            (plan, first_user, custom_exercise),
        ).fetchone()[0]
        db.execute(
            """INSERT INTO plan_sets
            (plan_exercise_id,set_number,measurement_type,target_reps,target_weight_kg)
            VALUES (%s,1,'reps',10,20.00), (%s,2,'reps',8,25.00)""",
            (plan_exercise, plan_exercise),
        )
        session = db.execute(
            """INSERT INTO workout_sessions (owner_user_id, source_plan_id)
            VALUES (%s, %s) RETURNING id""",
            (first_user, plan),
        ).fetchone()[0]
        session_exercise = db.execute(
            """INSERT INTO session_exercises
            (session_id, owner_user_id, exercise_order, source_kind,
             custom_exercise_id,exercise_name,body_part,equipment,measurement_type,note)
            VALUES (%s,%s,1,'custom',%s,'Band Row','back','resistance_band','reps','Keep shoulders down') RETURNING id""",
            (session, first_user, custom_exercise),
        ).fetchone()[0]
        db.execute(
            """INSERT INTO session_sets
            (session_exercise_id,set_number,measurement_type,target_reps,target_weight_kg,
             actual_reps, actual_weight_kg, status, completed_at)
            VALUES (%s,1,'reps',10,20.00,9,22.50,'completed',now())""",
            (session_exercise,),
        )
        db.execute(
            """UPDATE workout_sessions SET status = 'finished', finished_at = started_at
            + interval '30 minutes', total_time_seconds = 1800 WHERE id = %s""",
            (session,),
        )
        actual = db.execute(
            """SELECT s.actual_reps, s.actual_weight_kg, w.total_time_seconds
            FROM session_sets s JOIN session_exercises e ON e.id = s.session_exercise_id
            JOIN workout_sessions w ON w.id = e.session_id WHERE w.id = %s""",
            (session,),
        ).fetchone()
        assert actual == (9, 22.50, 1800)

        # Composite foreign keys prevent a second user from borrowing private data.
        with pytest.raises(psycopg.errors.ForeignKeyViolation), db.transaction():
            db.execute(
                """INSERT INTO plan_exercises
                (plan_id,owner_user_id,exercise_order,source_kind,custom_exercise_id,
                 exercise_name,body_part,equipment,measurement_type)
                VALUES (%s,%s,2,'custom',%s,'Private','other','other','reps')""",
                (
                    plan,
                    first_user,
                    db.execute(
                        """INSERT INTO custom_exercises
                    (owner_user_id,name,training_type,equipment,body_part,measurement_type)
                    VALUES (%s,'Private','strength','other','other','reps') RETURNING id""",
                        (second_user,),
                    ).fetchone()[0],
                ),
            )
        with pytest.raises(psycopg.errors.CheckViolation), db.transaction():
            db.execute(
                """INSERT INTO plan_exercises
                (plan_id, owner_user_id, exercise_order, source_kind,
                 custom_exercise_id,external_provider,external_exercise_id,
                 exercise_name,body_part,equipment,measurement_type)
                VALUES (%s,%s,2,'custom',%s,'vendor','123','Bad','other','other','reps')""",
                (plan, first_user, custom_exercise),
            )
        with pytest.raises(psycopg.errors.UniqueViolation), db.transaction():
            db.execute(
                """INSERT INTO plan_sets (plan_exercise_id,set_number,measurement_type,target_reps)
                VALUES (%s,1,'reps',12)""",
                (plan_exercise,),
            )
        with pytest.raises(psycopg.errors.CheckViolation), db.transaction():
            db.execute(
                """INSERT INTO session_sets
                (session_exercise_id,set_number,measurement_type,target_reps,status,completed_at)
                VALUES (%s,2,'reps',10,'completed',now())""",
                (session_exercise,),
            )

        # An ad-hoc workout has no source plan and may use an external reference.
        adhoc = db.execute(
            "INSERT INTO workout_sessions (owner_user_id) VALUES (%s) RETURNING id",
            (first_user,),
        ).fetchone()[0]
        external_record = db.execute(
            """INSERT INTO external_exercises
            (provider,external_exercise_id,name,body_part,equipment,attribution)
            VALUES ('exercisedb','vendor-123','Vendor Row','back','cable','ExerciseDB')
            RETURNING id"""
        ).fetchone()[0]
        db.execute(
            """INSERT INTO session_exercises
            (session_id, owner_user_id, exercise_order, source_kind,
             external_provider,external_exercise_id,external_exercise_record_id,
             exercise_name,body_part,equipment,measurement_type)
            VALUES (%s,%s,1,'external','exercisedb','vendor-123',%s,
                    'Vendor Row','back','cable','reps')""",
            (adhoc, first_user, external_record),
        )
        assert db.execute(
            "SELECT source_plan_id FROM workout_sessions WHERE id = %s", (adhoc,)
        ).fetchone() == (None,)
