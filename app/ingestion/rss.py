from datetime import datetime, timezone

import feedparser

from app.ingestion.url_fetcher import fetch_and_clean


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


async def fetch_rss_entries(feed_url: str) -> list[dict]:
    """Parse an RSS/Atom feed and return a list of entry dicts.

    Each dict contains: url, title, raw_text, clean_text, published_at.
    Entries without a usable link are skipped.
    """
    feed = feedparser.parse(feed_url)
    results = []

    for entry in feed.entries:
        link = getattr(entry, "link", None) or getattr(entry, "id", None)
        if not link:
            continue

        title = getattr(entry, "title", None)
        published_at = _parse_date(entry)

        # Prefer full-text from entry summary/content; fall back to fetching the URL.
        inline_text = None
        if hasattr(entry, "content") and entry.content:
            inline_text = entry.content[0].get("value", "")
        elif hasattr(entry, "summary"):
            inline_text = entry.summary

        if inline_text and len(inline_text) > 200:
            import trafilatura
            clean = trafilatura.extract(inline_text, include_comments=False)
            if not clean:
                from app.ingestion.cleaner import clean_html
                clean = clean_html(inline_text)
            raw_text = inline_text
        else:
            try:
                raw_text, clean = await fetch_and_clean(link)
            except Exception:
                # Skip entries we cannot fetch
                continue

        results.append(
            {
                "url": link,
                "title": title,
                "raw_text": raw_text,
                "clean_text": clean,
                "published_at": published_at,
            }
        )

    return results
