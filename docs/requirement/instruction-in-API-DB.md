# Unshaken API and database requirements for exercise selection and workout logging

**Status:** Draft for owner review. Do not implement until the owner approves this document.

## Owner quick view

> This section is only a short explanation for the owner. Developers must follow the detailed requirements and acceptance criteria below.

This proposal adds:

- One exercise list containing private custom exercises and live ExerciseDB exercises.
- Stable plan/session exercise names even when ExerciseDB is unavailable.
- One equipment category and one body part per custom exercise.
- Either repetitions or duration for each exercise; weight remains optional.
- A default 120-second rest after every set, individually adjustable.
- Only one in-progress workout per user.
- Permanent cancellation of an in-progress workout.
- The single most recent finished performance for an exercise.
- Plan summaries and details with enough exercise information for the referenced workflows.
- Plain-language Swagger descriptions, examples, errors, and normal call sequences for every API.

The proposal adds one table for selected ExerciseDB records and changes existing exercise and set tables. It stores no image, video, media address, or media bytes.

## 1. Scope

### Included

- Unified source-aware exercise selection.
- Search, alphabetical ordering, and filters.
- Stable Unshaken equipment, body-part, and measurement options.
- Minimum non-media information for selected ExerciseDB exercises.
- Custom or ExerciseDB exercises in plans and active sessions.
- Exercise information and last-performed values in plan responses.
- Latest previous performance.
- Per-set rest time.
- Repetition-based and duration-based sets, with optional weight.
- One in-progress workout per user and a current-workout endpoint.
- Permanent cancellation of an in-progress session.
- Complete Swagger/OpenAPI documentation.
- Relevant API/database corrections from the independent review.

### Not included

- React components, layouts, or styling.
- Images, videos, GIFs, media URLs, or custom uploads.
- Built-in/example plans.
- Distance-based exercises.
- Server-persisted rest countdown state.
- Multiple simultaneous active workouts for one user.
- Bulk ExerciseDB import or storage during normal browsing.
- ExerciseDB instructions, raw payloads, target lists, or other unnecessary vendor fields.
- Authentication implementation, reports, charts, or personal records.

## 2. Terminology

- **Custom exercise:** private exercise created by the current user.
- **External exercise:** exercise supplied by ExerciseDB.
- **Equipment:** the custom exercise category, such as barbell or dumbbell.
- **Body part:** one controlled body-area value.
- **Measurement type:** `reps` or `duration`.
- **Exercise occurrence:** an exercise placed in one plan or session.
- **Previous performance:** the latest occurrence of that exercise in a finished session.
- **Rest seconds:** planned rest after one set; default 120.
- **Snapshot:** minimum exercise display information copied into a plan/session so it remains readable after source changes or provider outages.

## 3. Controlled values

Approval of this document approves these initial keys. APIs return both key and readable label.

### Equipment/category

`barbell`, `dumbbell`, `kettlebell`, `resistance_band`, `cable`, `machine`, `bodyweight`, `cardio_machine`, `medicine_ball`, `suspension_trainer`, `other`.

### Body part

`full_body`, `chest`, `back`, `shoulders`, `arms`, `core`, `glutes`, `legs`, `calves`, `cardio`, `mobility`, `other`.

### Measurement type

- `reps`: sets record repetitions and may record weight.
- `duration`: sets record seconds and may record weight.

Distance is not accepted. ExerciseDB values must be mapped to these internal values behind the provider adapter. Unknown provider values map to `other`.

## 4. Shared API rules

- Scope private data to the server-identified user; never accept `owner_user_id` from a client.
- Missing and other-owner resources both return `404`.
- Use UTC timestamps and kilograms with at most two decimals.
- Default list size is 20; maximum is 50.
- Trim text, reject blank required values, and reject unknown fields with `422`.
- Keep existing `ETag`/`If-Match` rules for plan/session mutations.
- Missing required `If-Match` returns `428`; stale values return `409 version_conflict`.
- Failed mutations change no rows and do not increment parent versions.
- Keep the safe `{code, message, fields?}` error shape.
- Never expose provider keys/URLs, raw provider errors, SQL errors, or stack traces.

## 5. New APIs

### 5.1 `GET /api/exercise-options`

