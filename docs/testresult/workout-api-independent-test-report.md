# Workout API independent test report

**Date:** 2026-10-16  
**Role:** Test engineer  
**Result:** PASS with one non-blocking dependency warning

## Outcome

The implemented workout API satisfies the approved contract exercised by the automated and
functional tests. The final full run completed with **55 passed, 0 failed, 0 errors, and 0
skipped**. No production defect was reproduced during this test pass.

The test engineer added three independent regression tests for source snapshot isolation,
ownership-field injection and malformed concurrency headers, and rejection of unconfigured CORS
origins. Production code, migrations, configuration, and dependency manifests were not changed.

Passing automated tests do not negate the separate static-review findings below. The automated
result remains **55 passed, 0 failed, and 0 skipped**.

## Parallel reviewer observations

These are read-only reviewer observations, not failures produced by the executed test suite.

### High — local no-auth API and PostgreSQL ports bind to all interfaces

**Evidence:** [`compose.yaml`](../../compose.yaml:16) publishes PostgreSQL as `5432:5432`, and
[`compose.yaml`](../../compose.yaml:46) starts Uvicorn on `0.0.0.0` before publishing the API as
`8000:8000` at [line 64](../../compose.yaml:64). The temporary identity dependency accepts one
configured development user without authenticating the caller in
[`dependencies.py`](../../backend/app/api/dependencies.py:24).

**Impact:** Another device or process that can reach the host ports may use the API as the
configured development user or connect to PostgreSQL if network and credential conditions allow.

**Recommended correction:** Bind development ports to `127.0.0.1`, avoid publishing PostgreSQL
unless host access is needed, and require real authentication before any shared or deployed use.
Apply host firewall controls as an additional boundary.

### Medium — actual set values can be silently discarded unless status is completed

**Evidence:** [`sessions.py`](../../backend/app/api/routes/sessions.py:491) keeps the current status
when a patch omits `status`; lines 495–496 then clear `actual_reps`, `actual_weight_kg`, and
`completed_at` whenever the resulting status is `planned` or `skipped`.

**Impact:** A client that sends actual reps or weight without also sending `status: "completed"`
receives a successful response, but the submitted actual values are removed.

**Recommended correction:** Reject actual values unless the resulting status is `completed`, or
define that supplying actual reps automatically completes the set. Add a regression test for the
chosen behavior.

### Medium — database constraints are weaker than the API set contract

**Evidence:** Planned and session `target_reps` are nullable in
[`0002_workout_plans_and_sessions.py`](../../backend/migrations/versions/0002_workout_plans_and_sessions.py:149)
and [line 255](../../backend/migrations/versions/0002_workout_plans_and_sessions.py:255). The completed
result constraint at [lines 309–311](../../backend/migrations/versions/0002_workout_plans_and_sessions.py:309)
allows a completed set without `actual_reps` when an actual duration or distance exists. The
approved API contract currently requires target reps and requires actual reps for completion.

**Impact:** Direct database writers or future code paths can create rows that the current API would
reject, weakening data integrity and making API serialization assumptions less reliable.

**Recommended correction:** Add an approved migration that enforces the current contract at the
database boundary, or explicitly revise the contract and response models before enabling
duration/distance workouts.

### Low — editing an already completed set changes `completed_at`

**Evidence:** [`sessions.py`](../../backend/app/api/routes/sessions.py:497) assigns the current time
whenever the resulting status is `completed`, including patches to a set that was already
completed.

**Impact:** Correcting weight or reps rewrites the original completion timestamp, reducing audit
accuracy and changing workout timing metadata unexpectedly.

**Recommended correction:** Set `completed_at` only when transitioning from a non-completed state
to `completed`; preserve the existing value for edits while already completed.

### Low — plan and session detail use N+1 set queries

**Evidence:** [`plans.py`](../../backend/app/api/routes/plans.py:81) and
[`sessions.py`](../../backend/app/api/routes/sessions.py:79) loop through exercises and run a
separate set query for each exercise.

**Impact:** Detail requests perform one additional database query per exercise. The current maximum
of 50 exercises can therefore produce substantial avoidable query overhead.

**Recommended correction:** Fetch all child sets in one query and group them by exercise ID, or use
a joined/aggregated query while preserving deterministic order.

## Scope verified

- Profile read/update and rejection of email or owner injection.
- Custom exercise create, list, read, update, archive, pagination, validation, ownership, and
  preservation of existing references.
- Workout plan create, list, read, rename, duplicate, archive, exercise ordering, exercise notes,
  planned sets, compaction after deletes, limits, ownership, and rollback behavior.
- Workout session creation from a plan and ad hoc, read/list/filter/rename, exercise ordering,
  actual sets, complete/skip/reopen, finish, abandon, terminal immutability, and elapsed time.
- `ETag`/`If-Match`, missing and malformed preconditions, stale writes, and concurrent update
  winner behavior for plans and sessions.
