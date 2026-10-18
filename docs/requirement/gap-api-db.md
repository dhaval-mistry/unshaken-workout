# API and PostgreSQL gap analysis for referenced workout flows

**Status:** Draft for owner review. This document does not approve implementation.

The screenshots are workflow references only. Seven screenshots were supplied although eight screens were described. The body-part picker screenshot is absent, so its values and selection rules are not inferred.

## Workflow-to-backend mapping

| Referenced workflow | Current API and database support | API or database gap |
| --- | --- | --- |
| List workout plans | `GET /api/workout-plans`; plan tables | No exercise-name preview, set summary, or last-performed value. |
| Show last-performed date | Derivable from finished sessions using `source_plan_id` and `finished_at` | Missing read query/response field; no new stored column is initially required. |
| Open a plan | Detail returns ordered references, notes, and sets | Plan exercise response lacks display name, training type, muscles/body area, and equipment. |
| Start from a plan | Session create with `source_plan_id`; plan snapshot tables | Supported for custom exercises; saved ExerciseDB references are rejected. |
| Start an empty session | Session create without a plan; nullable source plan | Supported. |
| Add exercise to active session | Session-exercise create; source columns exist | API accepts custom exercises only. |
| Show elapsed time | Session returns `started_at`; start/end/total fields exist | Supported unless pause/resume is required. |
| Show active exercises and sets | Session detail and snapshot tables | Supported. |
| Enter reps and weight | Session-set PATCH; actual values per set | Supported, but planned-state updates can discard submitted actual values. |
| Complete, skip, add set, or finish | Session-set and finish routes | Supported. |
| Cancel session | Abandon endpoint preserves session | No discard/delete behavior; intended meaning is unresolved. |
| Restore active session | Status-filtered list plus detail | Multiple active sessions are permitted; no current-session rule exists. |
| Show previous performance | Completed session data exists | Missing read model; comparison rule is undefined. |
| Rest between sets | No fields or columns | API and migration changes required if included. |
| Alphabetical standard exercises | ExerciseDB live routes; vendor data not stored | No stable full-catalog alphabetical sort contract. |
| Alphabetical custom exercises | Custom-exercise list | Creation-date ordering only; no name search/sort or taxonomy filters. |
| Select custom and standard exercises together | Separate APIs and models | No unified source-aware response, ordering, or pagination. |
| Save ExerciseDB exercise | Catalog exists; write APIs reject external source; provider/ID columns exist | Blocked pending permission to retain provider IDs and an approved write contract. |
| Create custom exercise | API and table support name, training type, muscles, equipment, instructions, notes | Built-in category/body-part option contracts are missing. |
| Select category | No internal taxonomy endpoint; training type constrained, equipment/muscles free-form | Category meaning and allowed values are undefined. |
| Select body part | ExerciseDB body-part list only; custom muscles free-form | No internal custom-exercise body-part taxonomy or selection rule. |
| Show thumbnails | Optional ExerciseDB image proxy; no stored media/custom image column | Vendor media is permission-gated; custom images unsupported. |
| Use pounds | Profile has unit preference; APIs/DB use kilograms | No DB gap if clients convert; API change needed only for unit-bearing requests. |
| Duration/distance exercise | API requires reps; reserved DB columns exist | API contract, validation, and DB constraints are not aligned for these measurements. |
| Starter/example plans | No endpoint; every plan has a user owner | Separate ownership/copy model needed only if starter plans are required. |

## Confirmed API and database gaps

### P0 — blocks selection and plan-preview flows

#### 1. ExerciseDB exercises cannot be saved

The database has `external_provider` and `external_exercise_id`, but request models and route logic accept custom sources only. Keep this gate closed until the configured RapidAPI provider confirms whether retaining exercise IDs is permitted.

Provider names, instructions, taxonomy, image URLs, and media must not be copied into PostgreSQL without explicit permission.

#### 2. Plan details lack exercise display data

Plan responses contain `custom_exercise_id`, but not the exercise name or classification needed for a plan summary or preview. Requiring one request per exercise is inefficient and fragile for archived custom exercises.

An approved plan read model should include the required custom-exercise display fields. External display fields remain subject to provider permission.

#### 3. No source-aware exercise selection contract

