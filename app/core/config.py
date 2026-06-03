"""Application configuration via pydantic-settings."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration loaded from .env / environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # App
    app_env: str = "local"

    # MySQL
    database_url: str = "mysql+asyncmy://root:@localhost:3306/zyb?charset=utf8mb4"

    # LLM (DashScope / Qwen)
    dashscope_api_key: str = ""
    llm_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    llm_chat_model: str = "qwen-plus"


@lru_cache()
def get_settings() -> Settings:
    return Settings()
