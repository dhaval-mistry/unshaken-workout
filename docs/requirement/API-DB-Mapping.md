# API and Database Mapping

This document explains how each API uses PostgreSQL and ExerciseDB. It describes the current implementation in simple English.

## 1. Main data flow

### Browse exercises

1. The UI calls `GET /api/exercise-catalog`.
2. FastAPI reads the current user's active custom exercises from `custom_exercises`.
3. FastAPI also reads previously selected ExerciseDB records from `external_exercises`.
4. When available, FastAPI calls ExerciseDB for current vendor results.
5. FastAPI combines the results and sends one list to the UI.
6. Browsing does not save new ExerciseDB exercises.

### Select a custom exercise

1. The UI adds the custom exercise to a plan or workout session.
2. FastAPI verifies that the `custom_exercises` record belongs to the current user and is active.
3. FastAPI copies the exercise name, body part, equipment, and measurement type into `plan_exercises` or `session_exercises`.
4. The copied values are snapshots. Later changes to the custom exercise do not rewrite an existing plan or workout history.

### Select an ExerciseDB exercise

1. The UI adds an ExerciseDB exercise to a plan or workout session.
2. FastAPI looks for its provider ID in `external_exercises`.
3. If it has not been selected before, FastAPI retrieves it from ExerciseDB.
4. FastAPI stores only its provider ID, name, body part, equipment, attribution, and validation dates in `external_exercises`.
5. FastAPI does not store its image, video, instructions, media address, or raw vendor response.
6. FastAPI copies the approved fields into `plan_exercises` or `session_exercises`.
7. Existing plans and workout sessions can use their snapshots when ExerciseDB is unavailable.

### Start from a workout plan

1. FastAPI creates a row in `workout_sessions`.
2. It copies `plan_exercises` to `session_exercises`.
3. It copies `plan_sets` to `session_sets`.
4. It does not call ExerciseDB while copying the plan.
5. Changes made during the workout affect only the session.

### Start an empty workout

1. FastAPI creates a row in `workout_sessions` without a source plan.
2. The user adds exercises to `session_exercises`.
3. The user adds sets to `session_sets`.
4. The database allows only one in-progress session for each user.

### Record and finish a workout

1. Each performed set is updated in `session_sets`.
2. A completed set stores actual repetitions or actual duration, optional weight, and completion time.
3. Finishing the workout updates `workout_sessions` with finished status, finish time, and total time.
4. Finished and abandoned sessions become read-only.
5. Cancelling an active workout permanently deletes the session and its exercise and set rows.

### Show previous performance

1. FastAPI finds the most recent finished `workout_sessions` row containing the selected exercise.
2. It reads the matching `session_exercises` snapshot.
3. It reads the performed values from `session_sets`.
4. ExerciseDB is not called.

## 2. Database tables

| Table | Purpose |
| --- | --- |
| `users` | Stores the user's basic profile and preferred weight unit. Authentication details are not stored here yet. |
| `custom_exercises` | Stores private exercises created by a user. Each has one equipment value, one body part, and either repetitions or duration as its measurement type. |
| `external_exercises` | Stores the approved non-media fields for an ExerciseDB exercise after somebody selects it. This is shared provider reference data and does not contain a user owner. |
| `workout_plans` | Stores each user-owned reusable workout plan. |
| `plan_exercises` | Stores the ordered exercises inside a workout plan, including copied exercise details and the exercise-level note. |
| `plan_sets` | Stores planned repetitions or duration, optional weight, and rest time for each plan exercise. |
| `workout_sessions` | Stores an active, finished, or abandoned performed workout. It may have been created from a plan or started empty. |
| `session_exercises` | Stores the ordered exercises and copied exercise details for one performed workout. |
| `session_sets` | Stores planned values and actual performed results for each workout set. |

## 3. API-to-database mapping

`Read` means the API looks at the table. `Write` includes creating, updating, archiving, or deleting data.

### Health

| Method and path | Database use | Data flow |
| --- | --- | --- |
| `GET /health/live` | None | Confirms that the FastAPI process is running. |
| `GET /health/ready` | Connection check only | Runs a minimal PostgreSQL connection check. It does not read a workout table. |

