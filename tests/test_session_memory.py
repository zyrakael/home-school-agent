"""Tests for short-lived Agent session memory."""

from __future__ import annotations

import asyncio

from app.agent.agent_graph import AgentRunResult
from app.agent.planner import AgentPlanner
from app.agent.prompt_builder import PromptBuilder
from app.memory import SessionMemoryService, SessionMemoryStore
from app.mcp_gateway import MCPToolResult, MCPToolSource
from app.schemas.agent_contracts import AgentChatParams, AgentChatRequest
from app.schemas.response import AgentChatResponse, AgentSection


def _request(message: str = "帮我看一下小明最近数学作业情况") -> AgentChatRequest:
    return AgentChatRequest(
        conversation_id="conv_1",
        teacher_id="teacher_1",
        student_id="stu_1",
        message=message,
        scene="agent_workspace",
        params=AgentChatParams(intent="RECENT_SUMMARY", subject="数学"),
    )


def _response() -> AgentChatResponse:
    return AgentChatResponse(
        request_id="req_1",
        intent="RECENT_SUMMARY",
        status="success",
        title="近7天数学作业情况",
        content="小明最近数学作业整体稳定，应用题错误率偏高。",
        sections=[
            AgentSection(
                name="作业表现",
                items=["应用题错误率偏高，主要集中在审题漏条件。"],
            )
        ],
        evidence=["已查询近7天数学作业", "已查询近期错题"],
    )


def test_session_commit_and_recall_keeps_current_work_state() -> None:
    service = SessionMemoryService()
    request = _request()
    plan = AgentPlanner._fallback_result(request, "fallback").plan
    run_result = AgentRunResult(
        content='{"title":"近7天数学作业情况","content":"正文","sections":[]}',
        evidence=["已查询近7天数学作业"],
        tool_results={
            "learning.get_recent_homeworks": MCPToolResult(
                ok=True,
                data={"items": []},
                evidence=["已查询近7天数学作业"],
                source=MCPToolSource(server="fake", tool="learning.get_recent_homeworks"),
            )
        },
    )

    asyncio.run(service.commit(request, plan, run_result, _response()))
    state = asyncio.run(service.recall(request))

    assert state.student_id == "stu_1"
    assert state.subject == "数学"
    assert state.last_intent == "RECENT_SUMMARY"
    assert state.called_tools == ["learning.get_recent_homeworks"]
    assert "应用题错误率偏高" in state.key_data_summary[0]
    assert state.suggested_next_step == "generate_parent_reply"


def test_followup_request_can_inherit_session_student() -> None:
    service = SessionMemoryService()
    first_request = _request()
    plan = AgentPlanner._fallback_result(first_request, "fallback").plan
    asyncio.run(service.commit(first_request, plan, AgentRunResult(content="{}"), _response()))
    state = asyncio.run(service.recall(first_request))
    followup = AgentChatRequest(
        conversation_id="conv_1",
        teacher_id="teacher_1",
        student_id="",
        message="那帮我生成一段发给家长的话",
        params=AgentChatParams(intent="PARENT_REPLY", subject="数学"),
    )

    resolved = service.resolve_request(followup, state)

    assert resolved.student_id == "stu_1"
    assert resolved.params.intent == "PARENT_REPLY"


def test_session_state_is_isolated_by_conversation_id() -> None:
    service = SessionMemoryService()
    request = _request()
    plan = AgentPlanner._fallback_result(request, "fallback").plan
    asyncio.run(service.commit(request, plan, AgentRunResult(content="{}"), _response()))

    other_state = asyncio.run(
        service.recall(request.model_copy(update={"conversation_id": "conv_2"}))
    )

    assert not other_state.has_content()
    assert other_state.conversation_id == "conv_2"


def test_session_state_expires_after_ttl() -> None:
    service = SessionMemoryService(SessionMemoryStore(ttl_seconds=-1))
    request = _request()
    plan = AgentPlanner._fallback_result(request, "fallback").plan
    asyncio.run(service.commit(request, plan, AgentRunResult(content="{}"), _response()))

    expired_state = asyncio.run(service.recall(request))

    assert not expired_state.has_content()
    assert expired_state.conversation_id == "conv_1"


def test_prompt_builder_includes_session_state() -> None:
    service = SessionMemoryService()
    request = _request()
    plan = AgentPlanner._fallback_result(request, "fallback").plan
    asyncio.run(service.commit(request, plan, AgentRunResult(content="{}"), _response()))
    state = asyncio.run(service.recall(request))

    _, user_prompt = PromptBuilder.build_tool_calling_prompt(
        request,
        execution_plan=plan,
        session_context=state,
    )

    assert "Session 工作状态 JSON" in user_prompt
    assert "应用题错误率偏高" in user_prompt
    assert "Session Memory > 长期记忆" in user_prompt
