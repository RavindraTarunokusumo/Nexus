"""Asyncio-safe context variables for pipeline correlation IDs."""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from contextvars import ContextVar
from typing import AsyncIterator

run_id_var: ContextVar[uuid.UUID | None] = ContextVar("run_id", default=None)
document_id_var: ContextVar[uuid.UUID | None] = ContextVar("document_id", default=None)
span_id_var: ContextVar[uuid.UUID | None] = ContextVar("span_id", default=None)


@asynccontextmanager
async def extraction_run(document_id: uuid.UUID) -> AsyncIterator[uuid.UUID]:
    """Mint a run_id, bind run_id + document_id for the duration; Token-reset on exit."""
    run_id = uuid.uuid4()
    t_run = run_id_var.set(run_id)
    t_doc = document_id_var.set(document_id)
    try:
        yield run_id
    finally:
        run_id_var.reset(t_run)
        document_id_var.reset(t_doc)


@asynccontextmanager
async def chat_run() -> AsyncIterator[uuid.UUID]:
    """Mint a run_id for chat answers without binding a document_id."""
    run_id = uuid.uuid4()
    t_run = run_id_var.set(run_id)
    t_doc = document_id_var.set(None)
    t_span = span_id_var.set(None)
    try:
        yield run_id
    finally:
        span_id_var.reset(t_span)
        document_id_var.reset(t_doc)
        run_id_var.reset(t_run)


@asynccontextmanager
async def span_scope(span_id: uuid.UUID) -> AsyncIterator[None]:
    """Bind span_id within an active extraction_run; Token-reset on exit."""
    token = span_id_var.set(span_id)
    try:
        yield
    finally:
        span_id_var.reset(token)


def current_context() -> dict[str, uuid.UUID | None]:
    """Snapshot {run_id, document_id, span_id} for log records / DB writes."""
    return {
        "run_id": run_id_var.get(),
        "document_id": document_id_var.get(),
        "span_id": span_id_var.get(),
    }