**Purpose:** Return stable Unshaken options for custom-exercise creation and filters.

**Response fields:**

- `equipment`: list of `{key, label}`.
- `body_parts`: list of `{key, label}`.
- `measurement_types`: list of `{key, label}`.

**Rules:** Return `200`, make no database/provider call, and allow public caching. Swagger must say equipment is the custom-exercise category.

### 5.2 `GET /api/exercise-catalog`

**Purpose:** Return one source-aware alphabetical list containing the current user’s custom exercises and ExerciseDB exercises.

**Query fields:**

| Field | Rule |
| --- | --- |
| `query` | Optional case-insensitive name search, 1–100 characters. |
| `body_part` | Optional approved internal key. |
| `equipment` | Optional approved internal key. |
| `measurement_type` | Optional `reps` or `duration`. Live external items have no type until selection. |
| `source` | `all`, `custom`, or `exercisedb`; default `all`. |
| `cursor` | Optional opaque continuation token. |
| `page_size` | 1–50; default 20. |

**Item fields:**

- `source_kind`: `custom` or `external`.
- Exactly one source identifier: `custom_exercise_id`, or `external_provider` plus `external_exercise_id`.
- `name`, `body_part`, `equipment`.
- `measurement_type`; null for a live external result until selection.
- `measurement_type_required_on_selection`.
- `is_archived` (always false for selectable results).
- `provider_attribution` for external items, otherwise null.

**Response metadata:** `page_size`, `next_cursor`, and `provider_status` (`available`, `degraded`, or `not_requested`). Do not return an unreliable total.

**Ordering/pagination:**

- Sort by normalized case-insensitive name, then source and stable identifier.
- Do not return duplicates.
- The opaque cursor preserves custom/provider offsets and a filter signature.
- A malformed cursor or one reused with different filters returns `422 invalid_cursor`.
- Fetch provider pages only in bounded batches; never import the whole provider catalog.

**Provider outage behavior:**

- `source=custom` makes no ExerciseDB request.
- On provider failure, return custom items and locally stored external records with `provider_status: degraded`.
- Return `200` when useful degraded results exist.
- Return `503 catalog_unavailable` only for `source=exercisedb` when no local results can satisfy the request.
- Never claim degraded results are the complete provider catalog.
- Browsing alone must not persist an external record.

### 5.3 `GET /api/exercise-performance/latest`

**Purpose:** Return the current user’s single most recent finished performance for one exercise.

Use exactly one source:

- Custom: `source_kind=custom&custom_exercise_id=<UUID>`.
- External: `source_kind=external&external_provider=exercisedb&external_exercise_id=<ID>`.

Mixed or incomplete source fields return `422`.

**Response:** `{item: null}` when no history exists, otherwise item includes session ID/name, `finished_at`, session-exercise ID, exercise name, measurement type, and ordered sets with reps or duration, optional weight, and status.

**Rules:**

- Only `finished` sessions count.
- Select by `finished_at DESC`, then session ID for a stable tie.
- If the exercise occurs twice in that session, return the occurrence with highest exercise order.
- Include skipped sets with null actual values.
- Ignore active and abandoned sessions.
- A foreign custom exercise returns `404`.
- Use session snapshots and never call ExerciseDB.

### 5.4 `GET /api/workout-sessions/current`

**Purpose:** Restore the user’s only in-progress workout.

- Return `200` with full session detail and ETag when present.
- Return `404 no_active_session` when absent.
- Register this route before `/{session_id}`.

### 5.5 `DELETE /api/workout-sessions/{session_id}`

**Purpose:** Permanently cancel one in-progress workout.

- Require `If-Match` and no request body.
- Return `204` after deleting the session, exercises, and sets atomically.
- Return `404` for missing/foreign records.
- Return `409 terminal_session` for finished or abandoned sessions.
- Return `409 version_conflict` or `428 precondition_required` as applicable.
- Retain the existing abandon endpoint as a different action that preserves history.
- A retry after successful deletion returns `404`.

## 6. Updated APIs

### 6.1 Custom exercises

Replace plural free-form classifications with:

- `equipment`: one approved equipment key.
- `body_part`: one approved body-part key.
- `measurement_type`: `reps` or `duration`.

