"""Shared validators for API request schemas."""

import re

_IDENTIFIER_RE = re.compile(r"^[a-z0-9_\-]{1,64}$")


def validate_identifier(value: str) -> str:
    """Allow only safe, short, lowercased identifiers.

    Used to constrain values that flow into filesystem paths (domain pack
    ids) or other contexts where path traversal would otherwise be possible.
    """
    if not _IDENTIFIER_RE.match(value):
        raise ValueError("must match ^[a-z0-9_-]{1,64}$ (lowercase, digits, underscores, hyphens)")
    return value
