"""CLI settings — reads the same .env as the server."""
from pydantic_settings import BaseSettings, SettingsConfigDict


class CLISettings(BaseSettings):
    """CLI configuration. Loaded from .env in the project root.

    `database_url` is optional at construction time — HTTP-only commands
    (search, ingest) don't need it. Read commands enforce it just before use.
    """

    database_url: str = ""
    api_base_url: str = "http://localhost:8000"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")
