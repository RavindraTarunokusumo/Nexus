from __future__ import annotations

from typing import Any

SYSTEM_PROMPT = """You answer questions using only the provided Nexus context.
Return JSON with keys: answer, citations.
Use citation labels exactly as provided, such as C1.
If the context does not answer the question, say: I do not have enough evidence to answer that from the current corpus.
Do not use outside knowledge or speculation."""


def build_user_prompt(question: str, context_blocks: list[dict[str, Any]]) -> str:
    blocks = []
    for block in context_blocks:
        claims = "\n".join(f"- {claim['claim_text']}" for claim in block.get("claims", []))
        claims_text = claims if claims else "- No linked extracted claims."
        blocks.append(
            "\n".join(
                [
                    f"[{block['label']}]",
                    f"Title: {block.get('document_title') or '(untitled)'}",
                    f"URL: {block.get('url') or '(none)'}",
                    f"Span ID: {block['span_id']}",
                    f"Score: {block['score']:.3f}",
                    "Span text:",
                    block["text"],
                    "Linked claims:",
                    claims_text,
                ]
            )
        )
    return "\n\n".join(["Question:", question, "Context:", "\n\n".join(blocks)])
