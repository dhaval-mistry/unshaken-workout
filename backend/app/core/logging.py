"""Safe JSON logging with request correlation support."""

import json
import logging
from datetime import UTC, datetime
from typing import Any

from .request_context import get_correlation_id

_SENSITIVE_FIELD_NAMES = {"authorization", "cookie", "password", "secret", "token", "code"}
_STANDARD_RECORD_FIELDS = set(logging.makeLogRecord({}).__dict__)


def _safe_value(key: str, value: Any) -> Any:
    """Redact known credential-shaped fields before a log record leaves the process."""

    if any(sensitive in key.lower() for sensitive in _SENSITIVE_FIELD_NAMES):
        return "[redacted]"
    return value if isinstance(value, (str, int, float, bool, type(None))) else str(value)


class JsonFormatter(logging.Formatter):
    """Formats structured, credential-safe records for container log collectors."""

    def format(self, record: logging.LogRecord) -> str:
        """Serialize a record with the current correlation identifier and safe extras."""

        payload: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "correlation_id": get_correlation_id(),
        }
        for key, value in record.__dict__.items():
            if key not in _STANDARD_RECORD_FIELDS and not key.startswith("_"):
                payload[key] = _safe_value(key, value)
        return json.dumps(payload, default=str)


def configure_logging(level: str) -> None:
    """Configure root logging once, replacing implicit handlers with JSON output."""

    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    logging.basicConfig(level=level, handlers=[handler], force=True)
