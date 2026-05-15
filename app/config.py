from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Required — no defaults so startup fails fast when not configured.
    database_url: str
    app_secret: str

    # Optional with sensible defaults.
    redis_url: str = "redis://localhost:6379/0"
    openrouter_api_key: str = ""
    openrouter_t2_model: str = "openai/gpt-4o-mini"
    openrouter_t3_model: str = "openai/gpt-4o"
    embedding_model: str = "BAAI/bge-small-en-v1.5"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


settings = Settings()
