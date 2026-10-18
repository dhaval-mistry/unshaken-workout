# Workout API developer instructions

**Status: APPROVED on 2026-10-16 and implemented for backend review.**

This document is the approved developer contract. It defines the API behavior,
implementation order, and acceptance tests. Verified results are recorded in the
backend README; wording here remains the implementation baseline.

## Current baseline and language

Unshaken uses FastAPI, PostgreSQL, Alembic, React, and TypeScript. Migration `0002_workout_plans_and_sessions` defines `users`, `custom_exercises`, `workout_plans`, `plan_exercises`, `plan_sets`, `workout_sessions`, `session_exercises`, and `session_sets`. Only health and live ExerciseDB catalog routes exist today; there are no profile, plan, or session APIs. The database already has owner-scoped foreign keys, plan `version`, exercise-level notes, separate planned and actual set measurements, and session start/end fields. It has no authentication, user active flag, session version, or rest-time field. CORS currently allows only `GET`.

The repository has existing modified files and an untracked `0002` migration. The developer must inspect and preserve that work. The current database integration test asserts `0002` is Alembic head; update that test if a later migration becomes head.

An **exercise** is one activity. A **workout plan** is a reusable template containing ordered exercises and planned sets. A **workout session** is one performed workout, started from a plan or created ad hoc. A **set** has one rep count and optional weight. There is no repetition subtable or rep API. Notes are on plan/session exercises, not sets.

This handoff is backend-only. It excludes React work, public signup, invitations, real login, reports, previous-performance views, active rest timers, payments, and vendor-data import. The existing ExerciseDB read APIs remain separate.

## Rules shared by the new APIs

- Prefix all paths below with `/api`. Use UUIDs for local resources and JSON over HTTPS in deployed environments. Serialize timestamps as UTC ISO 8601.
- Resolve the current owner on the server. Never trust `owner_user_id`, email, role, or a user-ID header supplied by the client. An unknown or another owner's resource returns the same `404`.
- List responses have `{items, page, page_size, total}`; default page size 20, maximum 50. Return exercises by `exercise_order` and sets by `set_number`, both beginning at 1.
- Creates return `201` with a `Location` header; reads and updates return `200`; child deletes and custom-exercise archive return `204`. Use `422` for request-schema errors, `404` for missing/unowned resources, `409` for stale versions or invalid state transitions, and `428` for a missing required version precondition. Use a consistent safe error body `{code, message, fields?}`. Do not leak SQL details or secrets.
- Return `ETag: "N"` for plan/session detail, create, and body-bearing mutation responses. Require `If-Match: "N"` for every plan/session mutation after creation, including child changes. A missing header returns `428`; a stale value returns `409` with `code: "version_conflict"`. Increment the parent version exactly once per successful mutation; a failure must change nothing. Add session `version` through an approved migration.
- Input and output weights are kilograms with at most two decimal places. Use PostgreSQL `NUMERIC`, not floating point. The profile's `kg`/`lb` choice is a display preference; do not reinterpret incoming numbers. Zero kilograms is valid. For this first release, each planned set needs `target_reps` and each completed set needs `actual_reps`. Existing duration/distance columns are reserved for a later contract.
- Proposed bounds: display name 1–80 characters; exercise and plan name 1–120; exercise note and custom note at most 2,000; instructions at most 5,000; at most 10 muscle/equipment strings of 1–60 characters; at most 50 exercises per plan/session and 20 sets per exercise; reps 1–999; weight 0–999999.99 kg. Trim user text, reject blank values and unknown fields, and align API checks with existing DB constraints.
- Use one transaction per operation. Deep copy, plan-to-session start, reorder, archive, and finish must either commit completely or leave no changes. Nested operations must prove the full owner → parent → child chain.

## Identity and vendor gates

The owner asked to hold login. For local API development only, seed one user with an idempotent local command and configure its UUID server-side in the ignored local environment. Private routes resolve that user from PostgreSQL. Do **not** add a public `POST /api/users`, accept `X-User-ID`, or accept an owner ID in JSON. The development identity and seed command must refuse to run in staging/production; private endpoints fail closed there until real authentication exists. Tests may override the current-user dependency with two distinct test users. Real authentication and active-account checks are required before inviting members or deploying private APIs. An inactive-account test belongs to that later authentication work unless an `active` field is separately approved now.

