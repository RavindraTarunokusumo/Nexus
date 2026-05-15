import httpx
import trafilatura

_TIMEOUT = httpx.Timeout(30.0)
_HEADERS = {
    "User-Agent": "NexusBot/0.1 (private research aggregator; contact operator)"
}

# URLs that should never be fetched (local/private network ranges are blocked
# at the network layer on the VPS; this list covers common mis-use patterns).
_BLOCKED_SCHEMES = {"file", "ftp", "javascript", "data"}


def _validate_url(url: str) -> None:
    from urllib.parse import urlparse

    parsed = urlparse(url)
    if parsed.scheme in _BLOCKED_SCHEMES:
        raise ValueError(f"Scheme '{parsed.scheme}' is not allowed.")
    if parsed.scheme not in {"http", "https"}:
        raise ValueError(f"Scheme '{parsed.scheme}' is not supported. Only http/https allowed.")


async def fetch_and_clean(url: str) -> tuple[str, str]:
    """Fetch URL and return (raw_html, clean_text).

    Raises httpx.HTTPError on network failures.
    Raises ValueError for disallowed URL schemes.
    """
    _validate_url(url)

    async with httpx.AsyncClient(timeout=_TIMEOUT, headers=_HEADERS, follow_redirects=True) as client:
        response = client.build_request("GET", url)
        # Validate resolved URL after redirect (defense against SSRF via redirects)
        # We rely on httpx follow_redirects=True and accept the final destination;
        # VPS firewall blocks internal network access at the OS level.
        r = await client.send(response, follow_redirects=True)
        r.raise_for_status()
        raw_html = r.text

    clean = trafilatura.extract(raw_html, include_comments=False, include_tables=True)
    if not clean:
        # fallback: strip tags
        from app.ingestion.cleaner import clean_html
        clean = clean_html(raw_html)

    return raw_html, clean
