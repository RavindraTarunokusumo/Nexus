"""Unit tests for configure_logging and RunContextFilter."""
from __future__ import annotations

import io
import json
import logging
import uuid

import pytest

from app.observability import logger as obs_logger
from app.observability.run_context import extraction_run, span_scope


@pytest.fixture(autouse=True)
def reset_logging():
    """Force logger reconfiguration between tests."""
    obs_logger._configured = False
    root = logging.getLogger()
    root.handlers.clear()
    yield
    obs_logger._configured = False
    root.handlers.clear()


def _capture_json_log(level: str = "DEBUG") -> tuple[logging.Logger, io.StringIO]:
    """Configure logging with a StringIO stream; return (test_logger, stream)."""
    obs_logger.configure_logging(level=level, fmt="json", force=True)
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(obs_logger._make_json_formatter())
    handler.addFilter(obs_logger.RunContextFilter())  # Attach filter to handler
    test_logger = logging.getLogger("test.capture")
    test_logger.addHandler(handler)
    test_logger.setLevel(logging.DEBUG)
    return test_logger, stream


def test_configure_logging_is_idempotent():
    obs_logger.configure_logging()
    handler_count = len(logging.getLogger().handlers)
    obs_logger.configure_logging()
    assert len(logging.getLogger().handlers) == handler_count


def test_configure_logging_force_reconfigures():
    obs_logger.configure_logging()
    obs_logger.configure_logging(force=True)
    # Should not raise; just verify it ran twice
    assert obs_logger._configured is True


def test_json_formatter_emits_required_fields():
    logger, stream = _capture_json_log()
    logger.info("hello world")
    record = json.loads(stream.getvalue().strip())
    assert record["msg"] == "hello world"
    assert record["level"] == "INFO"
    assert "ts" in record
    assert "logger" in record


@pytest.mark.asyncio
async def test_run_context_filter_injects_ids():
    logger, stream = _capture_json_log()
    doc_id = uuid.uuid4()
    async with extraction_run(doc_id) as run_id:
        span_id = uuid.uuid4()
        async with span_scope(span_id):
            logger.info("inside scope")
    record = json.loads(stream.getvalue().strip())
    assert record["run_id"] == str(run_id)
    assert record["document_id"] == str(doc_id)
    assert record["span_id"] == str(span_id)


def test_run_context_filter_survives_broken_contextvar(caplog):
    """Filter must return True (keep record) even if contextvar lookup fails."""
    from app.observability.logger import RunContextFilter

    f = RunContextFilter()
    record = logging.LogRecord(
        name="test", level=logging.INFO, pathname="", lineno=0,
        msg="ok", args=(), exc_info=None,
    )
    # Simulate failure by patching current_context to raise
    import app.observability.logger as mod
    original = mod.current_context
    mod.current_context = lambda: (_ for _ in ()).throw(RuntimeError("boom"))
    try:
        result = f.filter(record)
    finally:
        mod.current_context = original
    assert result is True


def test_json_formatter_handles_non_serialisable_extra():
    logger, stream = _capture_json_log()
    logger.info("extra", extra={"obj": object()})
    record = json.loads(stream.getvalue().strip())
    assert "obj" in record  # repr fallback kept the field
