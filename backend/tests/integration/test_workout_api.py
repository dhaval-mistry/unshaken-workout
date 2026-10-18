# ruff: noqa: E501
"""Database-backed functional coverage for the private workout API journey."""

import os
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from uuid import UUID, uuid4

import psycopg
import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy.engine import make_url

from app.core.settings import Settings, get_settings
from app.infrastructure.exercise_db.client import (
    ExerciseCatalogUnavailableError,
    ExerciseSearchResult,
    NormalizedExercise,
)
from app.main import create_app

_TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    _TEST_DATABASE_URL is None, reason="TEST_DATABASE_URL is required for workout API tests"
)


def _url() -> str:
    assert _TEST_DATABASE_URL is not None
    return _TEST_DATABASE_URL


def _sync_url() -> str:
    return make_url(_url()).set(drivername="postgresql").render_as_string(hide_password=False)


def _assert_disposable_database() -> None:
    """Refuse destructive test setup unless the target is clearly local and test-only."""

    test_url = make_url(_url())
    allowed_hosts = {"localhost", "127.0.0.1", "database"}
    if not test_url.database or not test_url.database.endswith("_test"):
        raise RuntimeError("TEST_DATABASE_URL database name must end with _test")
    if test_url.host not in allowed_hosts:
        raise RuntimeError("TEST_DATABASE_URL must use a local or Compose PostgreSQL host")
    runtime_url = os.getenv("DATABASE_URL")
    if runtime_url and make_url(runtime_url).database == test_url.database:
        raise RuntimeError("TEST_DATABASE_URL must not target the runtime database")


@pytest.fixture
def api_users(monkeypatch: pytest.MonkeyPatch) -> Iterator[tuple[UUID, UUID]]:
    """Migrate and reset the dedicated database, then provide two isolated owners."""

    _assert_disposable_database()
    monkeypatch.setenv("DATABASE_URL", _url())
    get_settings.cache_clear()
    try:
        command.upgrade(Config("alembic.ini"), "head")
    finally:
        get_settings.cache_clear()
    first, second = uuid4(), uuid4()
    with psycopg.connect(_sync_url()) as db:
        db.execute("DROP TRIGGER IF EXISTS test_fail_plan_set_insert_trigger ON plan_sets")
        db.execute(
            "DROP TRIGGER IF EXISTS test_fail_plan_exercise_update_trigger ON plan_exercises"
        )
        db.execute("DROP FUNCTION IF EXISTS test_fail_plan_set_insert()")
        db.execute("DROP FUNCTION IF EXISTS test_fail_plan_exercise_update()")
        db.execute(
            """TRUNCATE session_sets, session_exercises, workout_sessions, plan_sets,
            plan_exercises, workout_plans, custom_exercises, external_exercises, users CASCADE"""
        )
        db.execute(
            """INSERT INTO users (id,display_name,email)
            VALUES (%s,'First','first@example.com'),(%s,'Second','second@example.com')""",
            (first, second),
        )
    yield first, second


def _client(user_id: UUID, *, raise_server_exceptions: bool = True) -> TestClient:
    return TestClient(
        create_app(
            Settings(
                app_environment="development",
                database_url=_url(),
                development_user_id=user_id,
            )
        ),
        raise_server_exceptions=raise_server_exceptions,
    )


