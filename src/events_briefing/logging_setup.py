"""JSON logs on stderr. Secret strings passed to configure_logging are redacted."""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any

_SECRETS: list[str] = []


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        fields = getattr(record, "fields", None)
        if isinstance(fields, dict):
            payload.update(fields)
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return _redact(json.dumps(payload, sort_keys=True, default=str))


def _redact(text: str) -> str:
    redacted = text
    for secret in _SECRETS:
        if secret:
            redacted = redacted.replace(secret, "[REDACTED]")
    return redacted


def configure_logging(secrets: list[str] | None = None, level: int = logging.INFO) -> None:
    global _SECRETS
    _SECRETS = [item for item in (secrets or []) if item]
    root = logging.getLogger()
    root.setLevel(level)
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(JsonFormatter())
    root.handlers = [handler]


def log_event(logger: logging.Logger, level: int, message: str, **fields: Any) -> None:
    logger.log(level, message, extra={"fields": fields})