### ExerciseDB live APIs

These APIs call ExerciseDB through the backend adapter. They do not read or write workout database tables.

| Method and path | Database use | Data flow |
| --- | --- | --- |
| `GET /api/exercises` | None | Gets a live page of ExerciseDB exercises. |
| `GET /api/exercises/status` | None | Checks whether ExerciseDB is reachable. |
| `GET /api/exercises/body-parts` | None | Gets the live ExerciseDB body-part list. |
| `GET /api/exercises/targets` | None | Gets the live ExerciseDB target-muscle list. |
| `GET /api/exercises/equipment` | None | Gets the live ExerciseDB equipment list. |
| `GET /api/exercises/search/{name}` | None | Searches ExerciseDB by exercise name. |
| `GET /api/exercises/target/{target}` | None | Gets ExerciseDB exercises for one target. |
| `GET /api/exercises/body-part/{body_part}` | None | Gets ExerciseDB exercises for one body part. |
| `GET /api/exercises/equipment/{equipment}` | None | Gets ExerciseDB exercises for one equipment value. |
| `GET /api/exercises/image/{exercise_id}` | None | Proxies an allowed image without saving it. |
| `GET /api/exercises/{exercise_id}` | None | Gets one live ExerciseDB exercise by provider ID. |

### Exercise options and combined catalog

| Method and path | Reads | Writes | Data flow |
| --- | --- | --- | --- |
| `GET /api/exercise-options` | None | None | Returns Unshaken's built-in equipment, body-part, and measurement choices from application code. |
| `GET /api/exercise-catalog` | `custom_exercises`, `external_exercises` | None | Combines the current user's custom exercises, stored ExerciseDB references, and live ExerciseDB results. Browsing does not save new vendor records. |
| `GET /api/exercise-performance/latest` | `custom_exercises`, `workout_sessions`, `session_exercises`, `session_sets` | None | Returns the selected exercise's most recent finished performance for the current user. |

### Profile

| Method and path | Reads | Writes | Data flow |
| --- | --- | --- | --- |
| `GET /api/me` | `users` | None | Returns the current user's basic profile. |
| `PATCH /api/me` | `users` | `users` | Updates the display name or preferred weight unit. |

### Custom exercises

| Method and path | Reads | Writes | Data flow |
| --- | --- | --- | --- |
| `GET /api/custom-exercises` | `custom_exercises` | None | Lists only the current user's custom exercises and applies search, filters, sorting, archive choice, and paging. |
| `POST /api/custom-exercises` | None | `custom_exercises` | Creates a private custom exercise for the current user. |
| `GET /api/custom-exercises/{exercise_id}` | `custom_exercises` | None | Gets one custom exercise when it belongs to the current user. |
| `PATCH /api/custom-exercises/{exercise_id}` | `custom_exercises`; `plan_exercises`, `session_exercises`, and `workout_sessions` when changing measurement type | `custom_exercises` | Updates the custom exercise. It blocks a measurement-type change when the exercise is already used by a plan or active session. |
| `POST /api/custom-exercises/{exercise_id}/archive` | `custom_exercises` | `custom_exercises` | Hides the custom exercise from normal selection while keeping existing plans and workout history valid. |

### Workout plans

