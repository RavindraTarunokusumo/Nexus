import hashlib
import re
from urllib.parse import urlparse, urlunparse


def normalize_text(text: str) -> str:
    """Lowercase and collapse whitespace for content hashing."""
    return re.sub(r"\s+", " ", text.lower()).strip()


def content_hash(text: str) -> str:
    """SHA-256 of normalized text."""
    return hashlib.sha256(normalize_text(text).encode("utf-8")).hexdigest()


def normalize_url(url: str) -> str:
    """Lowercase scheme+host, strip trailing slash and fragment."""
    parsed = urlparse(url.strip())
    normalized = parsed._replace(
        scheme=parsed.scheme.lower(),
        netloc=parsed.netloc.lower(),
        path=parsed.path.rstrip("/") or "/",
        fragment="",
    )
    return urlunparse(normalized)


def clean_html(raw: str) -> str:
    """Strip HTML tags as a minimal fallback when trafilatura fails."""
    return re.sub(r"<[^>]+>", " ", raw) ## Comment: this is a very naive tag stripper and may not handle all edge cases; consider using a proper HTML parser for more robust cleaning.


def extract_text(raw: str) -> str:
    """Extract clean text from HTML using trafilatura; fall back to tag stripping."""
    import trafilatura

    clean = trafilatura.extract(raw, include_comments=False, include_tables=True)
    return clean if clean else clean_html(raw)
