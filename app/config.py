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
    extraction_model: str = (
        "qwen3.6-flash-2026-04-16"  # Span/claim extraction only; empty falls back to T2.
    )
    t2_model_force: str = ""
    t2_concurrency: int = 4
    t3_model: str = "qwen3.7-max"

    # Default domain pack loaded for /chat/answer and session turns.
    default_pack_id: str = "personal_ai_tech"

    # Per-sub-query retrieval floor before shared rerank (B3); off until A/B gate passes.
    retrieval_subquery_slots: bool = False

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @property
    def llm_api_key(self) -> str:
        return self.qwen_cloud_api_key or self.openrouter_api_key


settings = Settings()  # type: ignore[call-arg]  # reads from env/.env at runtime
