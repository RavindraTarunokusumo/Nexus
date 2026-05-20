from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Required — no defaults so startup fails fast when not configured.
    database_url: str
    app_secret: str

    # Optional with sensible defaults.
    redis_url: str = "redis://localhost:6379/0"
    openrouter_api_key: str = ""

    # Model tiers — single place to swap all three:
    #   T1: local sentence-transformer (embedding, no API key needed)
    #   T2: fast LLM via OpenRouter (claim extraction)
    #   T3: strong LLM via OpenRouter (synthesis / query — future)
    t1_model: str = "BAAI/bge-small-en-v1.5"
    t2_model: str = "deepseek/deepseek-v4-flash"
    t3_model: str = "deepseek/deepseek-v4-pro"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


settings = Settings()  # type: ignore[call-arg]  # reads from env/.env at runtime