def test_destructive_setup_guard_rejects_runtime_database(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DATABASE_URL", _url())
    with pytest.raises(RuntimeError, match="must not target the runtime database"):
        _assert_disposable_database()


def test_complete_plan_and_session_journey(api_users: tuple[UUID, UUID]) -> None:
    first, second = api_users
    with _client(first) as client:
        me = client.patch(
            "/api/me", json={"display_name": "Athlete", "preferred_weight_unit": "lb"}
        )
        assert me.status_code == 200
        assert me.json()["preferred_weight_unit"] == "lb"

        custom = client.post(
            "/api/custom-exercises",
            json={
                "name": " Band Row ",
                "training_type": "strength",
                "equipment": "resistance_band",
                "body_part": "back",
                "measurement_type": "reps",
            },
        )
        assert custom.status_code == 201
        custom_id = custom.json()["id"]

        plan = client.post(
            "/api/workout-plans",
            headers={"Origin": "http://localhost:5173"},
            json={"name": "Upper Body"},
        )
        assert plan.status_code == 201
        assert plan.headers["location"].startswith("/api/workout-plans/")
        assert plan.headers["access-control-expose-headers"] == "ETag, Location"
        plan_id, plan_etag = plan.json()["id"], plan.headers["etag"]
        item = client.post(
            f"/api/workout-plans/{plan_id}/exercises",
            headers={"If-Match": plan_etag},
            json={
                "source_kind": "custom",
                "custom_exercise_id": custom_id,
                "note": "Keep shoulders down",
            },
        )
        assert item.status_code == 201
        item_id, plan_etag = item.json()["id"], item.headers["etag"]
        first_set = client.post(
            f"/api/workout-plans/{plan_id}/exercises/{item_id}/sets",
            headers={"If-Match": plan_etag},
            json={"target_reps": 12, "target_weight_kg": "20.00"},
        )
        assert first_set.status_code == 201
        plan_etag = first_set.headers["etag"]
        second_set = client.post(
            f"/api/workout-plans/{plan_id}/exercises/{item_id}/sets",
            headers={"If-Match": plan_etag},
            json={"target_reps": 8, "target_weight_kg": "25.00"},
        )
        assert second_set.status_code == 201
        assert (
            client.patch(
                f"/api/workout-plans/{plan_id}",
                headers={"If-Match": '"1"'},
                json={"name": "Stale"},
            ).status_code
            == 409
        )

        duplicate = client.post(
            f"/api/workout-plans/{plan_id}/duplicate", json={"name": "Upper Body Copy"}
        )
        assert duplicate.status_code == 201
        assert duplicate.json()["exercises"][0]["id"] != item_id

        session = client.post("/api/workout-sessions", json={"source_plan_id": plan_id})
        assert session.status_code == 201
        session_id, session_etag = session.json()["id"], session.headers["etag"]
        copied_item = session.json()["exercises"][0]
        assert copied_item["exercise_name"] == "Band Row"
        assert [item["target_reps"] for item in copied_item["sets"]] == [12, 8]
        for set_result, reps, weight in zip(
            copied_item["sets"], [11, 7], ["21.50", "26.00"], strict=True
        ):
            response = client.patch(
                f"/api/workout-sessions/{session_id}/exercises/{copied_item['id']}/sets/{set_result['id']}",
                headers={"If-Match": session_etag},
                json={"actual_reps": reps, "actual_weight_kg": weight, "status": "completed"},
            )
            assert response.status_code == 200
            session_etag = response.headers["etag"]
        finished = client.post(
            f"/api/workout-sessions/{session_id}/finish",
            headers={"If-Match": session_etag},
        )
        assert finished.status_code == 200
        assert finished.json()["status"] == "finished"
        assert finished.json()["total_time_seconds"] >= 0
        assert (
            client.patch(
                f"/api/workout-sessions/{session_id}",
                headers={"If-Match": finished.headers["etag"]},
                json={"name": "Too late"},
            ).status_code
            == 409
        )

        adhoc = client.post("/api/workout-sessions", json={"name": "Quick workout"})
        adhoc_id, adhoc_etag = adhoc.json()["id"], adhoc.headers["etag"]
        adhoc_item = client.post(
            f"/api/workout-sessions/{adhoc_id}/exercises",
            headers={"If-Match": adhoc_etag},
            json={"source_kind": "custom", "custom_exercise_id": custom_id},
        )
        abandoned = client.post(
            f"/api/workout-sessions/{adhoc_id}/abandon",
            headers={"If-Match": adhoc_item.headers["etag"]},
        )
        assert abandoned.status_code == 200
        assert abandoned.json()["status"] == "abandoned"

    with _client(second) as other:
        assert other.get(f"/api/workout-plans/{plan_id}").status_code == 404
        assert other.get(f"/api/workout-sessions/{session_id}").status_code == 404
        assert other.get("/api/custom-exercises").json()["total"] == 0


def test_validation_archive_and_finish_guards(api_users: tuple[UUID, UUID]) -> None:
    first, _ = api_users
    with _client(first) as client:
        assert (
            client.post(
                "/api/custom-exercises", json={"name": "x", "training_type": "unknown"}
            ).status_code
            == 422
        )
        custom = client.post(
            "/api/custom-exercises",
            json={
                "name": "Plank",
                "training_type": "functional",
                "equipment": "bodyweight",
                "body_part": "core",
                "measurement_type": "reps",
            },
        )
        exercise_id = custom.json()["id"]
        assert client.post(f"/api/custom-exercises/{exercise_id}/archive").status_code == 204
        assert (
            client.patch(
                f"/api/custom-exercises/{exercise_id}", json={"name": "Changed"}
            ).status_code
            == 409
        )

        session = client.post("/api/workout-sessions", json={})
        assert (
            client.post(
                f"/api/workout-sessions/{session.json()['id']}/finish",
                headers={"If-Match": session.headers["etag"]},
            ).status_code
            == 409
        )


def test_reorder_delete_compaction_and_archive(api_users: tuple[UUID, UUID]) -> None:
    first, _ = api_users
    with _client(first) as client:
        exercise_ids = []
        for name in ("Squat", "Plank"):
            created = client.post(
                "/api/custom-exercises",
                json={
                    "name": name,
                    "training_type": "strength",
                    "equipment": "other",
                    "body_part": "other",
                    "measurement_type": "reps",
                },
            )
            exercise_ids.append(created.json()["id"])
        plan = client.post("/api/workout-plans", json={"name": "Two exercises"})
        plan_id, version = plan.json()["id"], plan.headers["etag"]
        item_ids = []
        for exercise_id in exercise_ids:
            item = client.post(
                f"/api/workout-plans/{plan_id}/exercises",
                headers={"If-Match": version},
                json={"source_kind": "custom", "custom_exercise_id": exercise_id},
            )
            item_ids.append(item.json()["id"])
            version = item.headers["etag"]
        invalid = client.put(
            f"/api/workout-plans/{plan_id}/exercises/order",
            headers={"If-Match": version},
            json={"exercise_ids": [item_ids[0], item_ids[0]]},
        )
        assert invalid.status_code == 422
        reordered = client.put(
            f"/api/workout-plans/{plan_id}/exercises/order",
            headers={"If-Match": version},
            json={"exercise_ids": list(reversed(item_ids))},
        )
        assert reordered.status_code == 200
        assert [item["exercise_order"] for item in reordered.json()["exercises"]] == [1, 2]
        version = reordered.headers["etag"]

        item_id = reordered.json()["exercises"][0]["id"]
        set_ids = []
        for reps in (5, 8):
            created_set = client.post(
                f"/api/workout-plans/{plan_id}/exercises/{item_id}/sets",
                headers={"If-Match": version},
                json={"target_reps": reps},
            )
            set_ids.append(created_set.json()["id"])
            version = created_set.headers["etag"]
        deleted_set = client.delete(
            f"/api/workout-plans/{plan_id}/exercises/{item_id}/sets/{set_ids[0]}",
            headers={"If-Match": version},
        )
        assert deleted_set.status_code == 204
        version = deleted_set.headers["etag"]
        detail = client.get(f"/api/workout-plans/{plan_id}").json()
        assert detail["exercises"][0]["sets"][0]["set_number"] == 1

        deleted_item = client.delete(
            f"/api/workout-plans/{plan_id}/exercises/{item_ids[0]}",
            headers={"If-Match": version},
        )
        assert deleted_item.status_code == 204
        version = deleted_item.headers["etag"]
        assert (
            client.get(f"/api/workout-plans/{plan_id}").json()["exercises"][0]["exercise_order"]
            == 1
        )
        archived = client.post(
            f"/api/workout-plans/{plan_id}/archive", headers={"If-Match": version}
        )
        assert archived.status_code == 200
        repeated = client.post(
            f"/api/workout-plans/{plan_id}/archive",
            headers={"If-Match": archived.headers["etag"]},
        )
        assert repeated.status_code == 200
        assert repeated.headers["etag"] == archived.headers["etag"]
        assert all(row["id"] != plan_id for row in client.get("/api/workout-plans").json()["items"])
        assert any(
            row["id"] == plan_id
            for row in client.get("/api/workout-plans?include_archived=true").json()["items"]
        )


def test_ad_hoc_session_child_mutations_and_set_states(
    api_users: tuple[UUID, UUID],
) -> None:
    first, _ = api_users
    with _client(first) as client:
        custom = client.post(
            "/api/custom-exercises",
            json={
                "name": "Lunge",
                "training_type": "strength",
                "equipment": "bodyweight",
                "body_part": "legs",
                "measurement_type": "reps",
            },
        )
        custom_id = custom.json()["id"]
        updated_custom = client.patch(
            f"/api/custom-exercises/{custom_id}", json={"notes": "User-authored note"}
        )
        assert updated_custom.status_code == 200
        assert client.get(f"/api/custom-exercises/{custom_id}").json()["notes"] == (
            "User-authored note"
        )

        session = client.post("/api/workout-sessions", json={"name": "Ad hoc"})
        session_id, version = session.json()["id"], session.headers["etag"]
        assert (
            client.patch(
                f"/api/workout-sessions/{session_id}", json={"name": "Missing version"}
            ).status_code
            == 428
        )
        renamed = client.patch(
            f"/api/workout-sessions/{session_id}",
            headers={"If-Match": version},
            json={"name": "Leg work"},
        )
        version = renamed.headers["etag"]

        items = []
        for note in ("First", "Second"):
            item = client.post(
                f"/api/workout-sessions/{session_id}/exercises",
                headers={"If-Match": version},
                json={
                    "source_kind": "custom",
                    "custom_exercise_id": custom_id,
                    "note": note,
                },
            )
            items.append(item.json()["id"])
            version = item.headers["etag"]
        reordered = client.put(
            f"/api/workout-sessions/{session_id}/exercises/order",
            headers={"If-Match": version},
            json={"exercise_ids": list(reversed(items))},
        )
        version = reordered.headers["etag"]
        first_item = reordered.json()["exercises"][0]["id"]
        note = client.patch(
            f"/api/workout-sessions/{session_id}/exercises/{first_item}",
            headers={"If-Match": version},
            json={"note": "Updated exercise note"},
        )
        version = note.headers["etag"]
        assert note.json()["note"] == "Updated exercise note"

        workout_set = client.post(
            f"/api/workout-sessions/{session_id}/exercises/{first_item}/sets",
            headers={"If-Match": version},
            json={"target_reps": 10, "target_weight_kg": 0},
        )
        set_id, version = workout_set.json()["id"], workout_set.headers["etag"]
        completed = client.patch(
            f"/api/workout-sessions/{session_id}/exercises/{first_item}/sets/{set_id}",
            headers={"If-Match": version},
            json={"actual_reps": 9, "actual_weight_kg": "12.50", "status": "completed"},
        )
        version = completed.headers["etag"]
        assert completed.json()["completed_at"] is not None
        reopened = client.patch(
            f"/api/workout-sessions/{session_id}/exercises/{first_item}/sets/{set_id}",
            headers={"If-Match": version},
            json={"status": "planned"},
        )
        version = reopened.headers["etag"]
        assert reopened.json()["actual_reps"] is None
        assert reopened.json()["actual_weight_kg"] is None
        assert reopened.json()["completed_at"] is None
        completed_again = client.patch(
            f"/api/workout-sessions/{session_id}/exercises/{first_item}/sets/{set_id}",
            headers={"If-Match": version},
            json={"actual_reps": 8, "status": "completed"},
        )
        version = completed_again.headers["etag"]

        removed = client.delete(
            f"/api/workout-sessions/{session_id}/exercises/{items[0]}",
            headers={"If-Match": version},
        )
        assert removed.status_code == 204
        version = removed.headers["etag"]
        finished = client.post(
            f"/api/workout-sessions/{session_id}/finish", headers={"If-Match": version}
        )
        assert finished.status_code == 200
        assert finished.json()["exercises"][0]["sets"][0]["actual_reps"] == 8


def test_null_patch_fields_nested_ids_and_terminal_guards(
    api_users: tuple[UUID, UUID],
) -> None:
    first, _ = api_users
    with _client(first) as client:
        custom = client.post(
            "/api/custom-exercises",
            json={
                "name": "Press",
                "training_type": "strength",
                "equipment": "barbell",
                "body_part": "chest",
                "measurement_type": "reps",
                "instructions": "  Keep wrists stacked  ",
                "notes": "   ",
            },
        )
        custom_id = custom.json()["id"]
        assert custom.json()["instructions"] == "Keep wrists stacked"
        assert custom.json()["notes"] is None
        normalized_patch = client.patch(
            f"/api/custom-exercises/{custom_id}",
            json={"instructions": "   ", "notes": "  Personal cue  "},
        )
        assert normalized_patch.json()["instructions"] is None
        assert normalized_patch.json()["notes"] == "Personal cue"
        for payload in (
            {"name": None},
            {"training_type": None},
            {"muscle_groups": None},
            {"equipment_types": None},
        ):
            assert (
                client.patch(f"/api/custom-exercises/{custom_id}", json=payload).status_code == 422
            )
        assert client.patch("/api/me", json={"display_name": None}).status_code == 422

        plans = [client.post("/api/workout-plans", json={"name": name}) for name in ("A", "B")]
        first_plan, second_plan = plans
        added = client.post(
            f"/api/workout-plans/{first_plan.json()['id']}/exercises",
            headers={"If-Match": first_plan.headers["etag"]},
            json={
                "source_kind": "custom",
                "custom_exercise_id": custom_id,
                "note": "  Initial cue  ",
            },
        )
        assert added.json()["note"] == "Initial cue"
        assert (
            client.patch(
                f"/api/workout-plans/{first_plan.json()['id']}/exercises/{added.json()['id']}",
                headers={"If-Match": added.headers["etag"]},
                json={},
            ).status_code
            == 422
        )
        assert (
            client.patch(
                f"/api/workout-plans/{second_plan.json()['id']}/exercises/{added.json()['id']}",
                headers={"If-Match": second_plan.headers["etag"]},
                json={"note": "Foreign nested ID"},
            ).status_code
            == 404
        )
        changed_note = client.patch(
            f"/api/workout-plans/{first_plan.json()['id']}/exercises/{added.json()['id']}",
            headers={"If-Match": added.headers["etag"]},
            json={"note": "  Updated cue  "},
        )
        assert changed_note.status_code == 200
        assert changed_note.json()["note"] == "Updated cue"
        cleared_note = client.patch(
            f"/api/workout-plans/{first_plan.json()['id']}/exercises/{added.json()['id']}",
            headers={"If-Match": changed_note.headers["etag"]},
            json={"note": "   "},
        )
        assert cleared_note.json()["note"] is None

        planned_set = client.post(
            f"/api/workout-plans/{first_plan.json()['id']}/exercises/{added.json()['id']}/sets",
            headers={"If-Match": cleared_note.headers["etag"]},
            json={"target_reps": 10},
        )
        set_url = (
            f"/api/workout-plans/{first_plan.json()['id']}/exercises/"
            f"{added.json()['id']}/sets/{planned_set.json()['id']}"
        )
        assert (
            client.patch(
                set_url,
                headers={"If-Match": planned_set.headers["etag"]},
                json={"target_reps": None},
            ).status_code
            == 422
        )
        changed = client.patch(
            set_url,
            headers={"If-Match": planned_set.headers["etag"]},
            json={"target_weight_kg": "12.25"},
        )
        assert changed.status_code == 200
        assert changed.json()["target_reps"] == 10
        assert (
            client.patch(
                f"/api/workout-plans/{first_plan.json()['id']}",
                headers={"If-Match": "invalid"},
                json={"name": "Invalid version"},
            ).status_code
            == 422
        )

        session = client.post("/api/workout-sessions", json={"name": "Terminal"})
        session_item = client.post(
            f"/api/workout-sessions/{session.json()['id']}/exercises",
            headers={"If-Match": session.headers["etag"]},
            json={"source_kind": "custom", "custom_exercise_id": custom_id},
        )
        session_set = client.post(
            f"/api/workout-sessions/{session.json()['id']}/exercises/{session_item.json()['id']}/sets",
            headers={"If-Match": session_item.headers["etag"]},
            json={"target_reps": 5},
        )
        session_set_url = (
            f"/api/workout-sessions/{session.json()['id']}/exercises/"
            f"{session_item.json()['id']}/sets/{session_set.json()['id']}"
        )
        assert (
            client.patch(
                session_set_url,
                headers={"If-Match": session_set.headers["etag"]},
                json={"target_reps": None},
            ).status_code
            == 422
        )
        assert (
            client.patch(
                session_set_url,
                headers={"If-Match": session_set.headers["etag"]},
                json={"status": None},
            ).status_code
            == 422
        )
        skipped = client.patch(
            session_set_url,
            headers={"If-Match": session_set.headers["etag"]},
            json={"status": "skipped"},
        )
        finished = client.post(
            f"/api/workout-sessions/{session.json()['id']}/finish",
            headers={"If-Match": skipped.headers["etag"]},
        )
        assert finished.status_code == 200
        assert (
            client.patch(
                f"/api/workout-sessions/{session.json()['id']}/exercises/{session_item.json()['id']}",
                headers={"If-Match": finished.headers["etag"]},
                json={"note": "Too late"},
            ).status_code
            == 409
        )
        assert (
            client.post(
                f"/api/workout-sessions/{session.json()['id']}/finish",
                headers={"If-Match": finished.headers["etag"]},
            ).status_code
            == 409
        )


def test_concurrent_plan_update_has_one_winner_and_matching_etag(
    api_users: tuple[UUID, UUID],
) -> None:
    first, _ = api_users
    with _client(first) as client:
        plan = client.post("/api/workout-plans", json={"name": "Concurrent"})
    plan_id, version = plan.json()["id"], plan.headers["etag"]

    def update(name: str) -> tuple[int, dict[str, object], str | None]:
        with _client(first) as thread_client:
            response = thread_client.patch(
                f"/api/workout-plans/{plan_id}",
                headers={"If-Match": version},
                json={"name": name},
            )
            return response.status_code, response.json(), response.headers.get("etag")

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(update, ("Winner A", "Winner B")))
    assert sorted(result[0] for result in results) == [200, 409]
    success = next(result for result in results if result[0] == 200)
    assert success[2] == f'"{success[1]["version"]}"'


