"""App-wide settings, per ARCHITECTURE.md §4 folder structure (app/config.py).

If this file already exists in your repo, merge these fields in rather than
overwriting — don't lose any settings Person B or earlier scaffolding added.
"""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    llm_provider: str = "groq"  # "openai" | "anthropic" | "groq"
    mistral_api_key: str = ""
    groq_api_key: str = ""

    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/hiremind"

    default_llm_model: str = "openai/gpt-oss-20b"


@lru_cache
def get_settings() -> Settings:
    return Settings()