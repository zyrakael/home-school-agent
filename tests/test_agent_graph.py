"""Tests for the full LangGraph Agent workflow."""

from __future__ import annotations

import asyncio
from copy import deepcopy
from typing import Any

from app.agent.agent_graph import AgentGraphRunner
from app.llm.chat_client import ChatResult, ChatToolCall
from app.mcp_gateway import MCPToolDefinition, MCPToolError, MCPToolResult, MCPToolSource
from app.schemas.agent_contracts import AgentChatParams, AgentChatRequest
from app.services.agent_service import AgentService
from app.memory import InMemoryMemoryStore, MemoryService


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
                name="user.list_students",
                description="List students available to the teacher.",
                input_schema={
                    "type": "object",
                    "properties": {},
                    "required": [],
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


def _ok(tool: str, data: Any, evidence: list[str] | None = None) -> MCPToolResult:
    return MCPToolResult(
        ok=True,
        data=data,
        evidence=evidence or [],
        source=MCPToolSource(server="fake", tool=tool),
    )


def _request(intent: str = "RECENT_SUMMARY") -> AgentChatRequest:
    return AgentChatRequest(
        conversation_id="conv_graph",
        teacher_id="teacher_1",
        student_id="stu_1",
        message="总结一下",
        params=AgentChatParams(intent=intent, time_range="7d", subject="数学"),
    )


def _request_without_student(intent: str = "RECENT_SUMMARY") -> AgentChatRequest:
    return _request(intent).model_copy(update={"student_id": "", "message": "总结一下这个学生"})


def test_langgraph_workflow_generates_without_tool_calls() -> None:
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
    runner = AgentGraphRunner(
        gateway=gateway,  # type: ignore[arg-type]
        chat_client=chat_client,  # type: ignore[arg-type]
        planner=FallbackPlanner(),  # type: ignore[arg-type]
    )

    response = asyncio.run(runner.run(_request()))

    assert response.status == "success"
    assert response.content == "AI 生成正文"
    assert chat_client.calls[0]["tools"]


def test_langgraph_workflow_loops_through_mcp_tools() -> None:
    gateway = FakeGateway(
        {
            "user.get_student_profile": _ok(
                "user.get_student_profile",
                {"id": "stu_1", "name": "王同学"},
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
                content='{"title":"AI 生成标题","content":"AI 生成正文","sections":[]}',
                assistant_message={
                    "role": "assistant",
                    "content": '{"title":"AI 生成标题","content":"AI 生成正文","sections":[]}',
                },
            ),
        ]
    )
    service = AgentService(
        gateway=gateway,  # type: ignore[arg-type]
        chat_client=chat_client,  # type: ignore[arg-type]
        planner=FallbackPlanner(),  # type: ignore[arg-type]
    )

    response = asyncio.run(service.generate(_request()))

    assert response.status == "success"
    assert response.evidence == ["学生 stu_1 基础档案"]
    assert any(call[0] == "user.get_student_profile" for call in gateway.calls)


def test_langgraph_workflow_resolves_missing_student_from_mcp_list() -> None:
    gateway = FakeGateway(
        {
            "user.list_students": _ok(
                "user.list_students",
                {"students": [{"student_id": "stu_1", "name": "王同学"}]},
                ["老师可见学生列表"],
            ),
            "user.get_student_profile": _ok(
                "user.get_student_profile",
                {"id": "stu_1", "name": "王同学"},
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
                        id="call_list",
                        name="user_list_students",
                        arguments={},
                    )
                ],
                assistant_message={
                    "role": "assistant",
                    "tool_calls": [
                        {
                            "id": "call_list",
                            "type": "function",
                            "function": {
                                "name": "user_list_students",
                                "arguments": "{}",
                            },
                        }
                    ],
                },
            ),
            ChatResult(
                ok=True,
                tool_calls=[
                    ChatToolCall(
                        id="call_profile",
                        name="user_get_student_profile",
                        arguments={"student_id": "stu_1"},
                    )
                ],
                assistant_message={
                    "role": "assistant",
                    "tool_calls": [
                        {
                            "id": "call_profile",
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
                content='{"title":"AI 生成标题","content":"AI 生成正文","sections":[]}',
                assistant_message={
                    "role": "assistant",
                    "content": '{"title":"AI 生成标题","content":"AI 生成正文","sections":[]}',
                },
            ),
        ]
    )
    runner = AgentGraphRunner(
        gateway=gateway,  # type: ignore[arg-type]
        chat_client=chat_client,  # type: ignore[arg-type]
        planner=FallbackPlanner(),  # type: ignore[arg-type]
    )

    response = asyncio.run(runner.run(_request_without_student()))

    assert response.status == "success"
    assert [call[0] for call in gateway.calls][:2] == ["user.list_students", "user.get_student_profile"]
    assert gateway.calls[1][1] == {"student_id": "stu_1"}
    assert response.evidence == ["老师可见学生列表", "学生 stu_1 基础档案"]


def test_langgraph_workflow_asks_for_student_when_mcp_list_is_ambiguous() -> None:
    gateway = FakeGateway(
        {
            "user.list_students": _ok(
                "user.list_students",
                {
                    "students": [
                        {"student_id": "stu_1", "name": "王同学"},
                        {"student_id": "stu_2", "name": "李同学"},
                    ]
                },
                ["老师可见学生列表"],
            ),
        }
    )
    chat_client = FakeChatClient(
        [
            ChatResult(
                ok=True,
                tool_calls=[
                    ChatToolCall(
                        id="call_list",
                        name="user_list_students",
                        arguments={},
                    )
                ],
                assistant_message={
                    "role": "assistant",
                    "tool_calls": [
                        {
                            "id": "call_list",
                            "type": "function",
                            "function": {
                                "name": "user_list_students",
                                "arguments": "{}",
                            },
                        }
                    ],
                },
            ),
            ChatResult(
                ok=True,
                content='{"title":"需要补充学生信息","content":"请补充学生姓名或学生 ID。","sections":[]}',
                assistant_message={
                    "role": "assistant",
                    "content": '{"title":"需要补充学生信息","content":"请补充学生姓名或学生 ID。","sections":[]}',
                },
            ),
        ]
    )
    runner = AgentGraphRunner(
        gateway=gateway,  # type: ignore[arg-type]
        chat_client=chat_client,  # type: ignore[arg-type]
        planner=FallbackPlanner(),  # type: ignore[arg-type]
    )

    response = asyncio.run(runner.run(_request_without_student()))

    assert response.status == "success"
    assert [call[0] for call in gateway.calls] == ["user.list_students"]
    assert response.content == "请补充学生姓名或学生 ID。"


def test_langgraph_workflow_commits_long_term_memory_after_success() -> None:
    store = InMemoryMemoryStore()
    chat_client = FakeChatClient(
        [
            ChatResult(
                ok=True,
                content=(
                    '{"title":"总结","content":"正文",'
                    '"sections":[{"name":"学习表现","items":["应用题审题需要继续关注。"]}]}'
                ),
                assistant_message={
                    "role": "assistant",
                    "content": (
                        '{"title":"总结","content":"正文",'
                        '"sections":[{"name":"学习表现","items":["应用题审题需要继续关注。"]}]}'
                    ),
                },
            )
        ]
    )
    runner = AgentGraphRunner(
        gateway=FakeGateway({}),  # type: ignore[arg-type]
        chat_client=chat_client,  # type: ignore[arg-type]
        planner=FallbackPlanner(),  # type: ignore[arg-type]
        memory_service=MemoryService(store),
    )

    response = asyncio.run(runner.run(_request()))

    assert response.status == "success"
    assert store.list(owner_key="student:stu_1")[0].content == "学生稳定学习特征：应用题审题需要继续关注。"


def test_langgraph_workflow_stops_after_max_tool_rounds() -> None:
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
                assistant_message={"role": "assistant", "tool_calls": []},
            )
        ]
    )
    runner = AgentGraphRunner(
        gateway=FakeGateway({}),  # type: ignore[arg-type]
        chat_client=chat_client,  # type: ignore[arg-type]
        planner=FallbackPlanner(),  # type: ignore[arg-type]
        max_tool_rounds=0,
    )

    response = asyncio.run(runner.run(_request()))

    assert response.status == "failed"
    assert "工具调用轮次过多" in response.warnings[-1]