def test_archived_plan_rejects_edit_duplicate_and_session_start(
    api_users: tuple[UUID, UUID],
) -> None:
    first, _ = api_users
    with _client(first) as client:
        plan = client.post("/api/workout-plans", json={"name": "Archive me"})
        archived = client.post(
            f"/api/workout-plans/{plan.json()['id']}/archive",
            headers={"If-Match": plan.headers["etag"]},
        )
        assert archived.status_code == 200
        assert (
            client.patch(
                f"/api/workout-plans/{plan.json()['id']}",
                headers={"If-Match": archived.headers["etag"]},
                json={"name": "Rejected"},
            ).status_code
            == 409
        )
        assert client.post(f"/api/workout-plans/{plan.json()['id']}/duplicate").status_code == 409
        assert (
            client.post(
                "/api/workout-sessions", json={"source_plan_id": plan.json()["id"]}
            ).status_code
            == 409
        )


def test_session_set_delete_foreign_ids_completion_and_terminal_guards(
    api_users: tuple[UUID, UUID],
) -> None:
    first, _ = api_users
    with _client(first) as client:
        custom = client.post(
            "/api/custom-exercises",
            json={
                "name": "Row",
                "training_type": "strength",
                "equipment": "cable",
                "body_part": "back",
                "measurement_type": "reps",
            },
        )
        custom_id = custom.json()["id"]
        first_session = client.post("/api/workout-sessions", json={"name": "A"})
        first_item = client.post(
            f"/api/workout-sessions/{first_session.json()['id']}/exercises",
            headers={"If-Match": first_session.headers["etag"]},
            json={"source_kind": "custom", "custom_exercise_id": custom_id},
        )
        version = first_item.headers["etag"]
        created_sets = []
        for reps in (8, 12):
            workout_set = client.post(
                f"/api/workout-sessions/{first_session.json()['id']}/exercises/{first_item.json()['id']}/sets",
                headers={"If-Match": version},
                json={"target_reps": reps},
            )
            created_sets.append(workout_set)
            version = workout_set.headers["etag"]
        assert (
            client.patch(
                f"/api/workout-sessions/{first_session.json()['id']}/exercises/{first_item.json()['id']}/sets/{created_sets[0].json()['id']}",
                headers={"If-Match": version},
                json={"actual_weight_kg": "20.00", "status": "completed"},
            ).status_code
            == 422
        )
        deleted = client.delete(
            f"/api/workout-sessions/{first_session.json()['id']}/exercises/{first_item.json()['id']}/sets/{created_sets[0].json()['id']}",
            headers={"If-Match": version},
        )
        assert deleted.status_code == 204
        version = deleted.headers["etag"]
        detail = client.get(f"/api/workout-sessions/{first_session.json()['id']}").json()
        assert detail["exercises"][0]["sets"][0]["set_number"] == 1
        abandoned = client.post(
            f"/api/workout-sessions/{first_session.json()['id']}/abandon",
            headers={"If-Match": version},
        )
        assert abandoned.status_code == 200

        second_session = client.post("/api/workout-sessions", json={"name": "B"})
        second_item = client.post(
            f"/api/workout-sessions/{second_session.json()['id']}/exercises",
            headers={"If-Match": second_session.headers["etag"]},
            json={"source_kind": "custom", "custom_exercise_id": custom_id},
        )
        foreign_set = client.post(
            f"/api/workout-sessions/{second_session.json()['id']}/exercises/{second_item.json()['id']}/sets",
            headers={"If-Match": second_item.headers["etag"]},
            json={"target_reps": 5},
        )
        assert (
            client.patch(
                f"/api/workout-sessions/{second_session.json()['id']}/exercises/{second_item.json()['id']}/sets/{created_sets[1].json()['id']}",
                headers={"If-Match": foreign_set.headers["etag"]},
                json={"status": "skipped"},
            ).status_code
            == 404
        )
        assert (
            client.post(
                f"/api/workout-sessions/{first_session.json()['id']}/abandon",
                headers={"If-Match": abandoned.headers["etag"]},
            ).status_code
            == 409
        )
        assert (
            client.patch(
                f"/api/workout-sessions/{first_session.json()['id']}/exercises/{first_item.json()['id']}/sets/{created_sets[1].json()['id']}",
                headers={"If-Match": abandoned.headers["etag"]},
                json={"status": "skipped"},
            ).status_code
            == 409
        )


