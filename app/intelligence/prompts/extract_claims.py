"""System and user prompt builders for claim extraction."""

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
    return (
        f"{original_user}\n\n"
        f"---\n"
        f"Your previous response was invalid.\n"
        f"Error: {error}\n\n"
        f"Previous response:\n{invalid_response}\n\n"
        f"Please correct your response and return valid JSON matching the required schema exactly."
    )
