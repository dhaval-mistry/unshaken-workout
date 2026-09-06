# ADR 0002: use structured logs and correlation identifiers

## Status

Accepted for the technical foundation.

## Decision

Emit JSON application logs and attach an `X-Correlation-ID` to every HTTP response.
Reuse only bounded, safe client-provided identifiers; otherwise generate a UUID.
Redact credential-shaped structured log fields.

## Consequences

Operators can correlate a browser response with API logs without accepting header
injection or recording credentials. Future audit logging must use safe metadata
and continue this redaction discipline.