def test_concurrent_session_update_has_one_winner_and_matching_etag(
    api_users: tuple[UUID, UUID],
) -> None:
    first, _ = api_users
    with _client(first) as client:
        session = client.post("/api/workout-sessions", json={"name": "Concurrent"})
    session_id, version = session.json()["id"], session.headers["etag"]

    def update(name: str) -> tuple[int, dict[str, object], str | None]:
        with _client(first) as thread_client:
            response = thread_client.patch(
                f"/api/workout-sessions/{session_id}",
                headers={"If-Match": version},
                json={"name": name},
            )
            return response.status_code, response.json(), response.headers.get("etag")

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(update, ("Winner A", "Winner B")))
    assert sorted(result[0] for result in results) == [200, 409]
    success = next(result for result in results if result[0] == 200)
    assert success[2] == f'"{success[1]["version"]}"'


def test_concurrent_session_start_has_one_winner(api_users: tuple[UUID, UUID]) -> None:
    first, _ = api_users

    def start(name: str) -> tuple[int, str]:
        with _client(first) as client:
            response = client.post("/api/workout-sessions", json={"name": name})
            return response.status_code, response.json().get("code", "created")

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(start, ("A", "B")))
    assert sorted(code for code, _ in outcomes) == [201, 409]
    assert {label for _, label in outcomes} == {"created", "active_session_exists"}