Custom and standard catalogs have different response and pagination contracts. A unified backend contract is needed only if both sources must appear in one globally ordered result set. If separate source sections are acceptable, this endpoint may not be needed.

#### 4. Custom-exercise taxonomy is undefined

Current storage separates:

- `training_type`: `strength`, `functional`, `cardio`, `mobility`, or `other`.
- `equipment_types`: arbitrary strings.
- `muscle_groups`: arbitrary strings.

The referenced category mixes concepts that Unshaken models separately. No taxonomy API or database change should be designed until category, equipment, body area, target muscle, and measurement style are defined.

### P1 — needed for complete workout behavior

#### 5. Previous-performance read model is missing

Previous reps and weights can be derived from completed sessions. The API needs a read model after “previous” is defined as the latest occurrence across all sessions, the latest from the same plan, or another rule.

#### 6. Rest-time storage and contract are missing

No rest value exists in plan or session records. If approved, plan rest settings should be copied into the session snapshot. A timer that must survive refresh also needs a reconstructable server timestamp or persisted timer state.

#### 7. Plan summaries are incomplete

The plan list lacks exercise previews and last-performed information. Last performed can be derived by joining finished sessions and does not initially require denormalization.

#### 8. Alphabetical search and filtering are incomplete

Custom exercise listing needs an approved name-sort/search and taxonomy-filter contract. ExerciseDB has no guaranteed full-catalog alphabetical order. Cross-source ordering must work with live-provider pagination and cannot depend on bulk vendor storage.

#### 9. Active-session policy is undefined

PostgreSQL permits multiple in-progress sessions per user. A unique partial index or service rule is needed only if one active session per user is required.

#### 10. Cancellation semantics are undefined

Abandonment preserves the session and elapsed time. Permanent discard would require explicit delete behavior and child-cascade rules.

#### 11. Duration/distance logging is not implemented in the API

Reserved database columns exist, but request/response models implement reps with optional weight. Supporting duration/distance requires coordinated API validation, completion rules, and database constraints.

## Existing backend findings affecting these flows

1. **Actual set values may be discarded.** Patching actual reps or weight while status remains `planned` returns success but clears those values. The API should reject this or define automatic completion.
2. **Database constraints are weaker than API rules.** PostgreSQL permits null target reps and completed measurement combinations rejected by the current API. The schema should match the approved measurement contract.
3. **Completed timestamps can change during corrections.** Editing an already completed set replaces `completed_at`, affecting history and previous-performance results.
4. **Plan/session detail uses one set query per exercise.** This can become expensive for large or frequently refreshed sessions; sets should be loaded in a bounded query.

## Backend changes not currently required

- Basic elapsed time needs no additional column unless pause/resume is required.
- Last performed can initially be derived from finished sessions.
- Previous performance should initially be derived from completed sessions.
- Pounds need no additional weight column while kilograms remain canonical.
- Custom exercise creation already supports name, training type, multiple muscles, multiple equipment values, instructions, and notes.
- Plan creation, ordering, sets, plan-to-session copying, ad hoc sessions, actual sets, finish, and abandon already work for custom exercises.

## Owner questions required before backend design

1. Does custom-exercise **category** mean training type, equipment, set measurement style, or a new field?
2. Should a custom exercise select one body part or multiple muscle groups? What are the approved Unshaken values?
3. Should equipment selection be single or multiple, and what values should the backend permit?
4. Should standard and custom exercises use one combined result set or separate source sections?
5. Must alphabetical ordering cover the entire live standard catalog or only each returned page?
6. Has ExerciseDB explicitly allowed retaining exercise IDs? Until then, should standard exercises remain browse-only?
7. Should plan list/detail responses include last-performed date and compact exercise summaries?
8. Does “previous performance” mean the same exercise across all sessions or only the same plan?
9. Is rest configured per exercise, per set, or an exercise default with overrides? Must the timer survive refresh?
10. Does cancelling preserve an abandoned session or permanently discard it?
11. May a user have more than one in-progress session?
12. Are duration and distance required now, or should this release remain reps plus optional weight?
13. Are exercise images required? If yes, are permitted live vendor images sufficient, or must custom exercises support user-owned images?
14. Are starter/example plans required, and should users copy them into private plans before editing?