| Method and path | Reads | Writes | Data flow |
| --- | --- | --- | --- |
| `GET /api/workout-plans` | `workout_plans`, `plan_exercises`, `plan_sets`, `workout_sessions` | None | Lists the user's plans with an exercise preview and last performed time. |
| `POST /api/workout-plans` | `workout_plans`, `plan_exercises`, `plan_sets`, `workout_sessions` | `workout_plans` | Creates an empty plan and returns its detail. |
| `GET /api/workout-plans/{plan_id}` | `workout_plans`, `plan_exercises`, `plan_sets`, `workout_sessions` | None | Gets one owned plan with ordered exercises and sets. |
| `PATCH /api/workout-plans/{plan_id}` | `workout_plans`, `plan_exercises`, `plan_sets`, `workout_sessions` | `workout_plans` | Renames an active plan and advances its version. |
| `POST /api/workout-plans/{plan_id}/duplicate` | `workout_plans`, `plan_exercises`, `plan_sets` | `workout_plans`, `plan_exercises`, `plan_sets` | Copies a plan, its exercise snapshots, and its planned sets without calling ExerciseDB. |
| `POST /api/workout-plans/{plan_id}/archive` | `workout_plans`, `plan_exercises`, `plan_sets`, `workout_sessions` | `workout_plans` | Archives a plan. Its existing data remains available, but the plan becomes read-only. |
| `POST /api/workout-plans/{plan_id}/exercises` | `workout_plans`, `plan_exercises`; `custom_exercises` or `external_exercises` | `plan_exercises`; possibly `external_exercises`; `workout_plans` version | Adds a custom or ExerciseDB exercise. A first-time ExerciseDB selection stores only approved non-media fields. |
| `PATCH /api/workout-plans/{plan_id}/exercises/{item_id}` | `workout_plans`, `plan_exercises`, `plan_sets`, `workout_sessions` | `plan_exercises`, `workout_plans` version | Updates the exercise-level note. |
| `DELETE /api/workout-plans/{plan_id}/exercises/{item_id}` | `workout_plans`, `plan_exercises` | `plan_exercises`, `plan_sets` through cascade, `workout_plans` version | Removes an exercise and its sets, then closes gaps in exercise order. |
| `PUT /api/workout-plans/{plan_id}/exercises/order` | `workout_plans`, `plan_exercises`, `plan_sets`, `workout_sessions` | `plan_exercises`, `workout_plans` version | Saves the complete exercise order. |
| `POST /api/workout-plans/{plan_id}/exercises/{item_id}/sets` | `workout_plans`, `plan_exercises`, `plan_sets` | `plan_sets`, `workout_plans` version | Adds a repetitions or duration set with optional weight and rest time. |
| `PATCH /api/workout-plans/{plan_id}/exercises/{item_id}/sets/{set_id}` | `workout_plans`, `plan_exercises`, `plan_sets` | `plan_sets`, `workout_plans` version | Updates one planned set while keeping its measurement type valid. |
| `DELETE /api/workout-plans/{plan_id}/exercises/{item_id}/sets/{set_id}` | `workout_plans`, `plan_exercises`, `plan_sets` | `plan_sets`, `workout_plans` version | Removes a planned set and closes gaps in set numbering. |

### Workout sessions