def test_plan_rejects_more_than_fifty_exercises(api_users: tuple[UUID, UUID]) -> None:
    first, _ = api_users
    with _client(first) as client:
        custom = client.post(
            "/api/custom-exercises",
            json={
                "name": "Repeat",
                "training_type": "strength",
                "equipment": "other",
                "body_part": "other",
                "measurement_type": "reps",
            },
        )
        plan = client.post("/api/workout-plans", json={"name": "Limit"})
        version = plan.headers["etag"]
        for _ in range(50):
            item = client.post(
                f"/api/workout-plans/{plan.json()['id']}/exercises",
                headers={"If-Match": version},
                json={"source_kind": "custom", "custom_exercise_id": custom.json()["id"]},
            )
            assert item.status_code == 201
            version = item.headers["etag"]
        assert (
            client.post(
                f"/api/workout-plans/{plan.json()['id']}/exercises",
                headers={"If-Match": version},
                json={"source_kind": "custom", "custom_exercise_id": custom.json()["id"]},
            ).status_code
            == 409
        )


def test_database_failures_roll_back_deep_copy_and_reorder(
    api_users: tuple[UUID, UUID],
) -> None:
    """Test-only triggers simulate PostgreSQL failures without production hooks."""

    first, _ = api_users
    with _client(first) as client:
        custom = client.post(
            "/api/custom-exercises",
            json={
                "name": "Rollback",
                "training_type": "strength",
                "equipment": "other",
                "body_part": "other",
                "measurement_type": "reps",
            },
        )
        plan = client.post("/api/workout-plans", json={"name": "Copy source"})
        first_item = client.post(
            f"/api/workout-plans/{plan.json()['id']}/exercises",
            headers={"If-Match": plan.headers["etag"]},
            json={"source_kind": "custom", "custom_exercise_id": custom.json()["id"]},
        )
        source_set = client.post(
            f"/api/workout-plans/{plan.json()['id']}/exercises/{first_item.json()['id']}/sets",
            headers={"If-Match": first_item.headers["etag"]},
            json={"target_reps": 10},
        )
        second_item = client.post(
            f"/api/workout-plans/{plan.json()['id']}/exercises",
            headers={"If-Match": source_set.headers["etag"]},
            json={"source_kind": "custom", "custom_exercise_id": custom.json()["id"]},
        )
        original = client.get(f"/api/workout-plans/{plan.json()['id']}")
        original_total = client.get("/api/workout-plans?include_archived=true").json()["total"]

    with psycopg.connect(_sync_url()) as db:
        db.execute(
            """CREATE FUNCTION test_fail_plan_set_insert() RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN RAISE EXCEPTION 'forced plan set insert failure'; END $$"""
        )
        db.execute(
            """CREATE TRIGGER test_fail_plan_set_insert_trigger BEFORE INSERT ON plan_sets
            FOR EACH ROW EXECUTE FUNCTION test_fail_plan_set_insert()"""
        )
    try:
        with _client(first, raise_server_exceptions=False) as client:
            failed_copy = client.post(f"/api/workout-plans/{plan.json()['id']}/duplicate")
            assert failed_copy.status_code == 500
    finally:
        with psycopg.connect(_sync_url()) as db:
            db.execute("DROP TRIGGER test_fail_plan_set_insert_trigger ON plan_sets")
            db.execute("DROP FUNCTION test_fail_plan_set_insert()")
    with _client(first) as client:
        assert client.get("/api/workout-plans?include_archived=true").json()["total"] == (
            original_total
        )

    with psycopg.connect(_sync_url()) as db:
        db.execute(
            """CREATE FUNCTION test_fail_plan_exercise_update()
            RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN RAISE EXCEPTION 'forced plan exercise update failure'; END $$"""
        )
        db.execute(
            """CREATE TRIGGER test_fail_plan_exercise_update_trigger BEFORE UPDATE ON plan_exercises
            FOR EACH ROW EXECUTE FUNCTION test_fail_plan_exercise_update()"""
        )
    try:
        with _client(first, raise_server_exceptions=False) as client:
            failed_reorder = client.put(
                f"/api/workout-plans/{plan.json()['id']}/exercises/order",
                headers={"If-Match": original.headers["etag"]},
                json={"exercise_ids": [second_item.json()["id"], first_item.json()["id"]]},
            )
            assert failed_reorder.status_code == 500
    finally:
        with psycopg.connect(_sync_url()) as db:
            db.execute("DROP TRIGGER test_fail_plan_exercise_update_trigger ON plan_exercises")
            db.execute("DROP FUNCTION test_fail_plan_exercise_update()")
    with _client(first) as client:
        unchanged = client.get(f"/api/workout-plans/{plan.json()['id']}")
        assert unchanged.headers["etag"] == original.headers["etag"]
        assert [item["id"] for item in unchanged.json()["exercises"]] == [
            first_item.json()["id"],
            second_item.json()["id"],
        ]


