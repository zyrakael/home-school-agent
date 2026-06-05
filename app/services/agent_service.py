"""Agent service — ask the MCP tool-calling chain to draft a response."""

from __future__ import annotations

import logging
from uuid import uuid4

from app.agent.intent_router import IntentRouter
from app.agent.mcp_agent import AgentRunResult, MCPAgentChain
from app.agent.planner import AgentPlanner, PlannerResult
from app.agent.prompt_builder import LLMResponsePayload
from app.agent.tool_router import ToolRouter
from app.schemas.agent import AgentChatRequest, AgentExecutionPlan, AgentPlanStep
from app.schemas.response import AgentChatResponse, AgentSection
from app.skills.selector import SkillSelector

logger = logging.getLogger(__name__)


def _parse_days(value: str | None, default: int) -> int:
    if not value:
        return default
    try:
        return int(value.rstrip("d"))
    except ValueError:
        return default


class AgentService:
    """Stateless Agent service backed by an MCP tool-calling chain."""

    def __init__(
        self,
        agent: MCPAgentChain | None = None,
        intent_router: IntentRouter | None = None,
        planner: AgentPlanner | None = None,
        skill_selector: SkillSelector | None = None,
        tool_router: ToolRouter | None = None,
    ) -> None:
        self.agent = agent or MCPAgentChain()
        self.planner = planner or (
            _IntentRouterPlannerAdapter(intent_router) if intent_router else AgentPlanner()
        )
        self.skill_selector = skill_selector or SkillSelector()
        self.tool_router = tool_router or ToolRouter()

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    async def generate(self, request: AgentChatRequest) -> AgentChatResponse:
        """Generate a draft from a plan, local skills, and allowed MCP tools."""

        planned = await self.planner.plan(request)
        routed_request = planned.request
        plan = planned.plan
        intent = plan.intent
        skill_selection = self.skill_selector.select(intent)
        tool_route = self.tool_router.route(plan)
        run_result = await self.agent.run(
            routed_request,
            execution_plan=plan,
            selected_skills=skill_selection.skills,
            allowed_tools=tool_route.allowed_tools,
        )
        parsed = self._parse_agent_output(run_result)
        if parsed is None:
            reason = run_result.error or "LLM 输出解析失败"
            return self._error_response(
                intent=intent,
                title=self._default_title(routed_request),
                content="AI 暂时没有生成可用草稿，请稍后重试。",
                evidence=run_result.evidence,
                warnings=[
                    *planned.warnings,
                    *skill_selection.warnings,
                    *tool_route.warnings,
                    *run_result.warnings,
                    reason,
                ],
            )

        return self._base_response(
            intent=intent,
            title=parsed.title,
            content=parsed.content,
            sections=parsed.sections,
            evidence=run_result.evidence,
            warnings=[
                *planned.warnings,
                *skill_selection.warnings,
                *tool_route.warnings,
                *run_result.warnings,
            ],
        )

    # ------------------------------------------------------------------
    # Shared response factory
    # ------------------------------------------------------------------

    @staticmethod
    def _base_response(
        *,
        intent: str,
        title: str,
        content: str,
        sections: list[AgentSection],
        evidence: list[str],
        warnings: list[str] | None = None,
    ) -> AgentChatResponse:
        return AgentChatResponse(
            request_id=f"req_{uuid4().hex[:12]}",
            intent=intent,
            status="success",
            title=title,
            content=content,
            sections=sections,
            evidence=evidence,
            warnings=warnings or [],
            available_actions=["copy", "edit", "regenerate", "shorten", "change_tone"],
        )

    @staticmethod
    def _error_response(
        *,
        intent: str,
        title: str,
        content: str,
        evidence: list[str],
        warnings: list[str],
    ) -> AgentChatResponse:
        return AgentChatResponse(
            request_id=f"req_{uuid4().hex[:12]}",
            intent=intent,
            status="failed",
            title=title,
            content=content,
            sections=[],
            evidence=evidence,
            warnings=warnings,
            available_actions=["regenerate"],
        )

    @staticmethod
    def _parse_agent_output(result: AgentRunResult) -> LLMResponsePayload | None:
        """Parse agent output as JSON matching LLMResponsePayload.

        Handles markdown code fences the model may wrap JSON in.
        """
        if result.error or not result.content:
            return None
        try:
            text = result.content.strip()
            if text.startswith("```"):
                lines = text.split("\n")
                if lines[-1].strip() == "```":
                    lines = lines[1:-1]
                else:
                    lines = lines[1:]
                text = "\n".join(lines).strip()
            return LLMResponsePayload.model_validate_json(text)
        except Exception as exc:
            logger.warning("LLM output parse error: %s", exc)
            return None

    # ------------------------------------------------------------------
    # Titles
    # ------------------------------------------------------------------

    @staticmethod
    def _default_title(request: AgentChatRequest) -> str:
        intent = request.params.intent
        if intent == "RECENT_SUMMARY":
            days = _parse_days(request.params.time_range, default=7)
            return f"近{days}天学习情况总结"
        if intent == "HOMEWORK_DIAGNOSIS":
            return "作业与错题诊断"
        if intent == "LESSON_FEEDBACK":
            return "课后反馈草稿"
        if intent == "PARENT_REPLY":
            return "家长问题回复草稿"
        return "AI 草稿"


class _IntentRouterPlannerAdapter:
    """Compatibility adapter for tests and legacy callers that provide IntentRouter."""

    def __init__(self, intent_router: IntentRouter | None = None) -> None:
        self.intent_router = intent_router or IntentRouter()

    async def plan(self, request: AgentChatRequest) -> PlannerResult:
        routed = await self.intent_router.route(request)
        intent = routed.request.params.intent
        data_needs = AgentPlanner._default_data_needs(intent)
        plan = AgentExecutionPlan(
            intent=intent,
            task_goal=routed.request.message or AgentPlanner._default_goal(intent),
            steps=[
                AgentPlanStep(
                    step_id="step_1",
                    goal=AgentPlanner._default_goal(intent),
                    data_needs=data_needs,
                    output_requirements=["按事实数据生成老师可编辑草稿"],
                )
            ],
            data_needs=data_needs,
            response_requirements=["生成老师可编辑草稿", "不要编造没有工具支持的数据"],
            planner_reason="intent_router_adapter",
        )
        return PlannerResult(plan=plan, request=routed.request, warnings=routed.warnings)
