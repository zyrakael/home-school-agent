"""LangGraph orchestration for the home-school Agent."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Literal, TypedDict
from uuid import uuid4

from langgraph.graph import END, START, StateGraph

from app.agent.planner import AgentPlanner
from app.agent.prompt_builder import LLMResponsePayload, PromptBuilder
from app.agent.tool_router import ToolRouter
from app.llm.chat_client import ChatClient, get_chat_client
from app.mcp_gateway import MCPGateway, MCPToolDefinition, MCPToolResult, get_mcp_gateway
from app.memory import MemoryPack, MemoryService, SessionMemoryService, SessionState
from app.schemas.agent_contracts import AgentChatRequest, AgentExecutionPlan
from app.schemas.response import AgentChatResponse, AgentSection
from app.skills.loader import Skill
from app.skills.selector import SkillSelector

logger = logging.getLogger(__name__)


@dataclass
class AgentRunResult:
    """Final answer and tool trace produced by one agent run."""

    content: str | None
    evidence: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    tool_results: dict[str, MCPToolResult] = field(default_factory=dict)
    error: str | None = None


class AgentGraphState(TypedDict, total=False):
    """Shared state passed between LangGraph nodes."""

    original_request: AgentChatRequest
    session_state: SessionState
    resolved_request: AgentChatRequest
    plan: AgentExecutionPlan
    memory_pack: MemoryPack
    selected_skills: list[Skill]
    allowed_tools: set[str] | None
    tool_schemas: dict[str, dict[str, Any]]
    messages: list[dict[str, Any]]
    tools: list[dict[str, Any]]
    tool_name_map: dict[str, str]
    pending_tool_calls: list[dict[str, Any]]
    tool_results: dict[str, MCPToolResult]
    evidence: list[str]
    warnings: list[str]
    final_content: str | None
    response: AgentChatResponse
    error: str | None
    tool_rounds: int


class ToolCallingHelpers:
    """Shared MCP/OpenAI tool-call helpers used by graph nodes."""

    @staticmethod
    def validate_tool_arguments(
        tool_name: str,
        arguments: dict[str, Any],
        tool_schemas: dict[str, dict[str, Any]],
    ) -> tuple[dict[str, Any], str | None]:
        schema = tool_schemas.get(tool_name) or {}
        properties = schema.get("properties")
        required = schema.get("required")
        if not isinstance(properties, dict):
            properties = {}
        if not isinstance(required, list):
            required = []

        cleaned = {
            key: value
            for key, value in arguments.items()
            if key in properties and key != "context"
        }
        missing = [
            item
            for item in required
            if item != "context" and cleaned.get(item) in (None, "")
        ]
        if missing:
            return cleaned, f"{tool_name} 缺少必填参数：{', '.join(missing)}"
        return cleaned, None

    @classmethod
    def openai_tools(
        cls,
        definitions: list[MCPToolDefinition],
    ) -> tuple[list[dict[str, Any]], dict[str, str]]:
        tools: list[dict[str, Any]] = []
        tool_name_map: dict[str, str] = {}
        used_names: set[str] = set()
        for definition in definitions:
            openai_name = cls.safe_tool_name(definition.name, used_names)
            tool_name_map[openai_name] = definition.name
            tools.append(
                {
                    "type": "function",
                    "function": {
                        "name": openai_name,
                        "description": cls.tool_description(definition),
                        "parameters": cls.tool_parameters(definition.input_schema),
                    },
                }
            )
        return tools, tool_name_map

    @staticmethod
    def safe_tool_name(tool_name: str, used_names: set[str]) -> str:
        base = re.sub(r"[^a-zA-Z0-9_-]", "_", tool_name).strip("_") or "mcp_tool"
        candidate = base[:64]
        index = 2
        while candidate in used_names:
            suffix = f"_{index}"
            candidate = f"{base[:64 - len(suffix)]}{suffix}"
            index += 1
        used_names.add(candidate)
        return candidate

    @staticmethod
    def tool_description(definition: MCPToolDefinition) -> str:
        description = definition.description.strip()
        if description:
            return f"{description}\nMCP tool: {definition.name}"
        return f"MCP tool: {definition.name}"

    @staticmethod
    def tool_parameters(schema: dict[str, Any]) -> dict[str, Any]:
        parameters = json.loads(json.dumps(schema or {"type": "object"}))
        parameters.setdefault("type", "object")
        properties = parameters.get("properties")
        if isinstance(properties, dict):
            properties.pop("context", None)
        required = parameters.get("required")
        if isinstance(required, list):
            parameters["required"] = [item for item in required if item != "context"]
        return parameters


class AgentGraphRunner:
    """Run the full Agent flow as a LangGraph state machine."""

    def __init__(
        self,
        *,
        gateway: MCPGateway | None = None,
        chat_client: ChatClient | None = None,
        planner: AgentPlanner | None = None,
        skill_selector: SkillSelector | None = None,
        tool_router: ToolRouter | None = None,
        memory_service: MemoryService | None = None,
        session_memory_service: SessionMemoryService | None = None,
        max_tool_rounds: int = 4,
    ) -> None:
        self.gateway = gateway or get_mcp_gateway()
        self.chat_client = chat_client or get_chat_client()
        self.planner = planner or AgentPlanner()
        self.skill_selector = skill_selector or SkillSelector()
        self.tool_router = tool_router or ToolRouter()
        self.memory_service = memory_service or MemoryService()
        self.session_memory_service = session_memory_service or SessionMemoryService()
        self.max_tool_rounds = max_tool_rounds
        self._graph = self._build_graph()

    async def run(self, request: AgentChatRequest) -> AgentChatResponse:
        """Generate a response through the full LangGraph workflow."""

        self._log_node(
            "开始",
            "收到 Agent 请求",
            conversation_id=request.conversation_id,
            teacher_id=request.teacher_id,
            student_id=request.student_id,
            intent=request.params.intent,
            scene=request.scene,
            message_preview=self._preview(request.message),
        )
        state: AgentGraphState = {
            "original_request": request,
            "warnings": [],
            "tool_results": {},
            "evidence": [],
            "tool_rounds": 0,
        }
        final_state = await self._graph.ainvoke(state)
        response = final_state["response"]
        self._log_node(
            "结束",
            "Agent 请求完成",
            request_id=response.request_id,
            status=response.status,
            intent=response.intent,
            evidence_count=len(response.evidence),
            warning_count=len(response.warnings),
        )
        return response

    def _build_graph(self):
        graph = StateGraph(AgentGraphState)
        graph.add_node("recall_session", self._recall_session)
        graph.add_node("resolve_request", self._resolve_request)
        graph.add_node("plan_request", self._plan_request)
        graph.add_node("recall_long_term_memory", self._recall_long_term_memory)
        graph.add_node("select_skills", self._select_skills)
        graph.add_node("route_tools", self._route_tools)
        graph.add_node("prepare_tool_calling", self._prepare_tool_calling)
        graph.add_node("call_model", self._call_model)
        graph.add_node("call_tools", self._call_tools)
        graph.add_node("parse_response", self._parse_response)
        graph.add_node("build_error_response", self._build_error_response)
        graph.add_node("commit_session_memory", self._commit_session_memory)
        graph.add_node("commit_long_term_memory", self._commit_long_term_memory)

        graph.add_edge(START, "recall_session")
        graph.add_edge("recall_session", "resolve_request")
        graph.add_edge("resolve_request", "plan_request")
        graph.add_edge("plan_request", "recall_long_term_memory")
        graph.add_edge("recall_long_term_memory", "select_skills")
        graph.add_edge("select_skills", "route_tools")
        graph.add_edge("route_tools", "prepare_tool_calling")
        graph.add_edge("prepare_tool_calling", "call_model")
        graph.add_conditional_edges(
            "call_model",
            self._route_after_model,
            {
                "tools": "call_tools",
                "parse": "parse_response",
                "error": "build_error_response",
            },
        )
        graph.add_edge("call_tools", "call_model")
        graph.add_edge("parse_response", "commit_session_memory")
        graph.add_edge("build_error_response", "commit_session_memory")
        graph.add_conditional_edges(
            "commit_session_memory",
            self._route_after_session_commit,
            {"long_term": "commit_long_term_memory", "end": END},
        )
        graph.add_edge("commit_long_term_memory", END)
        return graph.compile()

    async def _recall_session(self, state: AgentGraphState) -> AgentGraphState:
        request = state["original_request"]
        self._log_node("recall_session", "召回 Session Memory", conversation_id=request.conversation_id)
        session_state = await self.session_memory_service.recall(request)
        self._log_node(
            "recall_session",
            "Session Memory 召回完成",
            has_content=session_state.has_content(),
            last_intent=session_state.last_intent,
            student_id=session_state.student_id,
            subject=session_state.subject,
            key_data_count=len(session_state.key_data_summary),
        )
        return {"session_state": session_state}

    async def _resolve_request(self, state: AgentGraphState) -> AgentGraphState:
        before = state["original_request"]
        self._log_node(
            "resolve_request",
            "根据 Session Memory 补全省略上下文",
            original_student_id=before.student_id,
            original_intent=before.params.intent,
        )
        resolved = self.session_memory_service.resolve_request(
            before,
            state.get("session_state", SessionState()),
        )
        self._log_node(
            "resolve_request",
            "请求补全完成",
            resolved_student_id=resolved.student_id,
            resolved_intent=resolved.params.intent,
            subject=resolved.params.subject,
        )
        return {
            "resolved_request": resolved
        }

    async def _plan_request(self, state: AgentGraphState) -> AgentGraphState:
        self._log_node(
            "plan_request",
            "开始生成执行计划",
            message_preview=self._preview(state["resolved_request"].message),
        )
        planned = await self.planner.plan(state["resolved_request"])
        self._log_node(
            "plan_request",
            "执行计划生成完成",
            intent=planned.plan.intent,
            data_needs=planned.plan.data_needs,
            step_count=len(planned.plan.steps),
            warning_count=len(planned.warnings),
        )
        return {
            "resolved_request": planned.request,
            "plan": planned.plan,
            "warnings": [*state.get("warnings", []), *planned.warnings],
        }

    async def _recall_long_term_memory(self, state: AgentGraphState) -> AgentGraphState:
        self._log_node(
            "recall_long_term_memory",
            "召回长期工作上下文",
            intent=state["plan"].intent,
            student_id=state["resolved_request"].student_id,
            teacher_id=state["resolved_request"].teacher_id,
        )
        memory_pack = await self.memory_service.recall(
            state["resolved_request"],
            state["plan"],
        )
        self._log_node(
            "recall_long_term_memory",
            "长期工作上下文召回完成",
            has_content=memory_pack.has_content(),
            student_pattern_count=len(memory_pack.student_learning_patterns),
            teacher_style_count=len(memory_pack.teacher_reply_styles),
            policy_count=len(memory_pack.internal_reply_policies),
            ephemeral_count=len(memory_pack.ephemeral_turn_context),
        )
        return {
            "memory_pack": memory_pack
        }

    async def _select_skills(self, state: AgentGraphState) -> AgentGraphState:
        self._log_node("select_skills", "选择本地 Skills", intent=state["plan"].intent)
        selected = self.skill_selector.select(state["plan"].intent)
        self._log_node(
            "select_skills",
            "Skills 选择完成",
            skills=[skill.name for skill in selected.skills],
            warning_count=len(selected.warnings),
        )
        return {
            "selected_skills": selected.skills,
            "warnings": [*state.get("warnings", []), *selected.warnings],
        }

    async def _route_tools(self, state: AgentGraphState) -> AgentGraphState:
        self._log_node("route_tools", "根据 data_needs 路由 MCP 工具", data_needs=state["plan"].data_needs)
        routed = self.tool_router.route(state["plan"])
        if not state["resolved_request"].student_id:
            routed.allowed_tools.add("user.list_students")
        self._log_node(
            "route_tools",
            "MCP 工具白名单生成完成",
            allowed_tools=sorted(routed.allowed_tools),
            warning_count=len(routed.warnings),
        )
        return {
            "allowed_tools": routed.allowed_tools,
            "warnings": [*state.get("warnings", []), *routed.warnings],
        }

    async def _prepare_tool_calling(self, state: AgentGraphState) -> AgentGraphState:
        request = state["resolved_request"]
        allowed_tools = state.get("allowed_tools")
        self._log_node(
            "prepare_tool_calling",
            "开始发现 MCP 工具并构造模型消息",
            allowed_tools=sorted(allowed_tools or []),
        )
        definitions = await self.gateway.list_tools()
        if allowed_tools is not None:
            definitions = [definition for definition in definitions if definition.name in allowed_tools]
        tools, tool_name_map = ToolCallingHelpers.openai_tools(definitions)
        system, user = PromptBuilder.build_tool_calling_prompt(
            request,
            execution_plan=state.get("plan"),
            selected_skills=state.get("selected_skills", []),
            allowed_tools=allowed_tools,
            memory_context=state.get("memory_pack"),
            session_context=state.get("session_state"),
        )
        warnings = list(state.get("warnings", []))
        discovery_errors = getattr(self.gateway, "last_discovery_errors", [])
        warnings.extend(discovery_errors)
        if allowed_tools is not None and not definitions:
            warnings.append("没有可用数据工具，已按数据不足场景生成草稿。")
        self._log_node(
            "prepare_tool_calling",
            "模型消息和工具 schema 准备完成",
            discovered_tool_count=len(definitions),
            exposed_tools=[tool["function"]["name"] for tool in tools],
            warning_count=len(warnings),
            discovery_errors=discovery_errors,
        )
        return {
            "tools": tools,
            "tool_name_map": tool_name_map,
            "tool_schemas": {definition.name: definition.input_schema for definition in definitions},
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "warnings": warnings,
        }

    async def _call_model(self, state: AgentGraphState) -> AgentGraphState:
        self._log_node(
            "call_model",
            "调用 LLM",
            message_count=len(state["messages"]),
            tool_count=len(state.get("tools", [])),
            tool_rounds=state.get("tool_rounds", 0),
        )
        result = await self.chat_client.chat(
            messages=state["messages"],
            tools=state.get("tools", []),
        )
        if not result.ok:
            self._log_node("call_model", "LLM 调用失败", error=result.error)
            return {"error": result.error or "LLM 调用失败"}

        messages = list(state["messages"])
        if result.assistant_message:
            messages.append(result.assistant_message)

        if result.tool_calls:
            self._log_node(
                "call_model",
                "LLM 请求调用工具",
                tool_calls=[call.name for call in result.tool_calls],
                finish_reason=result.finish_reason,
            )
            if state.get("tool_rounds", 0) >= self.max_tool_rounds:
                self._log_node(
                    "call_model",
                    "工具调用轮次超过上限",
                    max_tool_rounds=self.max_tool_rounds,
                )
                return {
                    "messages": messages,
                    "pending_tool_calls": [],
                    "error": "工具调用轮次过多，已停止生成。",
                }
            return {
                "messages": messages,
                "pending_tool_calls": [
                    {"id": call.id, "name": call.name, "arguments": call.arguments}
                    for call in result.tool_calls
                ],
                "final_content": None,
            }

        self._log_node(
            "call_model",
            "LLM 返回最终内容",
            finish_reason=result.finish_reason,
            content_preview=self._preview(result.content),
        )
        return {
            "messages": messages,
            "final_content": result.content,
            "pending_tool_calls": [],
        }

    async def _call_tools(self, state: AgentGraphState) -> AgentGraphState:
        request = state["resolved_request"]
        self._log_node(
            "call_tools",
            "开始执行 MCP 工具调用",
            pending_tool_count=len(state.get("pending_tool_calls", [])),
        )
        context = {
            "teacher_id": request.teacher_id,
            "student_id": request.student_id,
            "scene": request.scene,
            "request_context": request.context,
        }
        warnings = list(state.get("warnings", []))
        messages = list(state["messages"])
        tool_results = dict(state.get("tool_results", {}))
        evidence = list(state.get("evidence", []))

        for call in state.get("pending_tool_calls", []):
            openai_name = call["name"]
            mcp_name = state.get("tool_name_map", {}).get(openai_name, openai_name)
            allowed_tools = state.get("allowed_tools")
            self._log_node(
                "call_tools",
                "处理单个工具调用",
                openai_tool=openai_name,
                mcp_tool=mcp_name,
                arguments=call.get("arguments") or {},
            )
            if allowed_tools is not None and mcp_name not in allowed_tools:
                warnings.append(f"{mcp_name} 未在工具白名单中，已拒绝调用。")
                self._log_node("call_tools", "工具不在白名单，拒绝调用", mcp_tool=mcp_name)
                messages.append(self._tool_message(call["id"], {"ok": False, "error": "tool_not_allowed"}))
                continue

            arguments, validation_error = ToolCallingHelpers.validate_tool_arguments(
                mcp_name,
                call.get("arguments") or {},
                state.get("tool_schemas", {}),
            )
            if validation_error:
                warnings.append(validation_error)
                self._log_node("call_tools", "工具参数校验失败", mcp_tool=mcp_name, error=validation_error)
                messages.append(
                    self._tool_message(
                        call["id"],
                        {"ok": False, "error": "invalid_tool_arguments", "message": validation_error},
                    )
                )
                continue

            result = await self.gateway.call_tool(mcp_name, arguments, context)
            tool_results[mcp_name] = result
            if result.ok:
                evidence = self._dedupe([*evidence, *result.evidence])
                self._log_node(
                    "call_tools",
                    "MCP 工具调用成功",
                    mcp_tool=mcp_name,
                    evidence_count=len(result.evidence),
                )
            else:
                message = result.error.message if result.error else "unknown error"
                warnings.append(f"{mcp_name} 调用失败：{message}")
                self._log_node("call_tools", "MCP 工具调用失败", mcp_tool=mcp_name, error=message)
            messages.append({"role": "tool", "tool_call_id": call["id"], "content": result.model_dump_json()})

        self._log_node(
            "call_tools",
            "本轮 MCP 工具调用完成",
            total_tool_results=len(tool_results),
            evidence_count=len(evidence),
            warning_count=len(warnings),
        )
        return {
            "messages": messages,
            "warnings": warnings,
            "tool_results": tool_results,
            "evidence": evidence,
            "pending_tool_calls": [],
            "tool_rounds": state.get("tool_rounds", 0) + 1,
        }

    async def _parse_response(self, state: AgentGraphState) -> AgentGraphState:
        self._log_node("parse_response", "解析 LLM 最终 JSON 输出")
        parsed = self._parse_agent_output(self._run_result(state))
        if parsed is None:
            self._log_node("parse_response", "LLM 输出解析失败")
            return {
                "error": "LLM 输出解析失败",
                "response": self._error_response(
                    state,
                    reason="LLM 输出解析失败",
                ),
            }
        self._log_node(
            "parse_response",
            "LLM 输出解析成功",
            title=parsed.title,
            section_count=len(parsed.sections),
        )
        return {
            "response": self._base_response(
                intent=state["plan"].intent,
                title=parsed.title,
                content=parsed.content,
                sections=parsed.sections,
                evidence=state.get("evidence", []),
                warnings=state.get("warnings", []),
            )
        }

    async def _build_error_response(self, state: AgentGraphState) -> AgentGraphState:
        self._log_node("build_error_response", "构造失败响应", error=state.get("error"))
        return {
            "response": self._error_response(
                state,
                reason=state.get("error") or "LLM 输出解析失败",
            )
        }

    async def _commit_session_memory(self, state: AgentGraphState) -> AgentGraphState:
        self._log_node(
            "commit_session_memory",
            "写入 Session Memory",
            conversation_id=state["resolved_request"].conversation_id,
            status=state["response"].status,
        )
        await self.session_memory_service.commit(
            state["resolved_request"],
            state["plan"],
            self._run_result(state),
            state["response"],
        )
        self._log_node("commit_session_memory", "Session Memory 写入完成")
        return {}

    async def _commit_long_term_memory(self, state: AgentGraphState) -> AgentGraphState:
        self._log_node(
            "commit_long_term_memory",
            "写入长期工作上下文",
            status=state["response"].status,
            intent=state["plan"].intent,
        )
        await self.memory_service.commit(
            state["resolved_request"],
            state["plan"],
            self._run_result(state),
            state["response"],
        )
        self._log_node("commit_long_term_memory", "长期工作上下文写入完成")
        return {}

    @staticmethod
    def _route_after_model(state: AgentGraphState) -> Literal["tools", "parse", "error"]:
        if state.get("error"):
            return "error"
        if state.get("pending_tool_calls"):
            return "tools"
        return "parse"

    @staticmethod
    def _route_after_session_commit(state: AgentGraphState) -> Literal["long_term", "end"]:
        response = state.get("response")
        if response is not None and response.status == "success":
            return "long_term"
        return "end"

    @staticmethod
    def _run_result(state: AgentGraphState) -> AgentRunResult:
        return AgentRunResult(
            content=state.get("final_content"),
            evidence=state.get("evidence", []),
            warnings=state.get("warnings", []),
            tool_results=state.get("tool_results", {}),
            error=state.get("error"),
        )

    @staticmethod
    def _parse_agent_output(result: AgentRunResult) -> LLMResponsePayload | None:
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

    def _error_response(self, state: AgentGraphState, *, reason: str) -> AgentChatResponse:
        request = state.get("resolved_request") or state["original_request"]
        intent = state["plan"].intent if state.get("plan") else request.params.intent
        return AgentChatResponse(
            request_id=f"req_{uuid4().hex[:12]}",
            intent=intent,
            status="failed",
            title=self._default_title(request),
            content="AI 暂时没有生成可用草稿，请稍后重试。",
            sections=[],
            evidence=state.get("evidence", []),
            warnings=[*state.get("warnings", []), reason],
            available_actions=["regenerate"],
        )

    @staticmethod
    def _default_title(request: AgentChatRequest) -> str:
        intent = request.params.intent
        if intent == "RECENT_SUMMARY":
            days = AgentGraphRunner._parse_days(request.params.time_range, default=7)
            return f"近{days}天学习情况总结"
        if intent == "HOMEWORK_DIAGNOSIS":
            return "作业与错题诊断"
        if intent == "LESSON_FEEDBACK":
            return "课后反馈草稿"
        if intent == "PARENT_REPLY":
            return "家长问题回复草稿"
        return "AI 草稿"

    @staticmethod
    def _parse_days(value: str | None, default: int) -> int:
        if not value:
            return default
        try:
            return int(value.rstrip("d"))
        except ValueError:
            return default

    @staticmethod
    def _tool_message(tool_call_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        return {
            "role": "tool",
            "tool_call_id": tool_call_id,
            "content": json.dumps(payload, ensure_ascii=False),
        }

    @staticmethod
    def _log_node(node: str, message: str, **fields: Any) -> None:
        safe_fields = {
            key: value
            for key, value in fields.items()
            if value not in (None, "", [], {})
        }
        if safe_fields:
            logger.info("[AgentGraph][%s] %s | %s", node, message, safe_fields)
        else:
            logger.info("[AgentGraph][%s] %s", node, message)

    @staticmethod
    def _preview(value: str | None, limit: int = 120) -> str:
        if not value:
            return ""
        text = value.replace("\n", " ").strip()
        if len(text) <= limit:
            return text
        return f"{text[: limit - 3]}..."

    @staticmethod
    def _dedupe(items: list[str]) -> list[str]:
        deduped: list[str] = []
        for item in items:
            if item and item not in deduped:
                deduped.append(item)
        return deduped