def test_openapi_has_response_schemas_and_optional_duplicate_body() -> None:
    app = create_app(Settings(database_url="postgresql+asyncpg://test:test@localhost:1/test"))
    schema = app.openapi()
    plan_get = schema["paths"]["/api/workout-plans/{plan_id}"]["get"]
    assert plan_get["responses"]["200"]["content"]["application/json"]["schema"]["$ref"].endswith(
        "/PlanResponse"
    )
    assert "ProblemResponse" in schema["components"]["schemas"]
    duplicate = schema["paths"]["/api/workout-plans/{plan_id}/duplicate"]["post"]
    assert duplicate["requestBody"].get("required") is not True


def test_filters_limits_and_external_source_gate(api_users: tuple[UUID, UUID]) -> None:
    first, _ = api_users
    with _client(first) as client:
        assert (
            client.post(
                "/api/custom-exercises",
                json={"name": "x" * 121, "training_type": "strength"},
            ).status_code
            == 422
        )
        custom_ids = []
        for name in ("One", "Two", "Three"):
            response = client.post(
                "/api/custom-exercises",
                json={
                    "name": name,
                    "training_type": "strength",
                    "equipment": "other",
                    "body_part": "other",
                    "measurement_type": "reps",
                },
            )
            custom_ids.append(response.json()["id"])
        assert client.post(f"/api/custom-exercises/{custom_ids[-1]}/archive").status_code == 204
        active_page = client.get("/api/custom-exercises?page=1&page_size=1").json()
        assert active_page["total"] == 2
        assert len(active_page["items"]) == 1
        assert client.get("/api/custom-exercises?include_archived=true").json()["total"] == 3

        plan = client.post("/api/workout-plans", json={"name": "Set limit"})
        item = client.post(
            f"/api/workout-plans/{plan.json()['id']}/exercises",
            headers={"If-Match": plan.headers["etag"]},
            json={"source_kind": "custom", "custom_exercise_id": custom_ids[0]},
        )
        version = item.headers["etag"]
        for number in range(20):
            added = client.post(
                f"/api/workout-plans/{plan.json()['id']}/exercises/{item.json()['id']}/sets",
                headers={"If-Match": version},
                json={"target_reps": number + 1},
            )
            assert added.status_code == 201
            version = added.headers["etag"]
        assert (
            client.post(
                f"/api/workout-plans/{plan.json()['id']}/exercises/{item.json()['id']}/sets",
                headers={"If-Match": version},
                json={"target_reps": 21},
            ).status_code
            == 409
        )

        abandoned_session = client.post("/api/workout-sessions", json={"name": "Abandoned"})
        assert (
            client.post(
                f"/api/workout-sessions/{abandoned_session.json()['id']}/abandon",
                headers={"If-Match": abandoned_session.headers["etag"]},
            ).status_code
            == 200
        )
        active_session = client.post("/api/workout-sessions", json={"name": "Active"})
        assert client.get("/api/workout-sessions?status=abandoned").json()["total"] == 1
        in_progress = client.get("/api/workout-sessions?status=in_progress").json()
        assert in_progress["total"] == 1
        assert in_progress["items"][0]["id"] == active_session.json()["id"]


def test_private_routes_fail_closed_outside_development() -> None:
    app = create_app(
        Settings(
            app_environment="production",
            database_url="postgresql+asyncpg://test:test@localhost:1/test",
            development_user_id=uuid4(),
        )
    )
    with TestClient(app) as client:
        response = client.get("/api/me")
    assert response.status_code == 503
    assert response.json()["code"] == "identity_unavailable"


def test_cors_allows_configured_write_methods() -> None:
    app = create_app(
        Settings(
            database_url="postgresql+asyncpg://test:test@localhost:1/test",
            cors_origins=["http://localhost:5173"],
        )
    )
    with TestClient(app) as client:
        response = client.options(
            "/api/workout-plans",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "PATCH",
                "Access-Control-Request-Headers": "if-match,content-type",
            },
        )
    assert response.status_code == 200
    assert "PATCH" in response.headers["access-control-allow-methods"]
    with TestClient(app) as client:
        actual = client.get("/health/live", headers={"Origin": "http://localhost:5173"})
    assert actual.headers["access-control-expose-headers"] == "ETag, Location"