Keep `training_type` as a separate existing field (`strength`, `functional`, `cardio`, `mobility`, `other`). Do not merge it with equipment.

#### `POST /api/custom-exercises`

Required: `name`, `training_type`, `equipment`, `body_part`, `measurement_type`. Optional: `instructions`, `notes`.

Remove `muscle_groups` and `equipment_types` from the new contract after migration.

#### `PATCH /api/custom-exercises/{exercise_id}`

Accept the same editable fields. Measurement type may change only when the exercise is not referenced by a plan or active session; otherwise return `409 exercise_in_use`. Finished snapshots never change. Archived exercises remain read-only.

#### `GET /api/custom-exercises`

Add:

- `query` name search.
- `equipment`, `body_part`, and `measurement_type` filters.
- `sort`: `name_asc`, `name_desc`, or `created_desc`; default `name_asc`.
- Existing archive and pagination fields.

Use normalized name and ID as stable ordering keys.

### 6.2 Plan summaries and details

#### `GET /api/workout-plans`

Add `query` name search and `sort` (`updated_desc`, `name_asc`, `last_performed_desc`). Add:

- `last_performed_at`: latest finished session time for this plan, or null.
- `exercise_preview`: first three exercises, each with name, set count, and measurement type.

Derive last-performed; do not add a plan column. Use bounded SQL rather than one query per plan/exercise.

#### `GET /api/workout-plans/{plan_id}`

Add `last_performed_at`. Each exercise includes source identifiers, `exercise_name`, `body_part`, `equipment`, `measurement_type`, note, and ordered sets. Load all plan sets in one query and group them in memory.

#### `POST /api/workout-plans/{plan_id}/exercises`

Accept a discriminated source request.

Custom request: `source_kind`, `custom_exercise_id`, optional note. Verify owned/active custom exercise and copy its display fields and measurement type into a plan snapshot.

External request: `source_kind`, `external_provider: exercisedb`, `external_exercise_id`, required `measurement_type`, optional note.

For external selection:

- Reuse a stored external record when present.
- Otherwise fetch it through the adapter and store only approved fields.
- Provider failure during first selection returns `503` and writes nothing.
- Never accept name/body part/equipment from the client.
- Never store media, instructions, or raw payloads.
- Copy approved display values and chosen measurement type into the plan snapshot.

Plan duplication copies all snapshots, sets, measurement types, and rest without provider calls.

### 6.3 Planned sets

Update plan-set create/PATCH fields based on the parent exercise.

For `reps`: required `target_reps` (1–999), optional `target_weight_kg`, `rest_seconds` default 120. Duration must be null/absent.

For `duration`: required `target_duration_seconds` (1–86,400), optional weight, rest default 120. Reps must be null/absent.

- Rest range is 0–3600 seconds.
- Weight may accompany either type.
- Reject distance.
- Return measurement type, both measurement fields (unused one null), weight, and rest.
- Rest applies after every set, including between exercises. Clients do not start rest after the final set of the workout. No countdown state is persisted.

### 6.4 Session creation/detail/exercises

#### `POST /api/workout-sessions`

- Return `409 active_session_exists` if the owner already has an active session.
- Rely on a database partial unique index for concurrent requests and map its conflict to the same response.
- From a plan, copy display snapshots, measurement types, notes, sets, and rest without calling ExerciseDB.
- Empty sessions remain supported.

#### Session detail

Each exercise includes name, body part, equipment, measurement type, identifiers, note, and sets. Each set includes target/actual reps and duration, optional weight, rest, status, and completion time. Load all sets in one query.

#### Add session exercise

Use the same custom/external rules as plan exercise creation. Copy display information into the session snapshot and never trust client-submitted display fields.

### 6.5 Session sets

Session-set creation uses the same target/rest validation as plan sets.

For a completed `reps` set: require actual reps 1–999; actual duration must be null. For completed `duration`: require actual seconds 1–86,400; actual reps must be null. Actual weight is optional for either.

