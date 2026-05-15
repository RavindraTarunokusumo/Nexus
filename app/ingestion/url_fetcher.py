import asyncio
import ipaddress
import socket
from urllib.parse import urlparse

import httpx

from app.ingestion.cleaner import extract_text

_TIMEOUT = httpx.Timeout(30.0)
_HEADERS = {"User-Agent": "NexusBot/0.1 (private research aggregator; contact operator)"}

# Maximum response body size to process (10 MB).
_MAX_RESPONSE_BYTES = 10 * 1024 * 1024


def validate_url_scheme(url: str) -> None:
    """Reject any scheme that isn't http or https."""
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError(f"Scheme '{parsed.scheme}' is not supported. Only http/https allowed.")


async def assert_public_host(url: str) -> None:
    """Resolve the URL's hostname and reject RFC 1918, loopback, and link-local addresses."""
    hostname = urlparse(url).hostname
    if not hostname:
        raise ValueError("URL has no hostname.")

    try:
        infos = await asyncio.to_thread(socket.getaddrinfo, hostname, None)
    except socket.gaierror as exc:
        raise ValueError(f"Cannot resolve hostname '{hostname}': {exc}") from exc

    for info in infos:
        ip_str = info[4][0]
        try:
            ip = ipaddress.ip_address(ip_str)
        except ValueError:
            continue
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
            raise ValueError(f"URL resolves to a non-routable IP address and cannot be fetched.")


async def fetch_and_clean(url: str) -> tuple[str, str]:
    """Fetch URL and return (raw_html, clean_text).

    Raises ValueError for disallowed schemes or SSRF-blocked addresses.
    Raises httpx.HTTPError on network failures.
    """
    validate_url_scheme(url)
    await assert_public_host(url)

    async with httpx.AsyncClient(timeout=_TIMEOUT, headers=_HEADERS, follow_redirects=True) as client:
        r = await client.get(url)
        r.raise_for_status()
        # Avoid processing enormous responses
        if len(r.content) > _MAX_RESPONSE_BYTES:
            raise ValueError(f"Response exceeds maximum allowed size ({_MAX_RESPONSE_BYTES} bytes).")
        raw_html = r.text

    return raw_html, extract_text(raw_html)
