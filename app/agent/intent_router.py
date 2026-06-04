"""LLM-based intent routing for Agent chat requests."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field

from pydantic import BaseModel, Field, ValidationError

from app.llm.chat_client import ChatClient, get_chat_client
from app.schemas.agent import AgentChatParams, AgentChatRequest, AgentIntent

logger = logging.getLogger(__name__)


class IntentRoutePayload(BaseModel):
    """Structured intent routing output expected from the LLM."""

    intent: AgentIntent
    time_range: str | None = None
    subject: str | None = None
    lesson_id: str | None = None
    tone: str | None = None
    length: str | None = None
    parent_question: str | None = None
    reason: str = ""


@dataclass
class IntentRouteResult:
    """Request after routing, plus non-fatal routing warnings."""

    request: AgentChatRequest
    warnings: list[str] = field(default_factory=list)


class IntentRouter:
    """Classify the user's message into one MVP Agent intent using the LLM."""

    def __init__(self, chat_client: ChatClient | None = None) -> None:
        self.chat_client = chat_client or get_chat_client()

    async def route(self, request: AgentChatRequest) -> IntentRouteResult:
        system, user = self._build_prompt(request)
        result = await self.chat_client.generate(
            system_prompt=system,
            user_prompt=user,
            temperature=0.0,
            max_tokens=800,
        )
        if not result.ok or not result.content:
            return IntentRouteResult(
                request=request,
                warnings=[result.error or "意图识别失败，沿用请求中的默认意图。"],
            )

        parsed = self._parse_output(result.content)
        if parsed is None:
            return IntentRouteResult(
                request=request,
                warnings=["意图识别输出解析失败，沿用请求中的默认意图。"],
            )

        params = self._merge_params(request.params, parsed)
        routed = request.model_copy(update={"params": params})
        return IntentRouteResult(request=routed)

    @staticmethod
    def _merge_params(
        current: AgentChatParams,
        routed: IntentRoutePayload,
    ) -> AgentChatParams:
        update: dict[str, object] = {"intent": routed.intent}
        for field_name in (
            "time_range",
            "subject",
            "lesson_id",
            "tone",
            "length",
            "parent_question",
        ):
            value = getattr(routed, field_name)
            if value not in (None, ""):
                update[field_name] = value
        return current.model_copy(update=update)

    @staticmethod
    def _parse_output(content: str) -> IntentRoutePayload | None:
        try:
            text = content.strip()
            if text.startswith("```"):
                lines = text.split("\n")
                if lines[-1].strip() == "```":
                    lines = lines[1:-1]
                else:
                    lines = lines[1:]
                text = "\n".join(lines).strip()
            return IntentRoutePayload.model_validate_json(text)
        except (json.JSONDecodeError, ValidationError, Exception) as exc:
            logger.warning("Intent route parse error: %s", exc)
            return None

    @staticmethod
    def _build_prompt(request: AgentChatRequest) -> tuple[str, str]:
        system = """\
你是家校沟通 Agent 的意图识别器。

只根据用户输入和请求上下文判断最合适的 intent，并抽取可用于后续 Agent 的参数。
必须只返回严格 JSON，不要添加解释文字。

可选 intent：
- RECENT_SUMMARY：总结学生近期整体学习情况
- HOMEWORK_DIAGNOSIS：分析作业、错题、薄弱点、学习问题
- LESSON_FEEDBACK：生成某节课后的反馈
- PARENT_REPLY：回复家长问题、生成家长沟通话术或内部处理建议

输出 JSON 格式：
{
  "intent": "RECENT_SUMMARY",
  "time_range": "7d",
  "subject": "数学",
  "lesson_id": null,
  "tone": "温和",
  "length": "标准版",
  "parent_question": null,
  "reason": "一句话说明判断依据"
}
"""
        payload = {
            "teacher_id": request.teacher_id,
            "student_id": request.student_id,
            "message": request.message,
            "scene": request.scene,
            "params": request.params.model_dump(),
            "context": request.context,
        }
        user = f"""\
请识别下面请求的意图并抽取参数。

请求 JSON：
{json.dumps(payload, ensure_ascii=False, indent=2, default=str)}
"""
        return system, user