- Planned/skipped sets must have all actual fields null.
- If actual values are submitted while resulting status is planned/skipped, return `422 actual_values_require_completed`; never silently discard input.
- Reopening a completed set clears actual values and completion time.
- Skipping clears actual values and completion time.
- First completion sets server `completed_at`.
- Editing values while already completed preserves the original timestamp.
- Finished and abandoned sessions remain read-only.

## 7. Selected ExerciseDB persistence

Store an external record only after selection for a plan or active session:

- Provider `exercisedb` and external ID.
- Normalized name.
- One normalized body part and equipment value.
- Attribution text.
- First-selected and last-validated timestamps.

Do not store images, media addresses, instructions, targets, raw JSON, or credentials. Normal plan/session reads use snapshots and never call ExerciseDB. Live browsing may update an existing stored record, but must not rewrite existing plan/session snapshots. No background bulk refresh.

The owner approves this requested behavior, but provider-specific storage permission remains unclear and must be confirmed before public deployment.

## 8. PostgreSQL changes

All changes require a new Alembic migration after `0003_session_version`.

### 8.1 New `external_exercises` table

| Column | Type/rule |
| --- | --- |
| `id` | UUID primary key. |
| `provider` | Required text; initially `exercisedb`. |
| `external_exercise_id` | Required, trimmed, maximum 100. |
| `name` | Required nonblank VARCHAR(120). |
| `body_part` | Required approved internal key. |
| `equipment` | Required approved internal key. |
| `attribution` | Required safe display text. |
| `first_selected_at`, `last_validated_at` | Required timezone timestamps. |
| `created_at`, `updated_at` | Required timezone timestamps. |

Add unique `(provider, external_exercise_id)`, value checks, and a case-insensitive name index. Do not add owner, media, or raw payload columns.

### 8.2 `custom_exercises`

Add required `equipment`, `body_part`, and `measurement_type`. Transition existing arrays as follows:

1. Add new columns nullable.
2. Map exactly one recognized existing value.
3. Missing, multiple, or unknown values become `other`.
4. Existing exercises become `measurement_type=reps`.
5. Add NOT NULL/check constraints.
6. Remove old `equipment_types` and `muscle_groups` after validation.
7. Downgrade recreates arrays from the single values and documents that discarded extra legacy values cannot be restored.

Add owner/name index `(owner_user_id, lower(name), id)`.

### 8.3 `plan_exercises` and `session_exercises`

Add to both:

- Nullable `external_exercise_record_id` FK.
- Required snapshot `exercise_name`, `body_part`, `equipment`, `measurement_type` after backfill.
- Source checks ensuring exactly one valid custom or external source.
- Unique `(id, measurement_type)` for composite set foreign keys.

Backfill custom occurrences from custom exercises. Existing unexpected external rows without valid source data cause migration failure. Retire `custom_name_at_start` after the general session `exercise_name` snapshot is populated.

### 8.4 `plan_sets`

Add required `measurement_type` and `rest_seconds` default 120 with range 0–3600. Use existing reps, duration, and weight columns. Remove distance or constrain it null and remove it in a later cleanup; preferred approach is removal now.

Add exact-one measurement checks and composite FK `(plan_exercise_id, measurement_type)` to the parent. Backfill existing rows as reps/rest 120; fail if an existing set lacks target reps.

### 8.5 `session_sets`

Add required measurement type and rest default 120. Replace weak checks so:

- Target measurement matches the parent.
- Planned/skipped rows have null actual fields and completion time.
- Completed reps require actual reps and null duration.
- Completed duration requires actual duration and null reps.
- Weight remains optional/nonnegative.
- Composite FK matches the parent occurrence.

Backfill as reps and fail if completed legacy rows lack actual reps. Prefer removing distance columns now.

### 8.6 `workout_sessions` and deletion

Add unique partial index on `owner_user_id WHERE status='in_progress'`.

Add `ON DELETE CASCADE` from session exercises to session and session sets to session exercise. Do not cascade user deletion into finished history in this change.

### 8.7 Do not store derived values

Do not add columns for last-performed, previous performance, active countdown, or provider catalog total.

### 8.8 Migration verification

- Update the migration-head assertion.
- Test upgrade from current head with representative data, fresh upgrade, and downgrade to `0003`.
- Verify constraints with direct SQL rejection tests.
- Test concurrent active-session inserts.
- Confirm the schema has no vendor-media column.
- Document lossy legacy-array downgrade.
- Use only a guarded disposable test database.

