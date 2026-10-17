"""Safe JSON logging with request correlation support."""

import json
import logging
import re
from datetime import UTC, datetime
from typing import Any

from .request_context import get_correlation_id

_SENSITIVE_FIELD_NAMES = {
    "access_token",
    "api_key",
    "apikey",
    "authorization",
    "bearer",
    "code",
    "cookie",
    "credential",
    "password",
    "proxy_authorization",
    "secret",
    "set_cookie",
    "token",
}
_SAFE_TELEMETRY_FIELD_NAMES = {"duration_ms", "method", "path", "status_code"}
_STANDARD_RECORD_FIELDS = set(logging.makeLogRecord({}).__dict__)
_SENSITIVE_VALUE_PATTERN = re.compile(
    r"(?i)\\b(access_token|api[_-]?key|authorization|bearer|code|cookie|credential|"
    r"password|proxy[_-]?authorization|secret|token)\\s*([=:])\\s*([^&\\s,]+)"
)
_BEARER_VALUE_PATTERN = re.compile(r"(?i)\\bBearer\\s+[^\\s,]+")
_DATABASE_URL_PATTERN = re.compile(r"(?i)postgres(?:ql)?(?:\\+[a-z0-9_]+)?://[^\\s,]+")


def _safe_value(key: str, value: Any) -> Any:
    """Redact known credential-shaped fields before a log record leaves the process."""

    if key.lower() in _SAFE_TELEMETRY_FIELD_NAMES:
        return value
    if any(sensitive in key.lower() for sensitive in _SENSITIVE_FIELD_NAMES):
        return "[redacted]"
    return value if isinstance(value, str | int | float | bool | type(None)) else str(value)


def redact_message(message: str) -> str:
    """Remove credentials from unstructured messages supplied by framework dependencies."""

    without_database_url = _DATABASE_URL_PATTERN.sub("postgresql://[redacted]", message)
    without_bearer = _BEARER_VALUE_PATTERN.sub("Bearer [redacted]", without_database_url)
    return _SENSITIVE_VALUE_PATTERN.sub(r"\\1\\2[redacted]", without_bearer)


class JsonFormatter(logging.Formatter):
    """Formats structured, credential-safe records for container log collectors."""

    def format(self, record: logging.LogRecord) -> str:
        """Serialize a record with the current correlation identifier and safe extras."""

        payload: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": redact_message(record.getMessage()),
            "correlation_id": get_correlation_id(),
        }
        for key, value in record.__dict__.items():
            if key not in _STANDARD_RECORD_FIELDS and not key.startswith("_"):
                payload[key] = _safe_value(key, value)
        return json.dumps(payload, default=str)


def configure_logging(level: str) -> None:
    """Configure credential-safe structured application logs.

    Uvicorn's default access logger includes raw request targets, including query
    strings, so it is disabled in favor of the safe middleware access event.
    """

    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    logging.basicConfig(level=level, handlers=[handler], force=True)
    # Third-party request loggers can include complete URLs, so only our safe
    # application access event is retained at INFO level.
    for logger_name in ("httpcore", "httpx", "uvicorn.access"):
        request_logger = logging.getLogger(logger_name)
        request_logger.handlers.clear()
        request_logger.disabled = True
        request_logger.propagate = False