Do not persist ExerciseDB IDs in plans/sessions until this subscription's provider confirms ID-retention permission. The first complete journey uses custom exercises. If ID storage is approved later, support a source reference `{source_kind: "external", external_provider: "exercisedb", external_exercise_id}` and validate it through FastAPI. Never copy provider names, descriptions, classifications, instructions, image URLs, or media into the workout tables; never turn provider data into a custom exercise. The existing catalog GET APIs may still serve live provider results.

## Proposed route contract

### Profile

| Method and path | Request | Success and rule |
| --- | --- | --- |
| `GET /me` | None | `200` `{id, display_name, email, preferred_weight_unit, created_at, updated_at}` for the resolved user. |
| `PATCH /me` | `{display_name?, preferred_weight_unit?}`; at least one field | `200` updated profile. Reject ID, email, role, and owner fields. |

User creation is a local seed operation for this stage. Protected invitation/onboarding APIs require a later approved authentication design.

### Private custom exercises

Representation: `{id, name, training_type, muscle_groups, equipment_types, instructions, notes, archived_at, created_at, updated_at}`. `training_type` is `strength`, `functional`, `cardio`, `mobility`, or `other`.

| Method and path | Request | Success and rule |
| --- | --- | --- |
| `GET /custom-exercises` | `page`, `page_size`, optional `include_archived` | `200` owner-only page; archive omitted by default. |
| `POST /custom-exercises` | `{name, training_type, muscle_groups?, equipment_types?, instructions?, notes?}` | `201` created exercise; empty arrays and null optional text allowed. |
| `GET /custom-exercises/{exercise_id}` | None | `200` own exercise, including archived state. |
| `PATCH /custom-exercises/{exercise_id}` | Editable fields; at least one | `200` updated exercise; archived records are read-only. |
| `POST /custom-exercises/{exercise_id}/archive` | None | `204`; repeating archive is safe. Existing plan/session references remain. |

Do not offer hard delete. Archived exercises cannot be newly selected but remain visible through existing references.

### Workout plans

A summary has `{id, name, archived_at, version, exercise_count, created_at, updated_at}`. Detail also has ordered `exercises` with each exercise's source, note, and sets.

| Method and path | Request | Success and rule |
| --- | --- | --- |
| `GET /workout-plans` | `page`, `page_size`, optional `include_archived` | `200` owner-only summaries, active by default. |
| `POST /workout-plans` | `{name}` | `201` empty plan with `version: 1`. Names need not be unique. |
| `GET /workout-plans/{plan_id}` | None | `200` detail and ETag, including ordered children. |
| `PATCH /workout-plans/{plan_id}` | `{name}` and `If-Match` | `200` renamed plan and incremented version. |
| `POST /workout-plans/{plan_id}/duplicate` | Optional `{name}` | `201` independent deep copy, version 1. Read the source consistently within one transaction; reject archived source with `409`. |
| `POST /workout-plans/{plan_id}/archive` | `If-Match`; no body | `200` archived plan and incremented version; repeat with current version is idempotent. |

Archived plans remain explicitly readable, but cannot be edited, duplicated, or used to start a session. No restore or hard-delete route in this stage.

### Exercises within plans

Representation: `{id, exercise_order, source_kind, custom_exercise_id, external_provider, external_exercise_id, note, sets}`. Exactly one source is present. The current API accepts only `source_kind: "custom"`.

| Method and path | Request | Success and rule |
| --- | --- | --- |
| `POST /workout-plans/{plan_id}/exercises` | `If-Match`; `{source_kind: "custom", custom_exercise_id, note?}` | `201` append at next position; increment plan version. Reject unowned/archived custom source and external source while permission gate is closed. |
| `PATCH /workout-plans/{plan_id}/exercises/{item_id}` | `If-Match`; `{note}` | `200` changed exercise-level note; source is immutable. |
| `DELETE /workout-plans/{plan_id}/exercises/{item_id}` | `If-Match` | `204` remove the entry and its sets; compact order; do not delete the underlying custom exercise. |
| `PUT /workout-plans/{plan_id}/exercises/order` | `If-Match`; `{exercise_ids: [UUID, ...]}` | `200` reordered plan detail. Require the exact current ID set, without duplicates or omissions. |

