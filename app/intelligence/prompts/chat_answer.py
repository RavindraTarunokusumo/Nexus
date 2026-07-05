from __future__ import annotations

from datetime import datetime
from typing import Any

SYSTEM_PROMPT = """You answer questions using only the provided Nexus context.
Return JSON with keys: notes, answer, citations.
Use citation labels exactly as provided, such as C1.
If the context does not answer the question, say: I do not have enough evidence to answer that from the current corpus.
Do not use outside knowledge or speculation.

Context blocks may include role annotations:
- primary: main evidence for the answer
- counter_evidence: contradicting or negative-polarity evidence — cite when relevant to nuance the answer
- supersession: facts that supersede or are superseded by primary evidence — prefer superseding facts over superseded ones; when answering about changed facts, mention supersession explicitly.

When context blocks conflict, resolve the conflict using supersession role annotations, lifecycle_state, and block dates: prefer active, superseding, and more recent facts and state the single best-supported answer. Never say the sources conflict or present both values as the final answer.

Before answering, use the 'notes' field to reason briefly and concretely:
1. List each relevant context block with its resolved absolute date — combine the block 'Date:' line with any relative phrase in the excerpt (e.g. 'two weeks ago' relative to that block's date).
2. Ordering ('which happened first / most recent'): sort those events by date and name the first/latest.
3. Duration / elapsed time ('how long', 'how many days/weeks/months ago/between'): state the two anchor dates and compute the difference explicitly.
4. Counting ('how many'): enumerate every distinct matching occurrence across all blocks, then count.
5. If the question's subject (person, place, activity, or role) does not exactly match one in the evidence — e.g. it asks about 'table tennis' when only 'tennis' appears, or 'Dr. Johnson' when only 'Dr. Smith' appears — do NOT answer from the near match; abstain with the insufficient-evidence sentence.
Keep 'notes' short. Put only the final user-facing response in 'answer'."""


def build_user_prompt(
    question: str,
    context_blocks: list[dict[str, Any]],
    *,
    hint: str = "",
    as_of: datetime | None = None,
) -> str:
    blocks = []
    for block in context_blocks:
        lines = [f"[{block['label']}]"]
        published_at = block.get("published_at")
        if published_at is not None:
            lines.append(f"Date: {published_at.strftime('%Y-%m-%d (%a)')}")
        role = block.get("role")
        if role:
            lines.append(f"Role: {role}")
        lines.append(block["text"])
        evidence = block.get("evidence") or []
        if evidence and evidence[0].get("text"):
            lines.append(f"Excerpt: {evidence[0]['text']}")
        blocks.append("\n".join(lines))
    parts: list[str] = []
    if as_of is not None:
        parts.append(f"Current date: {as_of.strftime('%Y-%m-%d (%a)')}")
    parts.extend(["Question:", question, "Context:", "\n\n".join(blocks)])
    if hint:
        parts.append(f"Answer guidance: {hint}")
    return "\n\n".join(parts)
