# Frontend

The frontend is a Vite-powered React 18 and TypeScript single-page application.
Its initial shell is intentionally limited to public technical-foundation content:
responsive layout, routing, error handling, and an API health indicator.

## Structure

- `src/app/` — router and application shell.
- `src/api/` — typed API boundary; browser code must not call external providers.
- `src/components/` — reusable accessible UI pieces.
- `src/styles/` — design tokens and global responsive styles.
- `tests/` — component and API-boundary tests.

## Commands

Run from this directory:

```sh
npm install
npm run dev
npm run format:check
npm run lint
npm run typecheck
npm test
npm run build
```

Set `VITE_API_BASE_URL` to the API origin. It is a public browser configuration,
so it must never contain a secret. A missing value defaults to the same origin,
which is useful when a reverse proxy serves both applications.

## UI foundation

The shell includes semantic landmarks, a skip link, visible keyboard focus, an
`aria-live` health status, and a responsive navigation layout that works at 320px
without horizontal scrolling. Future protected routes must be authorized by the
API; client-side routes are not an authorization mechanism.
