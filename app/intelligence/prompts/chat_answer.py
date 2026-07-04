from __future__ import annotations

from datetime import datetime
from typing import Any

SYSTEM_PROMPT = """You answer questions using only the provided Nexus context.
Return JSON with keys: answer, citations.
Use citation labels exactly as provided, such as C1.
If the context does not answer the question, say: I do not have enough evidence to answer that from the current corpus.
Do not use outside knowledge or speculation.

Context blocks may include role annotations:
- primary: main evidence for the answer
- counter_evidence: contradicting or negative-polarity evidence — cite when relevant to nuance the answer
- supersession: facts that supersede or are superseded by primary evidence — prefer superseding facts over superseded ones; when answering about changed facts, mention supersession explicitly."""


def build_user_prompt(
    question: str,
    context_blocks: list[dict[str, Any]],
    *,
    hint: str = "",
    as_of: datetime | None = None,
) -> str:
    blocks = []
    for block in context_blocks:
        lines = [
            f"[{block['label']}]",
            f"Title: {block.get('document_title') or '(untitled)'}",
            f"URL: {block.get('url') or '(none)'}",
        ]
        published_at = block.get("published_at")
        if published_at is not None:
            lines.append(f"Date: {published_at.strftime('%Y-%m-%d (%a)')}")
        lines.extend(
            [
                f"Object type: {block.get('object_type') or '(unknown)'}",
                f"Score: {block['score']:.3f}",
            ]
        )
        role = block.get("role")
        if role:
            lines.append(f"Role: {role}")
        epistemic_note = block.get("epistemic_note")
        if epistemic_note:
            lines.append(f"Epistemic note: {epistemic_note}")
        lines.extend(["Capsule:", block["text"]])
        blocks.append("\n".join(lines))
    parts: list[str] = []
    if as_of is not None:
        parts.append(f"Current date: {as_of.strftime('%Y-%m-%d (%a)')}")
    parts.extend(["Question:", question, "Context:", "\n\n".join(blocks)])
    if hint:
        parts.append(f"Answer guidance: {hint}")
    return "\n\n".join(parts)
