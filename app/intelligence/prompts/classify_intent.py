from __future__ import annotations

from pydantic import BaseModel

from app.intelligence.router import QUESTION_SHAPES


class IntentClassification(BaseModel):
    intent: str
    shape: str = "general"


SYSTEM_PROMPT = (
    "Classify the user's question into exactly one query intent from the provided list. "
    "Return JSON with keys 'intent' and 'shape'. "
    "The 'intent' value must be an intent name exactly as listed, or 'general' if none fits. "
    f"The 'shape' value must be one of: {', '.join(QUESTION_SHAPES)}. "
    "Shape definitions: "
    "factoid — single-fact lookup (a date, number, or name) with no comparison or "
    "arithmetic between events; "
    "temporal — event ordering ('which happened first'), duration ('how long had I been'), "
    "elapsed time ('how many days ago/between'), and date-arithmetic questions; "
    "multi_doc — aggregation or comparison across sources; "
    "current_state — present-tense state query; "
    "conflict — verification or disputed claims; "
    "general — everything else."
)


def build_classify_prompt(question: str, intent_names: list[str]) -> str:
    if intent_names:
        joined = ", ".join(intent_names)
        intents_line = f"Available intents: {joined}"
    else:
        intents_line = "Available intents: (none — use 'general' for intent)"
    return f"{intents_line}\n\nQuestion: {question}"