## 9. Transactions and business rules

Each operation below is atomic:

- Store a newly selected external exercise and add it to a plan/session.
- Duplicate a plan.
- Start a plan-based or empty session.
- Reorder exercises.
- Finish or permanently cancel a session.
- Any parent-version mutation.

Provider failure during first external selection rolls back everything. Stored external records remain usable during outage. Browsing does not persist. Plan-to-session copying never calls ExerciseDB. Clients cannot override snapshots. Only one active session is allowed. Cancel hard-deletes active sessions only; abandon remains retained. Expanded reads must use bounded query counts. Actual values without completed status are rejected, and edits to completed values preserve the original completion time.

## 10. Swagger/OpenAPI requirements

### 10.1 Application and tags

Give the FastAPI application a plain-language description explaining profiles, exercise sources, plans, sessions, `ETag` concurrency, and development-only identity. Add a “Common API journeys” guide described below. Do not include secrets or internal addresses.

Use clear tag descriptions: `health`, `exercise catalog`, `ExerciseDB`, `exercise options`, `profile`, `custom exercises`, `workout plans`, `workout sessions`, and `exercise performance`.

### 10.2 Every API operation

Every existing and new route must have:

- Unique explicit `operation_id`.
- Short summary and plain-language description explaining when to use it.
- Descriptions for every path/query parameter and request field.
- Named success response model and meaningful example.
- Documented expected errors using the safe error model.
- Correct status and tag.
- Relevant response headers (`ETag`, `Location`, `Retry-After`, `X-Correlation-ID`).
- Deprecation marker only when intentionally being retired.

Swagger must distinguish provider-specific `/api/exercises...` routes from the unified `/api/exercise-catalog`.

### 10.3 Required summaries

| Area | Operations and summaries |
| --- | --- |
| Health | Live process check; database readiness check. |
| Options/catalog | List stable exercise options; browse selectable exercises; get latest performance. |
| ExerciseDB | Browse, status, provider taxonomies, search/filter, image proxy, and detail—with descriptions that these are live provider routes. |
| Profile | Get my profile; update my display preferences. |
| Custom exercises | List, create, get, update, and archive my private exercises. |
| Plans | List/create/get/rename/duplicate/archive; add/update/remove/reorder exercises; add/update/remove sets. |
| Sessions | List/start/get current/get detail/rename/cancel; add/update/remove/reorder exercises; add/update/remove sets; finish; abandon. |

Descriptions must explain `If-Match`, archive behavior, source forms, provider outage behavior, measurement rules, rest defaults, cancellation versus abandonment, and terminal immutability where relevant.

### 10.4 Common API journeys in Swagger

Document these sequences at the top of Swagger:

1. **Create a plan:** get options → browse unified catalog → create plan → add exercise → add sets → use returned ETag for each mutation.
2. **Start from a plan:** check current workout → create session using plan → record sets → finish.
3. **Ad hoc workout:** create empty session → browse catalog → add exercises/sets → finish or permanently cancel.
4. **Previous performance:** call latest-performance with the exercise source; null means no finished history.
5. **Provider outage:** existing snapshots remain readable; catalog may return custom/stored external items with degraded status.

## 11. Ordered implementation plan

1. Bind local API/PostgreSQL ports to loopback and retain development identity fail-closed behavior.
2. Create and verify the migration, constraints, indexes, cascades, and data transition.
3. Update request/response models with descriptions, examples, and exact measurement validation.
4. Add controlled options and provider-to-Unshaken mappings.
5. Implement selected external-exercise storage and custom/external plan/session additions.
6. Implement unified cursor-based catalog and degraded behavior.
7. Expand plan summaries/details and remove N+1 queries.
8. Add rest/duration support to plan sets.
9. Enforce one active session and add `/current`.
10. Expand session snapshots/set rules and remove N+1 queries.
11. Add permanent cancel.
12. Add latest previous performance.
13. Complete Swagger descriptions/examples/errors/operation IDs/journey guide for every route.
14. Run formatting, lint, type checking, full PostgreSQL/migration/OpenAPI tests, and a manual Swagger/curl journey; report exact results.

