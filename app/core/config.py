"""Application configuration via pydantic-settings."""

from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class MCPServerConfig(BaseModel):
    """Runtime configuration for one MCP server."""

    name: str
    transport: Literal["streamable_http", "stdio"] = "streamable_http"
    url: str | None = None
    headers: dict[str, str] = Field(default_factory=dict)
    command: str | None = None
    args: list[str] = Field(default_factory=list)
    env: dict[str, str] | None = None
    tool_prefixes: list[str] = Field(default_factory=list)
    timeout_seconds: float = 10


class Settings(BaseSettings):
    """Runtime configuration loaded from .env / environment variables."""

    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # App
    app_env: str = "local"

    # MCP
    mcp_servers: list[MCPServerConfig] = Field(default_factory=list)
    mcp_default_timeout_seconds: float = 10

    # LLM (DashScope / Qwen)
    dashscope_api_key: str = ""
    llm_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    llm_chat_model: str = "qwen-plus"


@lru_cache()
def get_settings() -> Settings:
    return Settings()