| Method and path | Reads | Writes | Data flow |
| --- | --- | --- | --- |
| `GET /api/workout-sessions` | `workout_sessions` | None | Lists the user's active and historical workout sessions. |
| `POST /api/workout-sessions` | `workout_plans`, `plan_exercises`, `plan_sets` when starting from a plan | `workout_sessions`, and possibly `session_exercises` and `session_sets` | Starts an empty workout or copies a plan into a new session. The database prevents a second active session for the same user. |
| `GET /api/workout-sessions/current` | `workout_sessions`, `session_exercises`, `session_sets` | None | Restores the current user's one active workout. |
| `GET /api/workout-sessions/{session_id}` | `workout_sessions`, `session_exercises`, `session_sets` | None | Gets one owned workout with all exercise and set details. |
| `DELETE /api/workout-sessions/{session_id}` | `workout_sessions` | Deletes `workout_sessions`, `session_exercises`, and `session_sets` | Permanently cancels an active workout. Child rows are removed by database cascade. |
| `PATCH /api/workout-sessions/{session_id}` | `workout_sessions`, `session_exercises`, `session_sets` | `workout_sessions` | Renames an active workout and advances its version. |
| `POST /api/workout-sessions/{session_id}/exercises` | `workout_sessions`, `session_exercises`; `custom_exercises` or `external_exercises` | `session_exercises`; possibly `external_exercises`; `workout_sessions` version | Adds a custom or ExerciseDB exercise to an active workout. |
| `PATCH /api/workout-sessions/{session_id}/exercises/{item_id}` | `workout_sessions`, `session_exercises`, `session_sets` | `session_exercises`, `workout_sessions` version | Updates the exercise-level note. |
| `DELETE /api/workout-sessions/{session_id}/exercises/{item_id}` | `workout_sessions`, `session_exercises` | `session_exercises`, `session_sets` through cascade, `workout_sessions` version | Removes an exercise and its sets, then closes gaps in exercise order. |
| `PUT /api/workout-sessions/{session_id}/exercises/order` | `workout_sessions`, `session_exercises`, `session_sets` | `session_exercises`, `workout_sessions` version | Saves the complete exercise order for an active workout. |
| `POST /api/workout-sessions/{session_id}/exercises/{item_id}/sets` | `workout_sessions`, `session_exercises`, `session_sets` | `session_sets`, `workout_sessions` version | Adds a planned set to an active workout. |
| `PATCH /api/workout-sessions/{session_id}/exercises/{item_id}/sets/{set_id}` | `workout_sessions`, `session_exercises`, `session_sets` | `session_sets`, `workout_sessions` version | Updates targets, actual results, status, optional weight, rest, and completion time for one set. |
| `DELETE /api/workout-sessions/{session_id}/exercises/{item_id}/sets/{set_id}` | `workout_sessions`, `session_exercises`, `session_sets` | `session_sets`, `workout_sessions` version | Removes a set and closes gaps in set numbering. |
| `POST /api/workout-sessions/{session_id}/finish` | `workout_sessions`, `session_exercises`, `session_sets` | `workout_sessions` | Finishes a complete workout and stores finish time and total time. |
| `POST /api/workout-sessions/{session_id}/abandon` | `workout_sessions`, `session_exercises`, `session_sets` | `workout_sessions` | Stops a workout but keeps it as abandoned history. |

## 4. Ownership and data protection

- Profile, custom exercise, plan, session, and performance queries are scoped to the current user.
- ExerciseDB reference rows are shared reference data, but plans and sessions do not reveal who selected them first.
- The React frontend does not decide database ownership.
- FastAPI checks ownership before reading or changing private data.
- Plan and session changes use an `ETag` and `If-Match` version to prevent one browser update from silently overwriting another.
- Real invitation-only authentication is still required before deployment. Local development currently uses a configured development user.

## 5. Quick API and database gap check

The API and database now support the screenshot-derived behaviors:

- One combined custom and ExerciseDB exercise catalog.
- Alphabetical exercise selection.
- One equipment category and one body part.
- Repetitions or duration, with optional weight.
- Exercise-level notes.
- Reusable workout plans with ordered exercises and sets.
- Starting a workout from a plan.
- Starting an empty workout and adding exercises.
- A 120-second default rest after every set, with a per-set override.
- One active workout at a time.
- Most recent finished performance.
- Finish, abandon, and permanent cancellation.
- Total workout time.
- Stored exercise snapshots that do not depend on ExerciseDB during a workout.

The following gaps remain:

1. **Swagger tag mismatch:** the declared `ExerciseDB`, `profile`, and `custom exercises` groups are empty because their routes currently use the tags `exercises` and `workouts`. Correct the route tags and add an OpenAPI test that checks each expected group contains methods.
2. **Swagger descriptions are incomplete:** many operations receive generated names and generic descriptions instead of a clear explanation written for that API. The approved requirement asked for explicit, useful descriptions for every method.
3. **Mixed catalog paging needs correction and a stronger test:** custom-only paging is tested, but the code advances one shared ExerciseDB offset across stored and live provider lists. A stored exercise can be skipped when stored and live lists have different ordering or sizes. Test several mixed pages containing custom, stored external, and live external results with overlap and a provider outage.
4. **Filtered ExerciseDB paging needs stronger coverage:** body-part and equipment filtering happens after a bounded provider page is retrieved. A page containing nonmatching vendor records can look incomplete even when later matching records exist. The catalog contract should either use a provider filter endpoint or continue fetching within a strict request limit.

No missing database table is required for the reviewed screens.