- Plan-to-session snapshots: later changes to a plan or custom exercise do not rewrite a started
  session. An archived custom exercise already in an active plan can still be copied into a new
  session, as required.
- Two-user isolation, nested owner/parent/child path checks, safe error behavior, request field
  validation, CORS, OpenAPI response schemas, and `Location`/`ETag` response headers.
- ExerciseDB persistence gate: API payloads accept custom sources only; duplicate/start operations
  reject database-injected external references and roll back partial writes.
- All 46 documented application operations were present in OpenAPI, including 33 profile/custom
  exercise/plan/session operations, 11 ExerciseDB catalog operations, and 2 health operations.

## PostgreSQL and migration verification

Tests used a dedicated local Compose database named `unshaken_api_test`. The safety guard required
a local/Compose host, required the database name to end in `_test`, and rejected the runtime
database. No development or production data was used.

The tests verified:

- Alembic upgrade through `0003_session_version` and downgrade to
  `0001_database_foundation` in an isolated schema.
- The eight domain tables, session version column, positive-version checks, and migration head.
- Owner-scoped composite foreign keys for plan/session relationships and private custom exercises.
- Custom-versus-external source exclusivity checks.
- Unique exercise order and set number constraints, positive numbering, measurement checks, and
  completed-set consistency.
- Independent planned and actual reps/weights, exercise-level notes, session name snapshots,
  ordered children, and server-owned session completion fields.
- Atomic deep copy, reorder, plan-to-session copy, and failure rollback behavior.
- Optimistic locking under concurrent plan and session writes.

The disposable database was removed after testing.

## Functional API journey

`test_complete_plan_and_session_journey` was executed separately through FastAPI's HTTP test
client against PostgreSQL. It passed the following journey: update profile, create Band Row,
create Upper Body, add an exercise-level note, add two distinct planned sets, reject a stale edit,
duplicate the plan, start a session, record different actual reps and weights, finish, reject a
terminal edit, start an ad hoc session, add an exercise, abandon it, and verify a second user's
isolation.

## Exact commands and results

All commands ran from the repository root unless stated otherwise.

