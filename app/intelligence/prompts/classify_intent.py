from __future__ import annotations

from pydantic import BaseModel


class IntentClassification(BaseModel):
    intent: str


SYSTEM_PROMPT = (
    "Classify the user's question into exactly one query intent from the provided list. "
    "Return JSON with key 'intent' containing the intent name exactly as listed. "
    "If no intent fits, return 'general'."
)


def build_classify_prompt(question: str, intent_names: list[str]) -> str:
    joined = ", ".join(intent_names)
    return f"Available intents: {joined}\n\nQuestion: {question}"
