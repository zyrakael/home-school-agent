"""LLM planner for intent recognition and abstract data needs."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, Field, ValidationError

from app.llm.chat_client import ChatClient, get_chat_client
from app.schemas.agent import (
    AgentChatRequest,
    AgentDataNeed,
    AgentExecutionPlan,
    AgentIntent,
    AgentPlanStep,
)

logger = logging.getLogger(__name__)


class PlannerPayload(BaseModel):
    """Structured JSON expected from the LLM planner."""

    intent: AgentIntent
    task_goal: str
    steps: list[AgentPlanStep] = Field(default_factory=list)
    data_needs: list[AgentDataNeed] = Field(default_factory=list)
    response_requirements: list[str] = Field(default_factory=list)
    planner_reason: str = ""


@dataclass
class PlannerResult:
    """Planner output plus non-fatal warnings."""

    plan: AgentExecutionPlan
    request: AgentChatRequest
    warnings: list[str] = field(default_factory=list)


class AgentPlanner:
    """Generate an internal execution plan from a user request."""

    def __init__(self, chat_client: ChatClient | None = None) -> None:
        self.chat_client = chat_client or get_chat_client()

    async def plan(self, request: AgentChatRequest) -> PlannerResult:
        """Return an execution plan, falling back to a deterministic plan on failure."""

        system, user = self._build_prompt(request)
        result = await self.chat_client.generate(
            system_prompt=system,
            user_prompt=user,
            temperature=0.0,
            max_tokens=1200,
        )
        if not result.ok or not result.content:
            warning = result.error or "Planner LLM 调用失败"
            return self._fallback_result(request, warning)

        payload = self._parse_output(result.content)
        if payload is None:
            return self._fallback_result(request, "Planner 输出解析失败，已使用默认执行计划。")

        routed_params = request.params.model_copy(update={"intent": payload.intent})
        routed_request = request.model_copy(update={"params": routed_params})
        data_needs = self._dedupe_data_needs(
            [
                *payload.data_needs,
                *[
                    need
                    for step in payload.steps
                    for need in step.data_needs
                ],
            ]
        )
        if not data_needs:
            data_needs = self._default_data_needs(payload.intent)
        plan = AgentExecutionPlan(
            intent=payload.intent,
            task_goal=payload.task_goal,
            steps=payload.steps or self._default_steps(payload.intent, data_needs),
            data_needs=data_needs,
            response_requirements=payload.response_requirements,
            planner_reason=payload.planner_reason,
        )
        return PlannerResult(plan=plan, request=routed_request)

    @classmethod
    def _fallback_result(cls, request: AgentChatRequest, warning: str) -> PlannerResult:
        intent = request.params.intent
        data_needs = cls._default_data_needs(intent)
        plan = AgentExecutionPlan(
            intent=intent,
            task_goal=request.message or cls._default_goal(intent),
            steps=cls._default_steps(intent, data_needs),
            data_needs=data_needs,
            response_requirements=["生成老师可编辑草稿", "不要编造没有工具支持的数据"],
            planner_reason="fallback",
        )
        return PlannerResult(plan=plan, request=request, warnings=[warning])

    @staticmethod
    def _parse_output(content: str) -> PlannerPayload | None:
        try:
            text = content.strip()
            if text.startswith("```"):
                lines = text.split("\n")
                if lines[-1].strip() == "```":
                    lines = lines[1:-1]
                else:
                    lines = lines[1:]
                text = "\n".join(lines).strip()
            return PlannerPayload.model_validate_json(text)
        except (json.JSONDecodeError, ValidationError, Exception) as exc:
            logger.warning("Planner parse error: %s", exc)
            return None

    @staticmethod
    def _build_prompt(request: AgentChatRequest) -> tuple[str, str]:
        system = """\
        你是家校沟通 Agent 的 Planner。

        你的职责：
        1. 识别用户意图
        2. 拆解任务
        3. 输出抽象 data_needs

        不要输出真实 MCP tool 名称。不要决定 suggested_tools。
        必须只返回严格 JSON，不要添加解释文字。

        可选 intent：
        - RECENT_SUMMARY
        - HOMEWORK_DIAGNOSIS
        - LESSON_FEEDBACK
        - PARENT_REPLY

        可选 data_needs：
        - student_profile
        - recent_homeworks
        - homework_detail
        - wrong_question_stats
        - recent_wrong_questions
        - lesson_performance
        - recent_lesson_performances
        - class_students

        输出 JSON：
        {
        "intent": "RECENT_SUMMARY",
        "task_goal": "一句话任务目标",
        "steps": [
            {
            "step_id": "step_1",
            "goal": "步骤目标",
            "data_needs": ["student_profile"],
            "output_requirements": ["输出要求"]
            }
        ],
        "data_needs": ["student_profile", "recent_homeworks"],
        "response_requirements": ["整体输出要求"],
        "planner_reason": "一句话说明"
        }
        """
        payload: dict[str, Any] = {
            "teacher_id": request.teacher_id,
            "student_id": request.student_id,
            "message": request.message,
            "scene": request.scene,
            "params": request.params.model_dump(),
            "context": request.context,
        }
        user = f"""\
            请为下面请求生成内部执行计划。

            请求 JSON：
            {json.dumps(payload, ensure_ascii=False, indent=2, default=str)}
            """
        return system, user

    @classmethod
    def _default_steps(
        cls,
        intent: AgentIntent,
        data_needs: list[AgentDataNeed],
    ) -> list[AgentPlanStep]:
        return [
            AgentPlanStep(
                step_id="step_1",
                goal=cls._default_goal(intent),
                data_needs=data_needs,
                output_requirements=["按事实数据生成老师可编辑草稿"],
            )
        ]

    @staticmethod
    def _default_goal(intent: AgentIntent) -> str:
        goals = {
            "RECENT_SUMMARY": "总结学生近期学习情况",
            "HOMEWORK_DIAGNOSIS": "分析作业和错题薄弱点",
            "LESSON_FEEDBACK": "生成课后反馈草稿",
            "PARENT_REPLY": "生成家长问题回复草稿",
        }
        return goals[intent]

    @classmethod
    def _default_data_needs(cls, intent: AgentIntent) -> list[AgentDataNeed]:
        defaults: dict[AgentIntent, list[AgentDataNeed]] = {
            "RECENT_SUMMARY": [
                "student_profile",
                "recent_homeworks",
                "recent_lesson_performances",
            ],
            "HOMEWORK_DIAGNOSIS": [
                "student_profile",
                "recent_homeworks",
                "wrong_question_stats",
                "recent_wrong_questions",
            ],
            "LESSON_FEEDBACK": [
                "student_profile",
                "lesson_performance",
                "recent_lesson_performances",
            ],
            "PARENT_REPLY": [
                "student_profile",
                "recent_homeworks",
                "wrong_question_stats",
            ],
        }
        return defaults[intent]

    @staticmethod
    def _dedupe_data_needs(data_needs: list[AgentDataNeed]) -> list[AgentDataNeed]:
        deduped: list[AgentDataNeed] = []
        for need in data_needs:
            if need not in deduped:
                deduped.append(need)
        return deduped
