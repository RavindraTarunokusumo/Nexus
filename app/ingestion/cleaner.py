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
    """Strip obvious HTML tags as a minimal fallback when trafilatura fails."""
    return re.sub(r"<[^>]+>", " ", raw)
