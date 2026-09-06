import json
import logging

from app.core.logging import JsonFormatter
from app.core.request_context import set_correlation_id


def test_json_formatter_redacts_sensitive_extra_fields() -> None:
    set_correlation_id("request-123")
    record = logging.makeLogRecord(
        {
            "name": "test",
            "levelno": logging.INFO,
            "levelname": "INFO",
            "msg": "safe event",
            "args": (),
            "access_token": "must-not-leak",
            "action": "health_check",
        }
    )

    payload = json.loads(JsonFormatter().format(record))

    assert payload["correlation_id"] == "request-123"
    assert payload["access_token"] == "[redacted]"
    assert payload["action"] == "health_check"
