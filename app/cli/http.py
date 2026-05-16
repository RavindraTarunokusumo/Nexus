"""CLI HTTP client wrappers. Each function calls the FastAPI server."""

from __future__ import annotations

import uuid
from typing import Any

import httpx

_TIMEOUT = httpx.Timeout(10.0)


class CLIHttpError(Exception):
    """Raised when the API returns a non-2xx response."""


async def _request(method: str, base_url: str, path: str, **kwargs) -> Any:
    async with httpx.AsyncClient(base_url=base_url, timeout=_TIMEOUT) as client:
        response = await client.request(method, path, **kwargs)
        if not response.is_success:
            try:
                detail = response.json()
            except Exception:
                detail = response.text
            raise CLIHttpError(f"{method} {path} → {response.status_code}: {detail}")
        return response.json()


async def ingest_url(base_url: str, url: str, source_name: str, domain_pack: str) -> dict:
    return await _request(
        "POST",
        base_url,
        "/ingest/url",
        json={"url": url, "source_name": source_name, "domain_pack": domain_pack},
    )


async def ingest_text(
    base_url: str, *, title: str, text: str, source_name: str, domain_pack: str
) -> dict:
    return await _request(
        "POST",
        base_url,
        "/ingest/text",
        json={"title": title, "text": text, "source_name": source_name, "domain_pack": domain_pack},
    )


async def ingest_rss(base_url: str, source_id: uuid.UUID) -> dict:
    return await _request("POST", base_url, f"/ingest/rss/{source_id}")


async def search_spans(base_url: str, query: str, top_k: int) -> list[dict]:
    return await _request(
        "POST",
        base_url,
        "/search/spans",
        json={"query": query, "top_k": top_k},
    )
