"""Tests for the MCP tool-calling Agent."""

from __future__ import annotations

import asyncio
from copy import deepcopy
from typing import Any

from app.agent.mcp_agent import MCPAgentChain
from app.agent.intent_router import IntentRouteResult, IntentRouter
from app.llm.chat_client import ChatResult, ChatToolCall
from app.mcp_gateway import (
    MCPToolDefinition,
    MCPToolError,
    MCPToolResult,
    MCPToolSource,
)
from app.schemas.agent import AgentChatParams, AgentChatRequest
from app.services.agent_service import AgentService


class FakeGateway:
    def __init__(self, responses: dict[str, MCPToolResult]) -> None:
        self.responses = responses
        self.calls: list[tuple[str, dict[str, Any], dict[str, Any]]] = []

    async def list_tools(self) -> list[MCPToolDefinition]:
        return [
            MCPToolDefinition(
                server="fake",
                name="user.get_student_profile",
                description="Get one student's profile and aggregate stats.",
                input_schema={
                    "type": "object",
                    "properties": {"student_id": {"type": "string"}},
                    "required": ["student_id"],
                },
            ),
            MCPToolDefinition(
                server="fake",
                name="learning.get_recent_homeworks",
                description="Get recent homeworks for one student.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "student_id": {"type": "string"},
                        "days": {"type": "integer"},
                    },
                    "required": ["student_id"],
                },
            ),
        ]

    async def call_tool(
        self,
        tool_name: str,
        arguments: dict[str, Any] | None = None,
        context: dict[str, Any] | None = None,
    ) -> MCPToolResult:
        self.calls.append((tool_name, arguments or {}, context or {}))
        return self.responses.get(
            tool_name,
            MCPToolResult(
                ok=False,
                data=None,
                evidence=[],
                source=MCPToolSource(server="fake", tool=tool_name),
                error=MCPToolError(code="missing_fake", message="No fake response"),
            ),
        )


class FakeChatClient:
    enabled = True

    def __init__(self, results: list[ChatResult]) -> None:
        self.results = results
        self.calls: list[dict[str, Any]] = []

    async def chat(
        self,
        *,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.2,
        max_tokens: int = 2000,
        timeout: float = 30.0,
    ) -> ChatResult:
        self.calls.append({"messages": deepcopy(messages), "tools": deepcopy(tools or [])})
        return self.results.pop(0)


class FakeGenerateClient:
    def __init__(self, results: list[ChatResult]) -> None:
        self.results = results
        self.calls: list[dict[str, Any]] = []

    async def generate(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.7,
        max_tokens: int = 2000,
        timeout: float = 30.0,
    ) -> ChatResult:
        self.calls.append(
            {
                "system_prompt": system_prompt,
                "user_prompt": user_prompt,
                "temperature": temperature,
                "max_tokens": max_tokens,
            }
        )
        return self.results.pop(0)


class FakeIntentRouter:
    def __init__(self, intent: str | None = None) -> None:
        self.intent = intent
        self.calls: list[AgentChatRequest] = []

    async def route(self, request: AgentChatRequest) -> IntentRouteResult:
        self.calls.append(request)
        if self.intent is None:
            return IntentRouteResult(request=request)
        params = request.params.model_copy(update={"intent": self.intent})
        return IntentRouteResult(request=request.model_copy(update={"params": params}))


def _ok(tool: str, data: Any, evidence: list[str] | None = None) -> MCPToolResult:
    return MCPToolResult(
        ok=True,
        data=data,
        evidence=evidence or [],
        source=MCPToolSource(server="fake", tool=tool),
    )


def _request(intent: str = "RECENT_SUMMARY") -> AgentChatRequest:
    return AgentChatRequest(
        teacher_id="teacher_1",
        student_id="stu_1",
        message="总结一下",
        params=AgentChatParams(intent=intent, time_range="7d"),
    )


def _agent(
    gateway: FakeGateway,
    chat_client: FakeChatClient,
) -> MCPAgentChain:
    return MCPAgentChain(
        gateway=gateway,  # type: ignore[arg-type]
        chat_client=chat_client,  # type: ignore[arg-type]
    )


def test_agent_exposes_mcp_tools_to_model() -> None:
    gateway = FakeGateway({})
    chat_client = FakeChatClient(
        [
            ChatResult(
                ok=True,
                content='{"title":"AI 生成标题","content":"AI 生成正文","sections":[]}',
                assistant_message={
                    "role": "assistant",
                    "content": '{"title":"AI 生成标题","content":"AI 生成正文","sections":[]}',
                },
            )
        ]
    )
    service = AgentService(_agent(gateway, chat_client), intent_router=FakeIntentRouter())  # type: ignore[arg-type]

    response = asyncio.run(service.generate(_request()))

    assert response.status == "success"
    assert response.content == "AI 生成正文"
    tool_names = [tool["function"]["name"] for tool in chat_client.calls[0]["tools"]]
    assert "user_get_student_profile" in tool_names
    assert "learning_get_recent_homeworks" in tool_names


