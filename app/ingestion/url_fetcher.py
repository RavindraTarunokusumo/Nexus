from urllib.parse import urlparse

import httpx

from app.ingestion.cleaner import extract_text

_TIMEOUT = httpx.Timeout(30.0)
_HEADERS = {"User-Agent": "NexusBot/0.1 (private research aggregator; contact operator)"}


def _validate_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError(f"Scheme '{parsed.scheme}' is not supported. Only http/https allowed.")


async def fetch_and_clean(url: str) -> tuple[str, str]:
    """Fetch URL and return (raw_html, clean_text).

    Raises httpx.HTTPError on network failures.
    Raises ValueError for disallowed URL schemes.
    """
    _validate_url(url)

    async with httpx.AsyncClient(timeout=_TIMEOUT, headers=_HEADERS, follow_redirects=True) as client:
        r = await client.get(url)
        r.raise_for_status()
        raw_html = r.text

    return raw_html, extract_text(raw_html)
