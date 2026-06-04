"""Async chat client for Qwen models via DashScope OpenAI-compatible endpoint."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any

import anyio
from openai import APIError, APIConnectionError, APIStatusError, APITimeoutError, AsyncOpenAI

from app.core.config import Settings, get_settings


@dataclass
class ChatToolCall:
    """A tool call requested by the model."""

    id: str
    name: str
    arguments: dict[str, Any] = field(default_factory=dict)


@dataclass
class ChatResult:
    """Normalised result from one chat completion call."""

    ok: bool
    content: str | None = None
    finish_reason: str | None = None
    error: str | None = None
    usage: dict[str, Any] = field(default_factory=dict)
    tool_calls: list[ChatToolCall] = field(default_factory=list)
    assistant_message: dict[str, Any] = field(default_factory=dict)


class ChatClient:
    """Async client that calls Qwen / DashScope through an OpenAI-compatible API."""

    def __init__(self, settings: Settings | None = None) -> None:
        self._client: AsyncOpenAI | None = None
        self._settings_override = settings
        self._configure(settings or get_settings())

    def _configure(self, settings: Settings) -> None:
        self.model = settings.llm_chat_model
        self.enabled = bool(settings.dashscope_api_key)
        self._client = (
            AsyncOpenAI(
                api_key=settings.dashscope_api_key,
                base_url=settings.llm_base_url,
            )
            if self.enabled
            else None
        )

    def _ensure_configured(self) -> None:
        """Refresh config once if this client was created before .env was filled."""

        if self.enabled or self._settings_override is not None:
            return
        get_settings.cache_clear()
        self._configure(get_settings())

    async def generate(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.7,
        max_tokens: int = 2000,
        timeout: float = 30.0,
    ) -> ChatResult:
        """Call the LLM and return a normalised ChatResult."""

        self._ensure_configured()
        if not self.enabled or self._client is None:
            return ChatResult(ok=False, error="LLM 未配置：缺少 DASHSCOPE_API_KEY")

        try:
            with anyio.fail_after(timeout):
                completion = await self._client.chat.completions.create(
                    model=self.model,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                )
        except TimeoutError:
            return ChatResult(
                ok=False,
                error=f"LLM 超时（{timeout:g}s）",
            )
        except APITimeoutError as exc:
            return ChatResult(
                ok=False,
                error=f"LLM 超时：{exc}",
            )
        except APIStatusError as exc:
            return ChatResult(
                ok=False,
                error=f"LLM 错误({exc.status_code})：{exc.message}",
            )
        except APIConnectionError as exc:
            return ChatResult(
                ok=False,
                error=f"LLM 连接失败：{exc}",
            )
        except APIError as exc:
            return ChatResult(
                ok=False,
                error=f"LLM API 错误：{exc}",
            )
        except Exception as exc:
            return ChatResult(
                ok=False,
                error=f"LLM 未知错误：{exc}",
            )

        choice = completion.choices[0] if completion.choices else None
        if choice is None:
            return ChatResult(ok=False, error="LLM 返回空结果")

        return ChatResult(
            ok=True,
            content=choice.message.content,
            finish_reason=choice.finish_reason,
            usage=(
                completion.usage.model_dump()
                if completion.usage
                else {}
            ),
        )

    async def chat(
        self,
        *,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.2,
        max_tokens: int = 2000,
        timeout: float = 30.0,
    ) -> ChatResult:
        """Call the LLM with raw chat messages and optional tool definitions."""

        self._ensure_configured()
        if not self.enabled or self._client is None:
            return ChatResult(ok=False, error="LLM 未配置：缺少 DASHSCOPE_API_KEY")

        request: dict[str, Any] = {
            "model": self.model,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "messages": messages,
        }
        if tools:
            request["tools"] = tools
            request["tool_choice"] = "auto"

        try:
            with anyio.fail_after(timeout):
                completion = await self._client.chat.completions.create(**request)
        except TimeoutError:
            return ChatResult(ok=False, error=f"LLM 超时（{timeout:g}s）")
        except APITimeoutError as exc:
            return ChatResult(ok=False, error=f"LLM 超时：{exc}")
        except APIStatusError as exc:
            return ChatResult(ok=False, error=f"LLM 错误({exc.status_code})：{exc.message}")
        except APIConnectionError as exc:
            return ChatResult(ok=False, error=f"LLM 连接失败：{exc}")
        except APIError as exc:
            return ChatResult(ok=False, error=f"LLM API 错误：{exc}")
        except Exception as exc:
            return ChatResult(ok=False, error=f"LLM 未知错误：{exc}")

        choice = completion.choices[0] if completion.choices else None
        if choice is None:
            return ChatResult(ok=False, error="LLM 返回空结果")

        message = choice.message
        assistant_message = message.model_dump(exclude_none=True)
        return ChatResult(
            ok=True,
            content=message.content,
            finish_reason=choice.finish_reason,
            usage=completion.usage.model_dump() if completion.usage else {},
            tool_calls=self._parse_tool_calls(message.tool_calls or []),
            assistant_message=assistant_message,
        )

    @staticmethod
    def _parse_tool_calls(raw_tool_calls: list[Any]) -> list[ChatToolCall]:
        parsed: list[ChatToolCall] = []
        for tool_call in raw_tool_calls:
            function = getattr(tool_call, "function", None)
            if function is None:
                continue
            arguments: dict[str, Any] = {}
            raw_arguments = getattr(function, "arguments", None)
            if raw_arguments:
                try:
                    arguments = json.loads(raw_arguments)
                except json.JSONDecodeError:
                    arguments = {}
            parsed.append(
                ChatToolCall(
                    id=getattr(tool_call, "id", ""),
                    name=getattr(function, "name", ""),
                    arguments=arguments,
                )
            )
        return parsed


@lru_cache
def get_chat_client() -> ChatClient:
    """Return the shared ChatClient singleton."""

    return ChatClient()