The same custom exercise may appear more than once in a plan. Reordering must avoid collisions with the unique `(plan_id, exercise_order)` constraint and must be transactional.

### Planned sets

Representation: `{id, set_number, target_reps, target_weight_kg}`. Plan version governs each change.

| Method and path | Request | Success and rule |
| --- | --- | --- |
| `POST /workout-plans/{plan_id}/exercises/{item_id}/sets` | `If-Match`; `{target_reps, target_weight_kg?}` | `201` appended set with next number. |
| `PATCH /workout-plans/{plan_id}/exercises/{item_id}/sets/{set_id}` | `If-Match`; `{target_reps?, target_weight_kg?}`; at least one | `200` changed set; explicit null clears optional weight. |
| `DELETE /workout-plans/{plan_id}/exercises/{item_id}/sets/{set_id}` | `If-Match` | `204` delete set and compact later set numbers. |

### Workout sessions

A summary has `{id, name, source_plan_id, status, started_at, finished_at, total_time_seconds, version}`. Detail includes ordered exercises and sets. Status is `in_progress`, `finished`, or `abandoned`.

| Method and path | Request | Success and rule |
| --- | --- | --- |
| `GET /workout-sessions` | `page`, `page_size`, optional `status` | `200` owner-only page, newest first. |
| `POST /workout-sessions` | From plan: `{source_plan_id}`; ad hoc: `{name?}` with no plan | `201` detail and version 1. Copy plan children atomically; ad hoc starts empty. |
| `GET /workout-sessions/{session_id}` | None | `200` detail and ETag. |
| `PATCH /workout-sessions/{session_id}` | `If-Match`; `{name}` | `200` renamed in-progress session. Source plan, timestamps, totals, and status are not editable here. |
| `POST /workout-sessions/{session_id}/finish` | `If-Match`; no body | `200` finished detail, server `finished_at` and elapsed seconds. Require at least one exercise and set and every set completed or skipped; else `409`. |
| `POST /workout-sessions/{session_id}/abandon` | `If-Match`; no body | `200` abandoned detail and server elapsed seconds. Planned sets may remain. |

The server sets `started_at` and calculates nonnegative `total_time_seconds`; do not accept client time or elapsed seconds. Finish/abandon only from `in_progress`; repeating a transition returns `409`. Terminal sessions are read-only. A foreign source plan returns `404`; an archived one returns `409`. Plan-based start copies exercise order, note, planned set values, and custom name snapshot into independent session rows in one transaction. Archived custom exercises already in an active plan may be copied; later plan/custom edits do not rewrite the session.

### Exercises within sessions

Representation: `{id, exercise_order, source_kind, custom_exercise_id, external_provider, external_exercise_id, custom_name_at_start, note, sets}`. Source identity is immutable. Only custom sources may be added while the vendor gate is closed.

| Method and path | Request | Success and rule |
| --- | --- | --- |
| `POST /workout-sessions/{session_id}/exercises` | `If-Match`; custom source and optional note | `201` append to in-progress session and capture the owned active custom exercise's current name. |
| `PATCH /workout-sessions/{session_id}/exercises/{item_id}` | `If-Match`; `{note}` | `200` changed note. |
| `DELETE /workout-sessions/{session_id}/exercises/{item_id}` | `If-Match` | `204` remove item and its sets, compact order. |
| `PUT /workout-sessions/{session_id}/exercises/order` | `If-Match`; `{exercise_ids: [UUID, ...]}` | `200` reordered detail; complete exact permutation required. |

Do not capture vendor names in `custom_name_at_start` or another DB column. All session exercise mutations require `in_progress`.

### Actual session sets

Representation: `{id, set_number, target_reps, target_weight_kg, actual_reps, actual_weight_kg, status, completed_at}`. New status is `planned`.

