"""OpenRouter HTTP client with per-call tracer logging."""

from __future__ import annotations

from typing import Any, Literal, TypeVar

import httpx
from pydantic import BaseModel, Field, ValidationError, field_validator

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
# v0.7 semantic-object extraction schema (A3) — the sole SUT response model
# after B5 retired the legacy ExtractedClaim / ExtractionOutput pair.
# Consumed by: extraction prompt (A4), projection layer (A5), eval runner (B5).
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


CoreType = Literal[
    "claim",
    "event",
    "observation",
    "result",
    "risk",
    "argument",
    "explanation",
    "comparison",
    "definition",
    "constraint",
    "question",
    "description",
    "state_change",
    "narrative_development",
    "other",
]


class EpistemicState(BaseModel):
    status: str
    source_authority: Literal["primary", "secondary", "tertiary", "unknown"] = "unknown"
    confidence: float = Field(ge=0.0, le=1.0)
    evidence_quality: Literal["high", "medium", "low", "unknown"] = "unknown"
    uncertainty: str | None = None
    needs_escalation: bool = False


class SemanticObject(BaseModel):
    source_refs: list[str]
    core_type: CoreType
    domain_family: str
    domain_object_type: str
    function: str
    text: str
    original_text: str | None = None
    facets: dict[str, list[str]] = Field(default_factory=dict)
    epistemic: EpistemicState
    salience: float = Field(ge=0.0, le=1.0)
    mvp_claim_type: ClaimType

    @field_validator("source_refs")
    @classmethod
    def source_refs_non_empty(cls, v: list[str]) -> list[str]:
        if len(v) < 1:
            raise ValueError("source_refs must contain at least one entry")
        return v


class SemanticExtractionOutput(BaseModel):
    objects: list[SemanticObject] = Field(default_factory=list)
