"""Request-scoped correlation identifiers used by logs and HTTP responses."""

from contextvars import ContextVar

_correlation_id: ContextVar[str | None] = ContextVar("correlation_id", default=None)


def set_correlation_id(value: str) -> None:
    """Associate a validated correlation identifier with the current async context."""

    _correlation_id.set(value)


def get_correlation_id() -> str | None:
    """Return the correlation identifier for the current request, if any."""

    return _correlation_id.get()
