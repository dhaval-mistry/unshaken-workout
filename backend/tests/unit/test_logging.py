import json
import logging

import pytest

from app.core.logging import JsonFormatter
from app.core.request_context import set_correlation_id


@pytest.mark.parametrize(
    "field_name",
    [
        "access_token",
        "token",
        "password",
        "secret",
        "api_key",
        "code",
        "authorization",
        "proxy_authorization",
    ],
)
def test_json_formatter_redacts_sensitive_extra_fields(field_name: str) -> None:
    set_correlation_id("request-123")
    record = logging.makeLogRecord(
        {
            "name": "test",
            "levelno": logging.INFO,
            "levelname": "INFO",
            "msg": "safe event",
            "args": (),
            field_name: "must-not-leak",
            "action": "health_check",
        }
    )

    payload = json.loads(JsonFormatter().format(record))

    assert payload["correlation_id"] == "request-123"
    assert payload[field_name] == "[redacted]"
    assert payload["action"] == "health_check"
