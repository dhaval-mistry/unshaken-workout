# ExerciseDB integration

## Approved scope

US-04 browse/search and US-05 details use ExerciseDB only through FastAPI. React
never receives provider credentials and never calls a provider URL. The API exposes
the normalized `GET /api/exercises` and `GET /api/exercises/{exercise_id}` routes.

## Setup

Obtain an active provider subscription, then set `EXERCISE_DB_BASE_URL`,
`EXERCISE_DB_API_KEY`, and `EXERCISE_DB_HOST` in the deployment environment. Keep
`EXERCISE_DB_MEDIA_ENABLED=false` unless the subscription's current terms explicitly
permit displaying provider media in this application. The adapter uses an eight-second
timeout and fixed provider paths; it does not accept client-supplied provider URLs.

## Content and licensing limits

ExerciseDB's current API Terms of Use state that its text, metadata, images, GIFs,
videos, and instructions are provider-owned, require an active subscription, and
must not be persistently stored or bulk-collected. Therefore Unshaken fetches each
page and detail record live, stores no provider table, avoids caches, and never
downloads media. Attribution is displayed beside source content. The product owner
must review the current terms and subscription entitlement before production launch:
<https://exercisedb.notion.site/ExerciseDB-API-Terms-of-Use-226983b728ca8090bf7be79564e4b356>.

If configuration is absent, a provider request times out, the provider returns an
invalid response, or an upstream service fails, the API returns a safe catalog
unavailable response. A confirmed missing provider identifier returns `404`.