def test_langgraph_workflow_rejects_non_allowlisted_tool_call() -> None:
    gateway = FakeGateway({})
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
                assistant_message={"role": "assistant", "tool_calls": []},
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
    runner = AgentGraphRunner(
        gateway=gateway,  # type: ignore[arg-type]
        chat_client=chat_client,  # type: ignore[arg-type]
        planner=SingleNeedPlanner("recent_homeworks"),  # type: ignore[arg-type]
    )

    response = asyncio.run(runner.run(_request()))

    assert gateway.calls == []
    assert "未在工具白名单中" in response.warnings[0]


def test_langgraph_workflow_skips_tool_call_with_missing_required_argument() -> None:
    gateway = FakeGateway({})
    chat_client = FakeChatClient(
        [
            ChatResult(
                ok=True,
                tool_calls=[
                    ChatToolCall(
                        id="call_1",
                        name="learning_get_recent_homeworks",
                        arguments={"days": 7},
                    )
                ],
                assistant_message={"role": "assistant", "tool_calls": []},
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
    runner = AgentGraphRunner(
        gateway=gateway,  # type: ignore[arg-type]
        chat_client=chat_client,  # type: ignore[arg-type]
        planner=SingleNeedPlanner("recent_homeworks"),  # type: ignore[arg-type]
    )

    response = asyncio.run(runner.run(_request()))

    assert gateway.calls == []
    assert "缺少必填参数：student_id" in response.warnings[0]


def test_langgraph_workflow_reports_tool_failure() -> None:
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
                assistant_message={"role": "assistant", "tool_calls": []},
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
    runner = AgentGraphRunner(
        gateway=gateway,  # type: ignore[arg-type]
        chat_client=chat_client,  # type: ignore[arg-type]
        planner=SingleNeedPlanner("recent_homeworks"),  # type: ignore[arg-type]
    )

    response = asyncio.run(runner.run(_request()))

    assert response.status == "success"
    assert response.warnings == ["learning.get_recent_homeworks 调用失败：timeout"]


def test_langgraph_workflow_returns_failed_response_on_llm_error() -> None:
    runner = AgentGraphRunner(
        gateway=FakeGateway({}),  # type: ignore[arg-type]
        chat_client=FakeChatClient([ChatResult(ok=False, error="LLM 未配置")]),  # type: ignore[arg-type]
        planner=FallbackPlanner(),  # type: ignore[arg-type]
    )

    response = asyncio.run(runner.run(_request()))

    assert response.status == "failed"
    assert response.sections == []
    assert "LLM 未配置" in response.warnings[-1]


class FallbackPlanner:
    async def plan(self, request: AgentChatRequest):
        from app.agent.planner import AgentPlanner

        result = AgentPlanner._fallback_result(request, "fallback")
        return result.__class__(plan=result.plan, request=result.request, warnings=[])


class SingleNeedPlanner:
    def __init__(self, data_need: str) -> None:
        self.data_need = data_need

    async def plan(self, request: AgentChatRequest):
        from app.agent.planner import AgentPlanner

        result = AgentPlanner._fallback_result(request, "fallback")
        plan = result.plan.model_copy(
            update={
                "data_needs": [self.data_need],
                "steps": [
                    step.model_copy(update={"data_needs": [self.data_need]})
                    for step in result.plan.steps
                ],
            }
        )
        return result.__class__(plan=plan, request=result.request, warnings=[])
