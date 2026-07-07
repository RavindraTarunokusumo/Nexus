from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Required — no defaults so startup fails fast when not configured.
    database_url: str
    app_secret: str

    # Optional with sensible defaults.
    redis_url: str = "redis://localhost:6379/0"
    openrouter_api_key: str = ""
    qwen_cloud_api_key: str = ""
    llm_base_url: str = "https://openrouter.ai/api/v1"

    # Model tiers — single place to swap all three:
    #   T1: local sentence-transformer (embedding, no API key needed)
    #   T2: fast LLM via llm_base_url (extraction, relation classification, chat)
    #   T3: strong LLM via llm_base_url (synthesis / query)
    # Defaults are Qwen Cloud (DashScope) model ids; override per env.
    t1_model: str = "BAAI/bge-small-en-v1.5"
    t2_model: str = "qwen3.6-flash"
    # Span/claim extraction only; empty falls back to T2. The 2026-04-16 flash
    # snapshot was gated and rejected: 0.820->0.531 (docs/experiments 2026-07-06).
    extraction_model: str = ""
    # Model ids that reject enable_thinking=false; the flag is omitted for them.
    thinking_locked_models: str = "qwen3.7-max-2026-05-17"
    # Process-global request pacing for rate-capped endpoints (0 = off).
    llm_max_rpm: int = 0
    # Send response_format=json_object. Off for endpoints whose JSON mode is
    # slow/flaky (e.g. NVIDIA integrate.api); prompts still demand JSON and the
    # client strips markdown fences before validation.
    llm_json_response_format: bool = True
    t2_model_force: str = ""
    t2_concurrency: int = 4
    t3_model: str = "qwen3.7-max"

    # Default domain pack loaded for /chat/answer and session turns.
    default_pack_id: str = "personal_ai_tech"

    # Per-sub-query retrieval floor before shared rerank (B3); off until A/B gate passes.
    retrieval_subquery_slots: bool = False

    # Sentence-window retrieval (deterministic ingest, no extraction graph).
    sentence_window_size: int = 2
    sentence_window_top_k: int = 15
    sentence_window_fetch_k: int = 60
    # Recency vs semantic blend for sentence-window ranking. Low by default: raw
    # sentences have no supersession edges, so a high recency weight buries old-but-
    # relevant evidence (fatal for "which happened first" questions). Semantic
    # dominates; the reader + ordering handle temporal.
    sentence_window_recency_weight: float = 0.05

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @property
    def llm_api_key(self) -> str:
        return self.qwen_cloud_api_key or self.openrouter_api_key


settings = Settings()  # type: ignore[call-arg]  # reads from env/.env at runtime