| Command | Exit | Result |
| --- | ---: | --- |
| `Get-Content AGENTS.md; Get-Content docs/workout-api-implementation-plan.md; git status --short; rg --files backend/tests backend/migrations backend/app \| Sort-Object` | 0 | Read rules, contract, status, and file inventory. |
| `Get-Content compose.yaml; Get-Content backend/tests/conftest.py; Get-Content backend/tests/integration/test_database_foundation.py; Get-Content backend/pyproject.toml` | 0 | Inspected test/database configuration. |
| `docker compose ps` | 0 | Database healthy; backend running. |
| `docker compose exec -T database sh -c 'dropdb --if-exists -U "$POSTGRES_USER" unshaken_test_engineer && createdb -U "$POSTGRES_USER" unshaken_test_engineer'` | 0 | Created an isolated database; its name did not meet the existing `_test` guard. |
| `docker compose exec -T backend ruff format --check .` | 0 | 34 files already formatted. |
| `docker compose exec -T backend ruff check .` | 0 | All checks passed. |
| `docker compose exec -T backend mypy app` | 0 | No issues in 22 source files. |
| `docker compose exec -T backend sh -c 'TEST_DATABASE_URL="${DATABASE_URL%/*}/unshaken_test_engineer" pytest'` | 1 | 39 passed, 1 failed, 12 setup errors. The test-only safety guard correctly rejected the database name because it did not end in `_test`; no application failure was involved. |
| `docker compose exec -T database sh -c 'dropdb --if-exists -U "$POSTGRES_USER" unshaken_test_engineer && dropdb --if-exists -U "$POSTGRES_USER" unshaken_api_test && createdb -U "$POSTGRES_USER" unshaken_api_test'` | 0 | Removed the misnamed database and created the correctly guarded disposable database. |
| `docker compose exec -T backend sh -c 'TEST_DATABASE_URL="${DATABASE_URL%/*}/unshaken_api_test" pytest'` | 0 | Baseline: 52 passed, 0 skipped, 1 warning. |
| `rg -n "^@router\|^async def\|^def test_" backend/app/api/routes backend/tests/integration/test_workout_api.py backend/tests/integration/test_database_foundation.py; Get-Content backend/migrations/versions/0002_workout_plans_and_sessions.py; Get-Content backend/migrations/versions/0003_session_version.py` | 0 | Audited route/test coverage and migration definitions. |
| `Get-Content backend/tests/integration/test_workout_api.py; Get-Content backend/app/api/models.py; Get-Content backend/app/api/dependencies.py; Get-Content backend/app/api/workout_common.py` | 0 | Inspected existing tests, models, identity, concurrency, and ordering helpers. |
| `Get-Content backend/app/api/routes/profile_custom.py; Get-Content backend/app/api/routes/plans.py; Get-Content backend/app/api/routes/sessions.py` | 0 | Inspected all private workout route implementations. |
| `docker compose exec -T backend ruff format tests/integration/test_workout_api.py` | 0 | Added test file already formatted. |
| `docker compose exec -T backend sh -c 'TEST_DATABASE_URL="${DATABASE_URL%/*}/unshaken_api_test" pytest tests/integration/test_workout_api.py -q'` | 0 | 19 passed, 1 warning. |
| `docker compose exec -T backend python -c "from app.main import create_app; from app.core.settings import Settings; a=create_app(Settings(database_url='postgresql+asyncpg://test:test@localhost:1/test')); paths=a.openapi()['paths']; ops=[(m.upper(),p) for p,v in paths.items() for m in v if m in {'get','post','patch','put','delete'}]; print(len(ops)); print('\\n'.join(f'{m} {p}' for m,p in ops))"` | 0 | 46 operations found and listed. |
| `docker compose exec -T backend sh -c 'TEST_DATABASE_URL="${DATABASE_URL%/*}/unshaken_api_test" pytest tests/integration/test_workout_api.py::test_complete_plan_and_session_journey -vv'` | 0 | Functional journey: 1 passed, 1 warning. |
| `docker compose exec -T backend ruff format --check .` | 0 | Final: 34 files already formatted. |
| `docker compose exec -T backend ruff check .` | 0 | Final: all checks passed. |
| `docker compose exec -T backend mypy app` | 0 | Final: no issues in 22 source files. |
| `docker compose exec -T backend sh -c 'TEST_DATABASE_URL="${DATABASE_URL%/*}/unshaken_api_test" pytest'` | 0 | Final: **55 passed, 0 failed, 0 skipped, 1 warning** in 10.19 seconds. |
| `git diff -- backend/tests/integration/test_workout_api.py; git status --short` | 0 | Confirmed the shared worktree state and test-engineer file scope. |
| `docker compose exec -T database sh -c 'dropdb --if-exists -U "$POSTGRES_USER" unshaken_api_test'` | 0 | Removed the disposable test database. |
| `rg -n "ports:\|target_reps.*nullable=True\|actual_reps.*nullable=True\|status <> 'completed'\|desired in\|desired == \"completed\"\|completed_at\|for exercise in exercises\|for exercise in source_exercises\|for exercise in" compose.yaml backend/migrations/versions/0002_workout_plans_and_sessions.py backend/app/api/routes/plans.py backend/app/api/routes/sessions.py` | 2 | Reviewer-evidence search had a shell quoting error; no files changed. |
| `rg -n "ports:\|5432:5432\|8000:8000" compose.yaml; rg -n "target_reps\|actual_reps\|completed_result" backend/migrations/versions/0002_workout_plans_and_sessions.py; rg -n "desired\|completed_at" backend/app/api/routes/sessions.py; rg -n "for exercise in exercises\|for exercise in source_exercises\|plan_detail\|session_detail" backend/app/api/routes/plans.py backend/app/api/routes/sessions.py` | 0 | Located database, set-state, and N+1 review evidence. |
| `rg -n "app_environment != \"development\"\|development_user_id\|--host\|ports:" backend/app/api/dependencies.py compose.yaml` | 2 | Reviewer-evidence search had a shell quoting error; no files changed. |
| `rg -n 'app_environment\|development_user_id' backend/app/api/dependencies.py; rg -n -- '--host\|ports:' compose.yaml` | 0 | Located development identity and network-binding evidence. |
| `git diff --check -- docs/testresult/workout-api-independent-test-report.md` | 0 | Report contains no whitespace errors. |

## Failures and bugs

No production failures or bugs were found in the final run.

The one unsuccessful full test invocation was a test-environment naming mistake. The safety guard
worked as designed and prevented destructive setup. The run was repeated against a correctly
named disposable database and passed without failures or skips.

## Observations and remaining risks

1. **Low — dependency deprecation warning.** Every pytest run reported that Starlette's test client
   imports the deprecated `anyio.abc.BlockingPortal` alias. This does not affect current behavior.
   Track it during a future dependency upgrade.
2. **Expected deployment blocker — development identity only.** The private APIs intentionally fail
   closed outside development. Real authentication and active-account enforcement remain required
   before deployment or invited multiuser use.
3. **Expected provider limitation — no live ExerciseDB call.** Automated catalog tests use mocked
   provider responses so they do not expose a key or consume quota. The existing live local check
   was outside this independent run. Vendor content and media persistence remain gated.
4. **Frontend checks not applicable.** This change is backend-only. Responsive layout, keyboard
   navigation, focus behavior, and browser accessibility checks require a future React interface.

## Files added or changed by the test engineer

- `backend/tests/integration/test_workout_api.py` — three additional independent regression tests.
- `docs/testresult/workout-api-independent-test-report.md` — this report.