| Method and path | Request | Success and rule |
| --- | --- | --- |
| `POST /workout-sessions/{session_id}/exercises/{item_id}/sets` | `If-Match`; `{target_reps, target_weight_kg?}` | `201` appended planned set. |
| `PATCH /workout-sessions/{session_id}/exercises/{item_id}/sets/{set_id}` | `If-Match`; planned values, actual values, and/or `status`; at least one | `200` updated set. `completed` requires `actual_reps` and sets `completed_at` server-side. `skipped` or `planned` clears actual values and completion time. Weight alone does not complete a set. |
| `DELETE /workout-sessions/{session_id}/exercises/{item_id}/sets/{set_id}` | `If-Match` | `204` delete set, compact later numbers. |

Each set retains its own actual reps and optional actual weight. Reopening a completed set while the session is in progress clears its actual values and timestamp. No set may change after the session is finished or abandoned.

## Database, CORS, and implementation sequence

Use Alembic for every database change; never run `create_all` on API startup. Add `workout_sessions.version INTEGER NOT NULL DEFAULT 1 CHECK (version > 0)` if session ETags are approved. Rest-time fields are deferred unless the owner chooses them now; if included, specify whether rest belongs to exercises or sets and add matching plan and session columns together. Keep vendor reference columns but do not populate them before ID-retention permission is confirmed. Child deletion needs explicit service behavior because current foreign keys do not declare cascading deletes.

Allow `POST`, `PATCH`, `PUT`, and `DELETE` in CORS only for configured frontend origins; allow `If-Match` and `Content-Type` request headers. Do not use a wildcard origin or expose a provider key. Preserve existing live catalog behavior.

The developer is the sole file writer under `AGENTS.md`. Complete each step and tests before the next. Inspect `git status` before editing and never revert existing work. Add concise comments for business rules; do not weaken tests.

| Step | Implementation | Exit criteria |
| --- | --- | --- |
| 1 | Request-scoped DB access, dev-only current-user dependency/seed, safe errors, transaction/version helpers, CORS. | Local user resolves from DB; production/staging dev identity is rejected; client owner IDs fail; CORS preflight works only for approved origin and methods. |
| 2 | `GET/PATCH /me`. | Allowed fields work; email/owner injection and invalid units fail without partial writes. |
| 3 | Custom-exercise list/create/get/edit/archive. | Two-user isolation, archive preservation, invalid input, and archived selection tests pass. |
| 4 | Plan list/create/get/rename/duplicate/archive and version behavior. | Deep copy is independent; archive and stale-version tests pass; failed copy rolls back. |
| 5 | Plan exercise and set add/edit/remove/reorder. | Exercise and set numbers remain contiguous; notes at exercise level; nested ownership, stale writes, and reordering rollback tests pass. |
| 6 | Session-version migration; list/get/create sessions from plan or ad hoc. | Migration upgrade/downgrade passes in disposable DB; copy is atomic; plan edits do not change started session. |
| 7 | Session rename, exercise/set add/edit/remove/reorder, complete/skip. | Distinct actual reps/weights survive reload; terminal, ownership, and stale-version guards work. |
| 8 | Finish/abandon with server elapsed time. | Empty/incomplete finish is rejected; repeated finish/abandon conflicts; finished session is immutable. |
| 9 | OpenAPI/README and validation; hand off for read-only review. | Docs match implementation; exact test commands, pass/fail/skip counts and limitations are reported. |

## Automated and functional test plan

For **every operation** below, cover successful response shape/status, persistence, schema errors, nested ownership, and rollback where applicable. Use FastAPI route tests, PostgreSQL integration tests with two users, unit tests for validators/business rules, and mock provider tests. Never spend live ExerciseDB quota in automated tests.