## 12. Acceptance criteria

### Options and unified catalog

- Options return all approved values without DB/provider calls.
- One catalog response may contain custom and ExerciseDB items in deterministic alphabetical order.
- Consecutive cursors produce no duplicates or missing items in controlled tests.
- Cursor/filter mismatch returns `422`.
- Only current-user active custom exercises appear.
- `source=custom` makes no provider call.
- Provider failures return safe degraded results when local results exist.
- Browsing writes no external records and exposes no secrets/media URLs.

### Custom and selected external exercises

- Custom create requires exactly one equipment, body part, and measurement type.
- Default custom list is alphabetical; search and filters work and remain owner-scoped.
- Referenced measurement-type changes return `409`.
- External selection stores only approved non-media fields.
- Stored external records remain selectable during provider outage.
- First-time selection during outage writes nothing and returns `503`.
- Concurrent first selection creates one external row.
- Plans/sessions never expose who first selected it.

### Plans

- Summaries contain first three exercise previews, set counts, and correct/null last-performed time.
- Detail includes source, name, body part, equipment, measurement type, note, and ordered sets.
- Plan reads work during provider outage.
- Client-supplied snapshot display data is rejected/ignored by schema.
- Duplication copies snapshots, measurement values, weight, duration, and rest without provider calls.
- Expanded reads use a bounded query count independent of exercise count.

### Sets and rest

- Reps exercises require reps and reject duration; duration exercises do the reverse.
- Optional weight works for both and zero weight is accepted.
- New sets default to 120 rest; 0 and 3600 are accepted, out-of-range values rejected.
- Distance is rejected.
- Direct SQL cannot create a set that conflicts with its parent measurement type.
- Plan-to-session copying preserves rest exactly.
- No countdown-state column exists.

### Active sessions and cancel

- A user can create one active session; a second returns `409`.
- Two simultaneous starts result in one success and one safe conflict.
- Different users may each have one active session.
- `/current` returns full detail/ETag or `404 no_active_session`.
- Plan session creation uses snapshots and makes no provider call.
- Cancel with current ETag removes active parent and children; transaction failure leaves everything intact.
- Finished/abandoned cancel returns `409`; foreign returns `404`; repeat delete returns `404`.

### Actual results and previous performance

- Completed reps require actual reps; completed duration requires actual seconds.
- Actual weight is optional for both.
- Planned/skipped sets cannot retain actual values.
- Actual values without completed status return `422` and are never discarded silently.
- Reopen/skip clears results and timestamp; editing an already completed set preserves its timestamp.
- Latest performance considers only finished sessions, uses deterministic latest selection, works during provider outage, and never leaks another user’s history.
- No history returns `200` with `item: null`.

### Migration

- Fresh and existing-data upgrades reach the new head; downgrade to `0003` succeeds with documented array-loss limitation.
- Existing data becomes reps/rest 120 and valid custom taxonomy values.
- Invalid legacy history causes a clear migration failure rather than invented data.
- DB constraints and one-active-session index are verified directly in a guarded disposable database.
- Schema contains no vendor media/raw payload column.

### Swagger/OpenAPI

- Every operation has a unique operation ID, summary, useful description, tags, parameter/body descriptions, named success schema, examples, errors, and relevant headers.
- OpenAPI JSON contains no secrets.
- The journey guide explains create plan, plan/ad hoc session, result logging, finish/cancel, previous performance, and provider outage.
- Automated tests fail when required documentation is missing.
- Manual review confirms a developer unfamiliar with Unshaken can follow the workflows.

## 13. Remaining risks

1. **ExerciseDB permission:** Owner approves minimal selected-record storage, but provider-specific permission remains unclear. Confirm it before public deployment.
2. **Provider quota:** Unified browsing consumes free-plan requests; use bounded calls and measure real traffic.
3. **Taxonomy mapping:** Provider values need an explicit tested mapping; unknown values become `other`.
4. **Legacy conversion:** Existing multi-value arrays will be reduced to one value, and downgrade cannot restore discarded extras.
5. **Authentication:** Development identity remains temporary; real authentication is mandatory before invited users or deployment.

No UI, component, layout, or styling work is included in this document.
