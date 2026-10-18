# Unshaken API Guide

This guide lists the APIs currently implemented and explains when to use each one. It does not describe request or response bodies.

## Health

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/health/live` | Check whether the FastAPI process is running. |
| GET | `/health/ready` | Check whether the API can connect to PostgreSQL. |

## ExerciseDB

These methods read live ExerciseDB information through FastAPI. They do not save an exercise just because a user browses it.

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/api/exercises` | Browse a page of live ExerciseDB exercises using one supported filter. |
| GET | `/api/exercises/status` | Check whether ExerciseDB is currently available. |
| GET | `/api/exercises/body-parts` | List body-part values supplied by ExerciseDB. |
| GET | `/api/exercises/targets` | List target-muscle values supplied by ExerciseDB. |
| GET | `/api/exercises/equipment` | List equipment values supplied by ExerciseDB. |
| GET | `/api/exercises/search/{name}` | Search live ExerciseDB exercises by name. |
| GET | `/api/exercises/target/{target}` | List live ExerciseDB exercises for one target muscle. |
| GET | `/api/exercises/body-part/{body_part}` | List live ExerciseDB exercises for one body part. |
| GET | `/api/exercises/equipment/{equipment}` | List live ExerciseDB exercises for one equipment value. |
| GET | `/api/exercises/image/{exercise_id}` | Retrieve an allowed ExerciseDB image through FastAPI without saving it. |
| GET | `/api/exercises/{exercise_id}` | Get live details for one ExerciseDB exercise. |

## Exercise options

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/api/exercise-options` | List Unshaken's supported equipment, body parts, and measurement types for forms and filters. |

## Exercise catalog

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/api/exercise-catalog` | Browse one combined list containing the current user's custom exercises and ExerciseDB exercises. Use this list when adding an exercise to a plan or active workout. |

## Exercise performance

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/api/exercise-performance/latest` | Get the current user's most recent finished result for one custom or ExerciseDB exercise. |

## Profile

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/api/me` | Get the current user's basic profile and weight-unit preference. |
| PATCH | `/api/me` | Update the current user's display name or weight-unit preference. |

## Custom exercises

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/api/custom-exercises` | List and search the current user's private custom exercises. |
| POST | `/api/custom-exercises` | Create a private custom exercise. |
| GET | `/api/custom-exercises/{exercise_id}` | Get one private custom exercise. |
| PATCH | `/api/custom-exercises/{exercise_id}` | Update an active private custom exercise. |
| POST | `/api/custom-exercises/{exercise_id}/archive` | Archive a custom exercise so it is hidden from normal selection without breaking plans or history. |

## Workout plans

A workout plan is a reusable ordered group of exercises and planned sets.

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/api/workout-plans` | List the current user's workout plans with previews and last performed dates. |
| POST | `/api/workout-plans` | Create an empty workout plan. |
| GET | `/api/workout-plans/{plan_id}` | Open one workout plan with all exercises and sets. |
| PATCH | `/api/workout-plans/{plan_id}` | Rename an active workout plan. |
| POST | `/api/workout-plans/{plan_id}/duplicate` | Create a new plan by copying an existing active plan. |
| POST | `/api/workout-plans/{plan_id}/archive` | Archive a workout plan and make it read-only. |
| POST | `/api/workout-plans/{plan_id}/exercises` | Add a custom or ExerciseDB exercise to a plan. |
| PATCH | `/api/workout-plans/{plan_id}/exercises/{item_id}` | Update the note for an exercise in a plan. |
| DELETE | `/api/workout-plans/{plan_id}/exercises/{item_id}` | Remove an exercise and its planned sets from a plan. |
| PUT | `/api/workout-plans/{plan_id}/exercises/order` | Save a new order for all exercises in a plan. |
| POST | `/api/workout-plans/{plan_id}/exercises/{item_id}/sets` | Add a planned set to a plan exercise. |
| PATCH | `/api/workout-plans/{plan_id}/exercises/{item_id}/sets/{set_id}` | Update repetitions or duration, optional weight, or rest time for a planned set. |
| DELETE | `/api/workout-plans/{plan_id}/exercises/{item_id}/sets/{set_id}` | Remove a planned set. |

## Workout sessions

A workout session is an active or previously performed workout. Changes to an active plan or session require the latest version value through `If-Match`.

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/api/workout-sessions` | List the current user's active and historical workouts. |
| POST | `/api/workout-sessions` | Start a workout from a plan or start an empty workout. |
| GET | `/api/workout-sessions/current` | Restore the current user's active workout. |
| GET | `/api/workout-sessions/{session_id}` | Get one workout with its exercises, planned values, and performed results. |
| DELETE | `/api/workout-sessions/{session_id}` | Permanently cancel an active workout and delete its exercise and set data. |
| PATCH | `/api/workout-sessions/{session_id}` | Rename an active workout. |
| POST | `/api/workout-sessions/{session_id}/exercises` | Add a custom or ExerciseDB exercise to an active workout. |
| PATCH | `/api/workout-sessions/{session_id}/exercises/{item_id}` | Update the note for an exercise in an active workout. |
| DELETE | `/api/workout-sessions/{session_id}/exercises/{item_id}` | Remove an exercise and its sets from an active workout. |
| PUT | `/api/workout-sessions/{session_id}/exercises/order` | Save a new exercise order for an active workout. |
| POST | `/api/workout-sessions/{session_id}/exercises/{item_id}/sets` | Add a set to an exercise in an active workout. |
| PATCH | `/api/workout-sessions/{session_id}/exercises/{item_id}/sets/{set_id}` | Update one set's target, performed result, status, optional weight, or rest time. |
| DELETE | `/api/workout-sessions/{session_id}/exercises/{item_id}/sets/{set_id}` | Remove a set from an active workout. |
| POST | `/api/workout-sessions/{session_id}/finish` | Finish a workout after every set has been completed or skipped. |
| POST | `/api/workout-sessions/{session_id}/abandon` | Stop a workout while keeping it as abandoned history. |

## Common usage order

### Create a workout plan

1. Get the exercise options.
2. Browse the combined exercise catalog.
3. Create a workout plan.
4. Add exercises.
5. Add planned sets.
6. Use the newest returned version for each later plan change.

### Start from a plan

1. Check the current workout.
2. Start a session from a plan.
3. Record each performed set.
4. Finish the session.

### Start without a plan

1. Start an empty session.
2. Browse the combined exercise catalog.
3. Add exercises and sets.
4. Finish the session or permanently cancel it.

### Show previous performance

1. Choose a custom or ExerciseDB exercise.
2. Get its latest performance.
3. A result with no item means that the user has no finished history for that exercise.