| Operation | Required success and failure tests |
| --- | --- |
| `GET/PATCH /me` | Current user and unit, permitted edit, blank/invalid field, owner/email injection, missing dev user, production guard. |
| Custom exercise list/create/get/edit/archive | Pagination and archive filter; all training types; optional arrays/text; blank/oversize/unknown fields; foreign `404`; archived read-only; archive retains referenced entries. |
| Plan list/create/get/edit/archive | Owner list, ordered detail/ETag, valid rename, missing/stale `If-Match`, foreign `404`, archived exclusion and immutability. |
| Plan duplicate | Independent plan/exercise/set IDs and data, archived/foreign source rejection, failed copy rollback. |
| Plan exercise add/edit/delete/reorder | Owned active custom source only, exercise-level note, source immutability, exact-list reorder, duplicate/missing/foreign IDs, contiguous order, no custom-exercise deletion, stale version. |
| Planned set add/edit/delete | Two sets with distinct reps/weights, null optional weight, invalid count/weight, max sets, nested `404`, compact numbering, stale version. |
| Session list/create/get/edit | Newest-first owner list/status filter, ad hoc empty start, atomic plan copy with name/note/sets, plan edits independent, archived/foreign source rejection, timestamps/owner injection rejected, ETag and stale edit. |
| Session exercise add/edit/delete/reorder | Capture owned custom name, note and source immutability, exact permutation, foreign/archived custom rejection, terminal session and stale-version rejection. |
| Session set add/edit/delete | Actual reps/weights differ by set and persist, complete/skip/reopen transitions, completed timestamp, weight-only completion rejected, invalid measures, compact numbering, terminal/stale/foreign rejection. |
| Session finish/abandon | Server elapsed seconds, no finish with zero exercises/sets or planned sets, repeat transition `409`, immutable terminal state, abandon with planned sets. |
| Data integrity and security | Two users cannot access each other's rows; all nested path chains checked; plan/session concurrency permits only one winner for a version; failed deep copy/reorder leaves no partial data; vendor content is never inserted. |

Run Alembic upgrade and downgrade tests, owner composite FK/source-exclusivity/ordering checks, and forced-failure transaction tests against a **dedicated disposable PostgreSQL database**, not the development database. `TEST_DATABASE_URL` must target that database; the existing integration tests skip if it is absent, and a run with skips does not complete this test plan. If a migration after `0002` is added, update the existing Alembic-head assertion. CI already has a disposable PostgreSQL service.

From `backend/`, run and report exact results for `ruff format --check .`, `ruff check .`, `mypy app`, and `pytest` with the dedicated test database configured. Use the existing test setup for the environment-specific command; do not print connection strings or credentials. Run relevant frontend checks only if frontend files change, which is not planned here.

After automation, run this manual **API-only** journey on disposable local data and record observed statuses: seed user → create Band Row → create Upper Body plan → add the exercise with an exercise-level note → add 12 reps/20 kg and 8 reps/25 kg as separate planned sets → duplicate and edit the copy → start a session from the original → record different actual values per set → finish and verify elapsed time and immutable history → start an ad hoc session, add an exercise and set, then abandon. Repeat selected GETs with a second test user to verify list isolation and `404` for foreign IDs. This journey is planned, not yet executed.

## Owner decisions required before implementation

1. **Scope:** Build profile, custom exercises, plans, then sessions. Recommended **yes**. Sessions extend the older Phase 1 document but match the owner's newer logging requirement.
2. **Interim identity:** Seed one local-development user, keep public user creation closed, and fail closed outside development. Recommended **yes**. Real login remains necessary before multiuser use or deployment.
3. **ExerciseDB saves:** Keep the external-reference save gate closed until provider permission to retain IDs is confirmed. Recommended **yes**; custom exercises provide the initial complete journey.
4. **Rest time:** Defer until the owner decides whether rest is per exercise or per set. Recommended **defer**; if included now, approve the plan/session migration fields and payloads first.
5. **Concurrency:** Add session version and require `If-Match` for all plan/session mutations. Recommended **yes**.
6. **Set measurements:** Use kilograms and one rep count per set; require reps in this release, reserve existing duration/distance columns for later. Recommended **yes**.
7. **Finish rule:** Require at least one exercise and set, and all sets completed or skipped; abandon may leave planned sets. Recommended **yes**.

After approval, assign this document to the developer agent. The developer implements one step at a time, reports actual verification and blockers, then releases writer ownership for a separate read-only review. Until approval, this document is only a proposal.
