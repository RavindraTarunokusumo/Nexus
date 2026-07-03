from __future__ import annotations

from pydantic import BaseModel


class IntentClassification(BaseModel):
    intent: str
    shape: str = "general"


SYSTEM_PROMPT = (
    "Classify the user's question into exactly one query intent from the provided list. "
    "Return JSON with keys 'intent' and 'shape'. "
    "The 'intent' value must be an intent name exactly as listed, or 'general' if none fits. "
    "The 'shape' value must be one of: factoid, multi_doc, current_state, conflict, general. "
    "Shape definitions: "
    "factoid — single-fact lookup (date, number, name, score); "
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
