#!/usr/bin/env bash
set -euo pipefail

# This exercises Docker's combined stdout/stderr stream, where Uvicorn formerly leaked query strings.
compose=(docker compose --env-file .env.example)
probe="compose-log-redaction-probe-20260906"

cleanup() {
  "${compose[@]}" down >/dev/null
}
trap cleanup EXIT

"${compose[@]}" config >/dev/null
"${compose[@]}" up -d --build

for attempt in $(seq 1 30); do
  if curl --fail --silent --show-error http://localhost:8000/health/ready >/dev/null; then
    break
  fi
  if [ "$attempt" = 30 ]; then
    echo "Backend readiness did not succeed" >&2
    exit 1
  fi
  sleep 2
done

curl --fail --silent --show-error \
  "http://localhost:8000/health/live?access_token=${probe}&token=${probe}&password=${probe}&secret=${probe}&api_key=${probe}&code=${probe}&authorization=${probe}" \
  >/dev/null
logs="$("${compose[@]}" logs --no-color backend)"
if grep --fixed-strings --quiet "$probe" <<<"$logs"; then
  echo "Sensitive query value appeared in complete backend logs" >&2
  exit 1
fi
if ! grep --fixed-strings --quiet '"message": "http_request_completed"' <<<"$logs"; then
  echo "Safe structured access event was not emitted" >&2
  exit 1
fi

echo "Compose log-redaction regression passed"
