from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Required — no defaults so startup fails fast when not configured.
    database_url: str
    app_secret: str

    # Optional with sensible defaults.
    redis_url: str = "redis://localhost:6379/0"
    openrouter_api_key: str = ""

    # Model tiers — single place to swap all three:
    #   T1: local encoder models (embedding + claim extraction, no API key needed)
    #   T2: fast LLM via OpenRouter (chat answer, extraction fallback)
    #   T3: strong LLM via OpenRouter (synthesis, eval judge)
    t1_embedding_model: str = "BAAI/bge-small-en-v1.5"   # 384-dim sentence transformer
    t1_extractor_model: str = "fastino/gliner2-base-v1"  # GLiNER2 encoder for claim extraction
    t2_model: str = "deepseek/deepseek-v4-flash"
    t3_model: str = "deepseek/deepseek-v4-pro"
    judge_model: str = "google/gemini-2.5-flash"          # cross-family judge (S7 finding)

    # Back-compat alias — older callers expect settings.t1_model to be the embedding model.
    @property
    def t1_model(self) -> str:
        return self.t1_embedding_model

    # Extractor selection: "gliner" (T1 local) or "llm" (T2 via OpenRouter).
    # Default is "gliner" — local CPU, $0 marginal cost, F1 ≥ LLM SUT on v3.
    extractor: str = "gliner"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


settings = Settings()  # type: ignore[call-arg]  # reads from env/.env at runtime
