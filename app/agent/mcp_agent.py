"""LangChain-style MCP tool-calling agent."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, TypedDict

from app.agent.prompt_builder import PromptBuilder
from app.llm.chat_client import ChatClient, get_chat_client
from app.mcp_gateway import MCPGateway, MCPToolDefinition, MCPToolResult, get_mcp_gateway
from app.schemas.agent import AgentChatRequest


@dataclass
class AgentRunResult:
    """Final answer and tool trace produced by one agent run."""

    content: str | None
    evidence: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    tool_results: dict[str, MCPToolResult] = field(default_factory=dict)
    error: str | None = None


class AgentChainState(TypedDict, total=False):
    request: AgentChatRequest
    messages: list[dict[str, Any]]
    tools: list[dict[str, Any]]
    tool_name_map: dict[str, str]
    evidence: list[str]
    warnings: list[str]
    tool_results: dict[str, MCPToolResult]
    final_content: str | None
    error: str | None


class MCPAgentChain:
    """Let the model choose MCP tools, execute them, then ask for final JSON."""

    def __init__(
        self,
        *,
        gateway: MCPGateway | None = None,
        chat_client: ChatClient | None = None,
        max_tool_rounds: int = 4,
    ) -> None:
        self.gateway = gateway or get_mcp_gateway()
        self.chat_client = chat_client or get_chat_client()
        self.max_tool_rounds = max_tool_rounds
        self._chain: Any | None = None

    async def run(self, request: AgentChatRequest) -> AgentRunResult:
        """Run the tool-calling agent."""

        state = await self._initial_state(request)
        chain = self._build_chain()
        if chain is not None:
            state = await chain.ainvoke(state)
        else:
            state = await self._run_tool_loop(state)

        return AgentRunResult(
            content=state.get("final_content"),
            evidence=state.get("evidence", []),
            warnings=state.get("warnings", []),
            tool_results=state.get("tool_results", {}),
            error=state.get("error"),
        )

    async def _initial_state(self, request: AgentChatRequest) -> AgentChainState:
        definitions = await self.gateway.list_tools()
        tools, tool_name_map = self._openai_tools(definitions)
        system, user = PromptBuilder.build_tool_calling_prompt(request)
        return {
            "request": request,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "tools": tools,
            "tool_name_map": tool_name_map,
            "evidence": [],
            "warnings": [],
            "tool_results": {},
            "final_content": None,
            "error": None,
        }

    def _build_chain(self) -> Any | None:
        if self._chain is not None:
            return self._chain
        try:
            from langchain_core.runnables import RunnableLambda
        except ImportError:
            return None

        self._chain = RunnableLambda(self._run_tool_loop)
        return self._chain

    async def _run_tool_loop(self, state: AgentChainState) -> AgentChainState:
        for _ in range(self.max_tool_rounds + 1):
            state = await self._call_model(state)
            if self._next_step(state) == "end":
                return state
            state = await self._call_tools(state)
        state["error"] = "工具调用轮次过多，已停止生成。"
        return state

    async def _call_model(self, state: AgentChainState) -> AgentChainState:
        result = await self.chat_client.chat(
            messages=state["messages"],
            tools=state.get("tools", []),
        )
        if not result.ok:
            state["error"] = result.error or "LLM 调用失败"
            return state

        if result.assistant_message:
            state["messages"].append(result.assistant_message)

        if result.tool_calls:
            state["_pending_tool_calls"] = [
                {"id": call.id, "name": call.name, "arguments": call.arguments}
                for call in result.tool_calls
            ]
            return state

        state["final_content"] = result.content
        state.pop("_pending_tool_calls", None)
        return state

    async def _call_tools(self, state: AgentChainState) -> AgentChainState:
        request = state["request"]
        context = {
            "teacher_id": request.teacher_id,
            "student_id": request.student_id,
            "scene": request.scene,
            "request_context": request.context,
        }

        for call in state.get("_pending_tool_calls", []):
            openai_name = call["name"]
            mcp_name = state.get("tool_name_map", {}).get(openai_name, openai_name)
            result = await self.gateway.call_tool(
                mcp_name,
                call.get("arguments") or {},
                context,
            )
            state["tool_results"][mcp_name] = result
            if result.ok:
                state["evidence"].extend(result.evidence)
            else:
                message = result.error.message if result.error else "unknown error"
                state["warnings"].append(f"{mcp_name} 调用失败：{message}")

            state["messages"].append(
                {
                    "role": "tool",
                    "tool_call_id": call["id"],
                    "content": result.model_dump_json(),
                }
            )

        state.pop("_pending_tool_calls", None)
        return state

    @staticmethod
    def _next_step(state: AgentChainState) -> str:
        if state.get("error") or state.get("final_content"):
            return "end"
        if state.get("_pending_tool_calls"):
            return "tools"
        return "end"

    @classmethod
    def _openai_tools(
        cls,
        definitions: list[MCPToolDefinition],
    ) -> tuple[list[dict[str, Any]], dict[str, str]]:
        tools: list[dict[str, Any]] = []
        tool_name_map: dict[str, str] = {}
        used_names: set[str] = set()
        for definition in definitions:
            openai_name = cls._safe_tool_name(definition.name, used_names)
            tool_name_map[openai_name] = definition.name
            tools.append(
                {
                    "type": "function",
                    "function": {
                        "name": openai_name,
                        "description": cls._tool_description(definition),
                        "parameters": cls._tool_parameters(definition.input_schema),
                    },
                }
            )
        return tools, tool_name_map

    @staticmethod
    def _safe_tool_name(tool_name: str, used_names: set[str]) -> str:
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
    def _tool_description(definition: MCPToolDefinition) -> str:
        description = definition.description.strip()
        if description:
            return f"{description}\nMCP tool: {definition.name}"
        return f"MCP tool: {definition.name}"

    @staticmethod
    def _tool_parameters(schema: dict[str, Any]) -> dict[str, Any]:
        parameters = json.loads(json.dumps(schema or {"type": "object"}))
        parameters.setdefault("type", "object")
        properties = parameters.get("properties")
        if isinstance(properties, dict):
            properties.pop("context", None)
        required = parameters.get("required")
        if isinstance(required, list):
            parameters["required"] = [item for item in required if item != "context"]
        return parameters
