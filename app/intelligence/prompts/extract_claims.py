"""System and user prompt builders for claim extraction."""

from __future__ import annotations

from app.intelligence.prompts import _shared

## Comment: Consider including examples (1-2 shot prompting) in the SYSTEM_PROMPT to guide the model towards the desired output format and content, especially if the claims can be complex or nuanced.
SYSTEM_PROMPT = """\
You are a precise claim extractor for an intelligence research system.

Extract only atomic propositions directly supported by the provided text.

Rules:
- Each claim expresses exactly one proposition.
- Each claim must stand alone without outside context.
- Do not infer, speculate, or use outside knowledge.
- Prefer fewer high-quality claims over many low-confidence ones.
- Output valid JSON with a "claims" array matching the required schema exactly.
"""


def build_user_prompt(span_text: str, metadata: dict) -> str:
    """Build the initial extraction prompt for one span."""
    lines = ["Extract claims from the following text."]
    if metadata.get("title"):
        lines.append(f"Article title: {metadata['title']}")
    if metadata.get("source_name"):
        lines.append(f"Source: {metadata['source_name']}")
    if metadata.get("published_at"):
        lines.append(f"Published: {metadata['published_at']}")
    lines.append(f"\nText:\n{span_text}")
    return "\n".join(lines)


def build_correction_prompt(original_user: str, invalid_response: str, error: str) -> str:
    """Append correction instructions when the model returns invalid output."""
    return _shared.build_correction_prompt(
        original_user, invalid_response, error, schema_name="required"
    )
