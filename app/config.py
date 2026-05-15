from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://nexus:nexus@localhost:5432/nexus"
    redis_url: str = "redis://localhost:6379/0"
    openrouter_api_key: str = ""
    openrouter_t2_model: str = "openai/gpt-4o-mini"
    openrouter_t3_model: str = "openai/gpt-4o"
    embedding_model: str = "BAAI/bge-small-en-v1.5"
    app_secret: str = "changeme"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


settings = Settings()
