import asyncio
from datetime import datetime, timezone

import feedparser

from app.ingestion.cleaner import extract_text
from app.ingestion.url_fetcher import (
    assert_public_host,
    fetch_and_clean,
    fetch_bytes,
    validate_url_scheme,
)

# Cap entries processed per feed to prevent unbounded asyncio.gather fan-out.
_MAX_ENTRIES = 100

# Limit concurrent URL fetches to avoid overwhelming the network or target servers.
_FETCH_SEMAPHORE = asyncio.Semaphore(10)


def _parse_date(entry) -> datetime | None:
    """Return a timezone-aware UTC datetime from a feedparser entry, or None."""
    for attr in ("published_parsed", "updated_parsed"):
        t = getattr(entry, attr, None)
        if t:
            try:
                return datetime(*t[:6], tzinfo=timezone.utc)
            except (TypeError, ValueError):
                continue
    return None


def _inline_text(entry) -> str | None:
    """Extract inline text from a feedparser entry's content or summary fields."""
    if hasattr(entry, "content") and entry.content:
        return entry.content[0].get("value", "")
    if hasattr(entry, "summary"):
        return entry.summary
    return None


async def _resolve_entry(entry) -> dict | None:
    """Resolve one feedparser entry to a result dict, or None if it should be skipped."""
    link = getattr(entry, "link", None) or getattr(entry, "id", None)
    if not link:
        return None

    inline = _inline_text(entry)
    if inline and len(inline) > 200:
        return {
            "url": link,
            "title": getattr(entry, "title", None),
            "raw_text": inline,
            "clean_text": extract_text(inline),
            "published_at": _parse_date(entry),
        }

    async with _FETCH_SEMAPHORE:
        try:
            raw_text, clean_text = await fetch_and_clean(link)
        except Exception:
            return None

    return {
        "url": link,
        "title": getattr(entry, "title", None),
        "raw_text": raw_text,
        "clean_text": clean_text,
        "published_at": _parse_date(entry),
    }


async def fetch_rss_entries(feed_url: str) -> list[dict]:
    """Parse an RSS/Atom feed and return a list of entry dicts.

    Validates the feed URL for scheme and SSRF before fetching.
    Entries without a usable link or that fail to fetch are excluded.
    URL fetches for entries without sufficient inline content run concurrently
    (bounded by _FETCH_SEMAPHORE).
    """
    validate_url_scheme(feed_url)
    await assert_public_host(feed_url)

    # Fetch via the validated httpx client (SSRF-safe, size-capped) then parse
    # in a thread to avoid blocking the event loop for the full parse step.
    feed_bytes = await fetch_bytes(feed_url)
    feed = await asyncio.to_thread(feedparser.parse, feed_bytes)
    entries = feed.entries[:_MAX_ENTRIES]
    results = await asyncio.gather(*[_resolve_entry(e) for e in entries])
    return [r for r in results if r is not None]