def test_started_session_is_an_immutable_snapshot_of_plan_and_custom_exercise(
    api_users: tuple[UUID, UUID],
) -> None:
    """Later source edits and archival must not rewrite an already-started workout."""

    first, _ = api_users
    with _client(first) as client:
        custom = client.post(
            "/api/custom-exercises",
            json={
                "name": "Band Row",
                "training_type": "strength",
                "equipment": "resistance_band",
                "body_part": "back",
                "measurement_type": "reps",
            },
        )
        custom_id = custom.json()["id"]
        plan = client.post("/api/workout-plans", json={"name": "Upper Body"})
        plan_id = plan.json()["id"]
        item = client.post(
            f"/api/workout-plans/{plan_id}/exercises",
            headers={"If-Match": plan.headers["etag"]},
            json={
                "source_kind": "custom",
                "custom_exercise_id": custom_id,
                "note": "Original cue",
            },
        )
        planned_set = client.post(
            f"/api/workout-plans/{plan_id}/exercises/{item.json()['id']}/sets",
            headers={"If-Match": item.headers["etag"]},
            json={"target_reps": 10, "target_weight_kg": "20.00"},
        )

        started = client.post("/api/workout-sessions", json={"source_plan_id": plan_id})
        assert started.status_code == 201
        session_id = started.json()["id"]

        renamed_custom = client.patch(
            f"/api/custom-exercises/{custom_id}", json={"name": "Renamed Row"}
        )
        assert renamed_custom.status_code == 200
        assert client.post(f"/api/custom-exercises/{custom_id}/archive").status_code == 204
        changed_note = client.patch(
            f"/api/workout-plans/{plan_id}/exercises/{item.json()['id']}",
            headers={"If-Match": planned_set.headers["etag"]},
            json={"note": "Changed later"},
        )
        changed_set = client.patch(
            f"/api/workout-plans/{plan_id}/exercises/{item.json()['id']}/sets/{planned_set.json()['id']}",
            headers={"If-Match": changed_note.headers["etag"]},
            json={"target_reps": 5, "target_weight_kg": None},
        )
        assert changed_set.status_code == 200

        snapshot = client.get(f"/api/workout-sessions/{session_id}").json()
        snapshot_item = snapshot["exercises"][0]
        assert snapshot_item["exercise_name"] == "Band Row"
        assert snapshot_item["note"] == "Original cue"
        assert snapshot_item["sets"][0]["target_reps"] == 10
        assert snapshot_item["sets"][0]["target_weight_kg"] == "20.00"

        # An archived custom exercise already present in an active plan remains usable.
        assert (
            client.post(
                f"/api/workout-sessions/{session_id}/abandon",
                headers={
                    "If-Match": client.get(f"/api/workout-sessions/{session_id}").headers["etag"]
                },
            ).status_code
            == 200
        )
        later_session = client.post("/api/workout-sessions", json={"source_plan_id": plan_id})
        assert later_session.status_code == 201
        assert later_session.json()["exercises"][0]["exercise_name"] == "Band Row"


def test_private_write_contract_rejects_injected_fields_and_bad_preconditions(
    api_users: tuple[UUID, UUID],
) -> None:
    """Client-supplied ownership and malformed versions must fail without writes."""

    first, second = api_users
    with _client(first) as client:
        injected_profile = client.patch("/api/me", json={"email": "changed@example.com"})
        assert injected_profile.status_code == 422
        assert client.get("/api/me").json()["email"] == "first@example.com"

        injected_custom = client.post(
            "/api/custom-exercises",
            json={
                "name": "Injected",
                "training_type": "strength",
                "owner_user_id": str(second),
            },
        )
        assert injected_custom.status_code == 422
        assert client.get("/api/custom-exercises").json()["total"] == 0

        plan = client.post("/api/workout-plans", json={"name": "Safe"})
        malformed = client.patch(
            f"/api/workout-plans/{plan.json()['id']}",
            headers={"If-Match": "1"},
            json={"name": "Should not persist"},
        )
        assert malformed.status_code == 422
        unchanged = client.get(f"/api/workout-plans/{plan.json()['id']}")
        assert unchanged.json()["name"] == "Safe"
        assert unchanged.headers["etag"] == '"1"'


class _CatalogStub:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.search_calls = 0
        self.detail_calls = 0

    async def search(self, **_: object) -> ExerciseSearchResult:
        self.search_calls += 1
        if self.fail:
            raise ExerciseCatalogUnavailableError("provider_error")
        return ExerciseSearchResult(
            items=[
                NormalizedExercise(
                    id="vendor-press",
                    name="Vendor Press",
                    body_parts=["chest"],
                    target_muscles=[],
                    equipment=["barbell"],
                    exercise_type=None,
                    instructions=["not persisted"],
                    media_url="https://provider.invalid/media.gif",
                )
            ],
            total=1,
        )

    async def get_by_id(self, _: str) -> NormalizedExercise:
        self.detail_calls += 1
        if self.fail:
            raise ExerciseCatalogUnavailableError("provider_error")
        return (await self.search()).items[0]


def test_duration_current_cancel_and_latest_performance(
    api_users: tuple[UUID, UUID],
) -> None:
    first, _ = api_users
    with _client(first) as client:
        exercise = client.post(
            "/api/custom-exercises",
            json={
                "name": "Plank",
                "training_type": "functional",
                "equipment": "bodyweight",
                "body_part": "core",
                "measurement_type": "duration",
            },
        )
        plan = client.post("/api/workout-plans", json={"name": "Core"})
        item = client.post(
            f"/api/workout-plans/{plan.json()['id']}/exercises",
            headers={"If-Match": plan.headers["etag"]},
            json={"source_kind": "custom", "custom_exercise_id": exercise.json()["id"]},
        )
        assert (
            client.post(
                f"/api/workout-plans/{plan.json()['id']}/exercises/{item.json()['id']}/sets",
                headers={"If-Match": item.headers["etag"]},
                json={"target_reps": 10},
            ).status_code
            == 422
        )
        planned = client.post(
            f"/api/workout-plans/{plan.json()['id']}/exercises/{item.json()['id']}/sets",
            headers={"If-Match": item.headers["etag"]},
            json={"target_duration_seconds": 60, "target_weight_kg": 0, "rest_seconds": 3600},
        )
        assert planned.status_code == 201
        assert planned.json()["rest_seconds"] == 3600
        session = client.post("/api/workout-sessions", json={"source_plan_id": plan.json()["id"]})
        assert (
            client.post("/api/workout-sessions", json={"name": "second"}).json()["code"]
            == "active_session_exists"
        )
        current = client.get("/api/workout-sessions/current")
        assert current.json()["id"] == session.json()["id"]
        session_item = current.json()["exercises"][0]
        session_set = session_item["sets"][0]
        completed = client.patch(
            f"/api/workout-sessions/{session.json()['id']}/exercises/{session_item['id']}/sets/{session_set['id']}",
            headers={"If-Match": current.headers["etag"]},
            json={"status": "completed", "actual_duration_seconds": 55, "actual_weight_kg": 0},
        )
        assert completed.status_code == 200
        timestamp = completed.json()["completed_at"]
        edited = client.patch(
            f"/api/workout-sessions/{session.json()['id']}/exercises/{session_item['id']}/sets/{session_set['id']}",
            headers={"If-Match": completed.headers["etag"]},
            json={"actual_duration_seconds": 50},
        )
        assert edited.json()["completed_at"] == timestamp
        finished = client.post(
            f"/api/workout-sessions/{session.json()['id']}/finish",
            headers={"If-Match": edited.headers["etag"]},
        )
        assert finished.status_code == 200
        latest = client.get(
            "/api/exercise-performance/latest",
            params={"source_kind": "custom", "custom_exercise_id": exercise.json()["id"]},
        )
        assert latest.json()["item"]["sets"][0]["actual_duration_seconds"] == 50
        assert client.get("/api/workout-sessions/current").json()["code"] == "no_active_session"
        assert (
            client.delete(
                f"/api/workout-sessions/{session.json()['id']}",
                headers={"If-Match": finished.headers["etag"]},
            ).status_code
            == 409
        )
        disposable = client.post("/api/workout-sessions", json={"name": "cancel me"})
        assert (
            client.delete(
                f"/api/workout-sessions/{disposable.json()['id']}",
                headers={"If-Match": disposable.headers["etag"]},
            ).status_code
            == 204
        )
        assert client.get(f"/api/workout-sessions/{disposable.json()['id']}").status_code == 404


