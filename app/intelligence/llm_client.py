"""OpenRouter HTTP client with per-call tracer logging."""

from __future__ import annotations

from typing import Any, Literal, TypeVar

import httpx
from pydantic import BaseModel, ValidationError, model_validator

from app.observability.tracer import record_agent_run

_BASE_URL = "https://openrouter.ai/api/v1"
_TIMEOUT = httpx.Timeout(60.0)
_COST_PER_TOKEN_USD = 0.14 / 1_000_000

T = TypeVar("T", bound=BaseModel)


class LLMError(Exception):
    """Non-retriable LLM error (4xx or unexpected response structure)."""


class LLMNetworkError(LLMError):
    """5xx or connection failure — callers should abort the pipeline."""


class LLMSchemaError(LLMError):
    """Response arrived but failed Pydantic validation.

    The raw model output is preserved on `raw_output` so callers can include it
    in a correction prompt.
    """

    def __init__(self, message: str, raw_output: str = "") -> None:
        super().__init__(message)
        self.raw_output = raw_output


class LLMClient:
    """Async OpenRouter client. Records every call to agent_runs via tracer."""

    def __init__(self, api_key: str, session_factory: Any) -> None:
        self._api_key = api_key
        self._session_factory = session_factory

    async def complete_json(
        self,
        *,
        model: str,
        system: str,
        user: str,
        response_model: type[T],
        temperature: float = 0.1,
        max_tokens: int = 2000,
        run_type: str = "claim_extraction",
    ) -> tuple[T, int]:
        """Call OpenRouter and return (validated_result, total_tokens).

        Raises LLMNetworkError on 5xx / connection failure.
        Raises LLMError on 4xx.
        Raises LLMSchemaError if the response fails Pydantic validation.
        Always records an agent_runs row (even on failure).
        """
        import os as _os

        if _os.environ.get("EVAL_JSON_SCHEMA", "0") == "1":
            response_format: dict = {
                "type": "json_schema",
                "json_schema": {
                    "name": response_model.__name__,
                    "strict": True,
                    "schema": response_model.model_json_schema(),
                },
            }
        else:
            response_format = {"type": "json_object"}

        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "response_format": response_format,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        raw_output: str | None = None
        total_tokens = 0
        prompt_tokens: int | None = None
        completion_tokens: int | None = None
        call_status = "success"

        try:
            async with httpx.AsyncClient(
                base_url=_BASE_URL,
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                },
                timeout=_TIMEOUT,
            ) as http:
                resp = await http.post("/chat/completions", json=payload)

            if resp.status_code >= 500:
                call_status = f"http_{resp.status_code}"
                raise LLMNetworkError(f"OpenRouter {resp.status_code}: {resp.text[:300]}")

            if resp.status_code >= 400:
                call_status = f"http_{resp.status_code}"
                raise LLMError(f"OpenRouter {resp.status_code}: {resp.text[:300]}")

            data = resp.json()
            try:
                raw_output = data["choices"][0]["message"]["content"]
            except (KeyError, IndexError, TypeError) as exc:
                call_status = "malformed_response"
                raise LLMError(f"Malformed OpenRouter response: {exc}") from exc

            usage = data.get("usage", {})
            total_tokens = usage.get("total_tokens", 0)
            prompt_tokens = usage.get("prompt_tokens")
            completion_tokens = usage.get("completion_tokens")

            if raw_output is None:
                call_status = "schema_error"
                raise LLMSchemaError("LLM returned null content", raw_output="")

            try:
                validated = response_model.model_validate_json(raw_output)
            except (ValueError, ValidationError) as exc:
                call_status = "schema_error"
                raise LLMSchemaError(
                    f"Schema validation failed: {exc}. Raw: {raw_output[:200]}",
                    raw_output=raw_output,
                ) from exc

        except httpx.HTTPError as exc:
            call_status = "network_error"
            raise LLMNetworkError(str(exc)) from exc

        finally:
            await record_agent_run(
                self._session_factory,
                run_type=run_type,
                model=model,
                input_payload={"system": system, "user": user},
                raw_output=raw_output,
                total_tokens=total_tokens,
                status=call_status,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
            )

        return validated, total_tokens


# ---------------------------------------------------------------------------
# Extraction schema — imported by extraction.py and tests
# ---------------------------------------------------------------------------

# Backwards-compatible legacy alias kept for older callers / tests; production
# extractor uses the v2 dotted vocabulary below.
LegacyClaimType = Literal[
    "model_release",
    "benchmark_result",
    "product_launch",
    "pricing_change",
    "research_finding",
    "infrastructure_update",
    "security_issue",
    "funding_event",
    "regulation",
    "forecast",
    "other",
]

# v2 taxonomy — 7 categories × 23 subtypes, dotted "category.subtype".
# Source of truth: app/intelligence/taxonomy.py CATEGORIES dict.
ClaimType = Literal[
    "release.model",
    "release.product",
    "release.dataset",
    "release.weights",
    "performance.benchmark",
    "performance.capability_demo",
    "performance.safety_eval",
    "research.methodology",
    "research.theoretical",
    "research.empirical",
    "research.replication",
    "infra.compute",
    "infra.hardware",
    "infra.deployment",
    "business.funding",
    "business.pricing",
    "business.partnership",
    "business.acquisition",
    "business.personnel",
    "governance.regulation",
    "governance.policy",
    "governance.safety_incident",
    "forecast.prediction",
    "forecast.roadmap_commitment",
]


class ExtractedClaim(BaseModel):
    claim_text: str
    claim_type: ClaimType
    entities: list[str]
    topics: list[str]
    confidence: float
    rationale: str


class ExtractionOutput(BaseModel):
    claims: list[ExtractedClaim]


class SentenceBoundedItem(BaseModel):
    sentence_index: int
    claim: ExtractedClaim | None = None


class SentenceBoundedOutput(BaseModel):
    items: list[SentenceBoundedItem]

    def to_claims(self) -> list[ExtractedClaim]:
        """Flatten to a plain claim list, dropping null entries."""
        return [it.claim for it in self.items if it.claim is not None]


def is_atomic_claim(claim_text: str) -> tuple[bool, str | None]:
    """Heuristic atomicity check (used by the eval runner as a per-claim filter).

    Returns (ok, reason). Rejects claims that look compound by structural signals:
      - two distinct action verbs joined by 'and' in the same claim
      - three or more distinct dates / years
      - three or more distinct non-year numeric quantities
    """
    import re

    t = claim_text
    dates = re.findall(
        r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\w*\s+\d{1,2},?\s+\d{4}|\b\d{4}\b",
        t,
    )
    if len(set(dates)) >= 3:
        return False, f"atomicity: {len(set(dates))} distinct dates"
    if re.search(
        r"\b(?:released|announced|launched|raised|reported|scored|signed|disclosed|acquired|funded|introduced)\b[^.]*\band\b[^.]*\b(?:released|announced|launched|raised|reported|scored|signed|disclosed|acquired|funded|introduced)\b",
        t,
        re.IGNORECASE,
    ):
        return False, "atomicity: two action verbs joined by 'and'"
    numbers = re.findall(r"\b\d+(?:\.\d+)?%?\b", t)
    non_year = [n for n in numbers if not (n.isdigit() and 1900 <= int(n) <= 2100)]
    if len(non_year) >= 3:
        return False, f"atomicity: {len(non_year)} non-year numbers"
    return True, None