def test_model_tool_call_is_executed_through_mcp_gateway() -> None:
    gateway = FakeGateway(
        {
            "user.get_student_profile": _ok(
                "user.get_student_profile",
                {"id": "stu_1", "name": "王同学", "status": "active"},
                ["学生 stu_1 基础档案"],
            ),
        }
    )
    chat_client = FakeChatClient(
        [
            ChatResult(
                ok=True,
                tool_calls=[
                    ChatToolCall(
                        id="call_1",
                        name="user_get_student_profile",
                        arguments={"student_id": "stu_1"},
                    )
                ],
                assistant_message={
                    "role": "assistant",
                    "tool_calls": [
                        {
                            "id": "call_1",
                            "type": "function",
                            "function": {
                                "name": "user_get_student_profile",
                                "arguments": '{"student_id":"stu_1"}',
                            },
                        }
                    ],
                },
            ),
            ChatResult(
                ok=True,
                content=(
                    '{"title":"AI 生成标题","content":"AI 生成正文",'
                    '"sections":[{"name":"AI 章节","items":["AI 要点"]}]}'
                ),
                assistant_message={
                    "role": "assistant",
                    "content": (
                        '{"title":"AI 生成标题","content":"AI 生成正文",'
                        '"sections":[{"name":"AI 章节","items":["AI 要点"]}]}'
                    ),
                },
            ),
        ]
    )
    service = AgentService(_agent(gateway, chat_client), intent_router=FakeIntentRouter())  # type: ignore[arg-type]

    response = asyncio.run(service.generate(_request()))

    assert response.status == "success"
    assert gateway.calls == [
        (
            "user.get_student_profile",
            {"student_id": "stu_1"},
            {
                "teacher_id": "teacher_1",
                "student_id": "stu_1",
                "scene": "student_detail",
                "request_context": {},
            },
        )
    ]
    assert response.evidence == ["学生 stu_1 基础档案"]
    assert chat_client.calls[1]["messages"][-1]["role"] == "tool"


def test_tool_failure_becomes_agent_warning() -> None:
    gateway = FakeGateway(
        {
            "learning.get_recent_homeworks": MCPToolResult(
                ok=False,
                data=None,
                evidence=[],
                source=MCPToolSource(server="fake", tool="learning.get_recent_homeworks"),
                error=MCPToolError(code="timeout", message="timeout"),
            )
        }
    )
    chat_client = FakeChatClient(
        [
            ChatResult(
                ok=True,
                tool_calls=[
                    ChatToolCall(
                        id="call_1",
                        name="learning_get_recent_homeworks",
                        arguments={"student_id": "stu_1", "days": 7},
                    )
                ],
                assistant_message={
                    "role": "assistant",
                    "tool_calls": [
                        {
                            "id": "call_1",
                            "type": "function",
                            "function": {
                                "name": "learning_get_recent_homeworks",
                                "arguments": '{"student_id":"stu_1","days":7}',
                            },
                        }
                    ],
                },
            ),
            ChatResult(
                ok=True,
                content='{"title":"AI 生成标题","content":"AI 生成正文","sections":[]}',
                assistant_message={
                    "role": "assistant",
                    "content": '{"title":"AI 生成标题","content":"AI 生成正文","sections":[]}',
                },
            ),
        ]
    )
    service = AgentService(_agent(gateway, chat_client), intent_router=FakeIntentRouter())  # type: ignore[arg-type]

    response = asyncio.run(service.generate(_request()))

    assert response.status == "success"
    assert response.warnings == ["learning.get_recent_homeworks 调用失败：timeout"]


def test_llm_failure_does_not_generate_local_template() -> None:
    gateway = FakeGateway({})
    chat_client = FakeChatClient(
        [ChatResult(ok=False, error="LLM 未配置：缺少 DASHSCOPE_API_KEY")]
    )
    service = AgentService(_agent(gateway, chat_client), intent_router=FakeIntentRouter())  # type: ignore[arg-type]

    response = asyncio.run(service.generate(_request()))

    assert response.status == "failed"
    assert response.content == "AI 暂时没有生成可用草稿，请稍后重试。"
    assert response.sections == []
    assert response.available_actions == ["regenerate"]
    assert "LLM 未配置" in response.warnings[0]


def test_llm_intent_router_updates_request_params() -> None:
    chat_client = FakeGenerateClient(
        [
            ChatResult(
                ok=True,
                content=(
                    '{"intent":"PARENT_REPLY","time_range":"30d","subject":"数学",'
                    '"lesson_id":null,"tone":"温和","length":"标准版",'
                    '"parent_question":"家长问孩子最近有没有进步","reason":"用户要求回复家长"}'
                ),
            )
        ]
    )
    router = IntentRouter(chat_client=chat_client)  # type: ignore[arg-type]
    request = _request()
    request.message = "家长问孩子最近有没有进步，我该怎么回复？"

    result = asyncio.run(router.route(request))

    assert result.request.params.intent == "PARENT_REPLY"
    assert result.request.params.parent_question == "家长问孩子最近有没有进步"
    assert result.request.params.time_range == "30d"
    assert chat_client.calls[0]["temperature"] == 0.0