def test_catalog_cursor_external_storage_and_outage_fallback(
    api_users: tuple[UUID, UUID],
) -> None:
    first, _ = api_users
    app = create_app(
        Settings(app_environment="development", database_url=_url(), development_user_id=first)
    )
    provider = _CatalogStub()
    app.state.exercise_catalog = provider
    with TestClient(app) as client:
        for name in ("Zulu", "Alpha", "Mike"):
            assert (
                client.post(
                    "/api/custom-exercises",
                    json={
                        "name": name,
                        "training_type": "strength",
                        "equipment": "other",
                        "body_part": "other",
                        "measurement_type": "reps",
                    },
                ).status_code
                == 201
            )
        first_page = client.get(
            "/api/exercise-catalog", params={"source": "custom", "page_size": 2}
        )
        second_page = client.get(
            "/api/exercise-catalog",
            params={"source": "custom", "page_size": 2, "cursor": first_page.json()["next_cursor"]},
        )
        assert [
            item["name"] for item in first_page.json()["items"] + second_page.json()["items"]
        ] == ["Alpha", "Mike", "Zulu"]
        assert provider.search_calls == 0
        assert (
            client.get("/api/exercise-catalog", params={"source": "exercisedb"}).status_code == 200
        )
        with psycopg.connect(_sync_url()) as db:
            assert db.execute("SELECT count(*) FROM external_exercises").fetchone() == (0,)
        plan = client.post("/api/workout-plans", json={"name": "External"})
        selected = client.post(
            f"/api/workout-plans/{plan.json()['id']}/exercises",
            headers={"If-Match": plan.headers["etag"]},
            json={
                "source_kind": "external",
                "external_provider": "exercisedb",
                "external_exercise_id": "vendor-press",
                "measurement_type": "reps",
            },
        )
        assert selected.status_code == 201
        with psycopg.connect(_sync_url()) as db:
            columns = {
                row[0]
                for row in db.execute(
                    "SELECT column_name FROM information_schema.columns WHERE table_name='external_exercises'"
                )
            }
            assert not {"media_url", "instructions", "raw_payload"} & columns
            assert db.execute("SELECT count(*) FROM external_exercises").fetchone() == (1,)
        provider.fail = True
        degraded = client.get("/api/exercise-catalog", params={"source": "exercisedb"})
        assert degraded.status_code == 200
        assert degraded.json()["provider_status"] == "degraded"
        outage_plan = client.post("/api/workout-plans", json={"name": "Stored fallback"})
        failed_selection = client.post(
            f"/api/workout-plans/{outage_plan.json()['id']}/exercises",
            headers={"If-Match": outage_plan.headers["etag"]},
            json={
                "source_kind": "external",
                "external_provider": "exercisedb",
                "external_exercise_id": "not-stored",
                "measurement_type": "reps",
            },
        )
        assert failed_selection.status_code == 503
        with psycopg.connect(_sync_url()) as db:
            assert db.execute("SELECT count(*) FROM external_exercises").fetchone() == (1,)
        assert (
            client.post(
                f"/api/workout-plans/{outage_plan.json()['id']}/exercises",
                headers={"If-Match": outage_plan.headers["etag"]},
                json={
                    "source_kind": "external",
                    "external_provider": "exercisedb",
                    "external_exercise_id": "vendor-press",
                    "measurement_type": "duration",
                },
            ).status_code
            == 201
        )
        duplicate = client.post(f"/api/workout-plans/{plan.json()['id']}/duplicate")
        assert duplicate.status_code == 201


def test_openapi_shared_documentation_is_complete(api_users: tuple[UUID, UUID]) -> None:
    first, _ = api_users
    with _client(first) as client:
        schema = client.get("/openapi.json").json()
    operations = [
        operation
        for item in schema["paths"].values()
        for method, operation in item.items()
        if method in {"get", "post", "patch", "put", "delete"}
    ]
    ids = [operation["operationId"] for operation in operations]
    assert len(ids) == len(set(ids))
    assert all(
        operation.get("summary") and operation.get("description") for operation in operations
    )
    assert "Common API journeys" in schema["info"]["description"]
    assert "26a555" not in str(schema)


def test_openapi_places_routes_in_their_declared_groups(api_users: tuple[UUID, UUID]) -> None:
    first, _ = api_users
    with _client(first) as client:
        schema = client.get("/openapi.json").json()

    declared_tags = {tag["name"] for tag in schema["tags"]}
    used_tags = {
        tag
        for path_item in schema["paths"].values()
        for method, operation in path_item.items()
        if method in {"get", "post", "patch", "put", "delete"}
        for tag in operation.get("tags", [])
    }
    assert declared_tags <= used_tags

    expected_groups = {
        "/api/me": "Profile",
        "/api/custom-exercises": "Custom exercises",
        "/api/exercises": "ExerciseDB",
    }
    for path, path_item in schema["paths"].items():
        expected_tag = next(
            (tag for prefix, tag in expected_groups.items() if path.startswith(prefix)), None
        )
        if expected_tag is None:
            continue
        for method, operation in path_item.items():
            if method in {"get", "post", "patch", "put", "delete"}:
                assert operation["tags"] == [expected_tag]


def test_cors_rejects_unconfigured_origin() -> None:
    app = create_app(
        Settings(
            database_url="postgresql+asyncpg://test:test@localhost:1/test",
            cors_origins=["http://localhost:5173"],
        )
    )
    with TestClient(app) as client:
        response = client.options(
            "/api/workout-plans",
            headers={
                "Origin": "https://untrusted.example",
                "Access-Control-Request-Method": "POST",
            },
        )
    assert response.status_code == 400
    assert "access-control-allow-origin" not in response.headers
