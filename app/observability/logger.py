"""Centralized logging configuration for Nexus — stdlib + JSON formatter."""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone

from app.observability.run_context import current_context

_configured = False


class RunContextFilter(logging.Filter):
    """Inject run_id, document_id, span_id from active contextvars into every log record."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            ctx = current_context()
            record.run_id = str(ctx["run_id"]) if ctx["run_id"] else None
            record.document_id = str(ctx["document_id"]) if ctx["document_id"] else None
            record.span_id = str(ctx["span_id"]) if ctx["span_id"] else None
        except Exception:
            record.run_id = None
            record.document_id = None
            record.span_id = None
        return True


class _JsonFormatter(logging.Formatter):
    """Emit one JSON object per log record."""

    _SKIP = {
        "msg",
        "message",
        "args",
        "exc_info",
        "exc_text",
        "stack_info",
        "levelname",
        "levelno",
        "pathname",
        "filename",
        "module",
        "created",
        "msecs",
        "relativeCreated",
        "thread",
        "threadName",
        "processName",
        "process",
        "name",
        "funcName",
        "lineno",
        "taskName",
    }

    def format(self, record: logging.LogRecord) -> str:
        record.message = record.getMessage()
        payload: dict = {
            "ts": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.message,
            "run_id": getattr(record, "run_id", None),
            "document_id": getattr(record, "document_id", None),
            "span_id": getattr(record, "span_id", None),
        }
        for key, value in record.__dict__.items():
            if key not in self._SKIP and not key.startswith("_"):
                try:
                    json.dumps(value)
                    payload[key] = value
                except (TypeError, ValueError):
                    payload[key] = repr(value)
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload)


def _make_json_formatter() -> _JsonFormatter:
    return _JsonFormatter()


def configure_logging(
    level: str | None = None,
    fmt: str | None = None,
    *,
    force: bool = False,
) -> None:
    """Configure root logger with RunContextFilter and JSON (default) or console formatter.

    Idempotent — second call is a no-op unless force=True.
    Reads LOG_LEVEL (default INFO) and LOG_FORMAT (default 'json') from env.
    """
    global _configured
    if _configured and not force:
        return

    effective_level = (level or os.environ.get("LOG_LEVEL", "INFO")).upper()
    effective_fmt = fmt or os.environ.get("LOG_FORMAT", "json")

    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(effective_level)

    handler = logging.StreamHandler()
    handler.setLevel(effective_level)

    if effective_fmt == "json":
        handler.setFormatter(_make_json_formatter())
    else:
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)-8s %(name)s %(message)s"))

    ctx_filter = RunContextFilter()
    root.addFilter(ctx_filter)
    root.addHandler(handler)
    _configured = True
