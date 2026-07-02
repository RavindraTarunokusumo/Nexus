from __future__ import annotations

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


def build_user_prompt(question: str, context_blocks: list[dict[str, Any]]) -> str:
    blocks = []
    for block in context_blocks:
        lines = [
            f"[{block['label']}]",
            f"Title: {block.get('document_title') or '(untitled)'}",
            f"URL: {block.get('url') or '(none)'}",
            f"Object type: {block.get('object_type') or '(unknown)'}",
            f"Score: {block['score']:.3f}",
        ]
        role = block.get("role")
        if role:
            lines.append(f"Role: {role}")
        epistemic_note = block.get("epistemic_note")
        if epistemic_note:
            lines.append(f"Epistemic note: {epistemic_note}")
        lines.extend(["Capsule:", block["text"]])
        blocks.append("\n".join(lines))
    return "\n\n".join(["Question:", question, "Context:", "\n\n".join(blocks)])
