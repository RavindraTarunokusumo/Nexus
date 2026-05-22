"""OpenRouter HTTP client with per-call tracer logging."""

from __future__ import annotations

from typing import Any, Literal, TypeVar

import httpx
from pydantic import BaseModel, ValidationError

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
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "response_format": {"type": "json_object"},
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

        if raw_output is None:
            raise LLMSchemaError("LLM returned null content", raw_output="")

        try:
            validated = response_model.model_validate_json(raw_output)
        except (ValueError, ValidationError) as exc:
            raise LLMSchemaError(
                f"Schema validation failed: {exc}. Raw: {raw_output[:200]}",
                raw_output=raw_output,
            ) from exc

        return validated, total_tokens


# ---------------------------------------------------------------------------
# Extraction schema — imported by extraction.py and tests
# ---------------------------------------------------------------------------

ClaimType = Literal[
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


class ExtractedClaim(BaseModel):
    claim_text: str
    claim_type: ClaimType
    entities: list[str]
    topics: list[str]
    confidence: float
    rationale: str


class ExtractionOutput(BaseModel):
    claims: list[ExtractedClaim]
