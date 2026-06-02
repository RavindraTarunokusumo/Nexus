"""Shared helpers used by multiple prompt builders in this package."""

from __future__ import annotations


def build_correction_prompt(
    original_user: str,
    invalid_response: str,
    error: str,
    schema_name: str,
) -> str:
    """Build a correction-retry prompt referencing the named response schema."""
    return (
        f"{original_user}\n\n"
        f"---\n"
        f"Your previous response was invalid.\n"
        f"Error: {error}\n\n"
        f"Previous response:\n{invalid_response}\n\n"
        f"Please correct your response and return valid JSON matching the {schema_name} schema exactly."
    )
