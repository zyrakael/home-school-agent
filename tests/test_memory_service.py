"""Tests for the Agent work-context memory layer."""

from __future__ import annotations

import asyncio

from app.agent.planner import AgentPlanner
from app.agent.prompt_builder import PromptBuilder
from app.memory import InMemoryMemoryStore, MemoryRecord, MemoryService
from app.schemas.agent_contracts import AgentChatParams, AgentChatRequest
from app.schemas.response import AgentChatResponse, AgentSection


def _request(intent: str = "PARENT_REPLY") -> AgentChatRequest:
    return AgentChatRequest(
        teacher_id="teacher_1",
        student_id="stu_1",
        message="家长问作业是不是太多了",
        params=AgentChatParams(
            intent=intent,
            parent_question="作业是不是太多了？",
            tone="温和",
        ),
        context={
            "pasted_chat": "家长：昨天孩子写到很晚，这段只允许本轮参考。",
            "teacher_note": "老师补充：最近需要关注完成时长。",
        },
    )


def test_parent_reply_recalls_teacher_context_and_internal_policy() -> None:
    store = InMemoryMemoryStore(
        [
            MemoryRecord(
                owner_key="teacher:teacher_1",
                memory_type="teacher_reply_style",
                content="偏好先回应关切，再给出下一步安排。",
            ),
            MemoryRecord(
                owner_key="teacher:teacher_1",
                memory_type="teacher_case_handling",
                content="作业量争议先解释目标，再观察完成时长。",
            ),
        ]
    )
    service = MemoryService(store)
    request = _request("PARENT_REPLY")
    plan = AgentPlanner._fallback_result(request, "fallback").plan

    pack = asyncio.run(service.recall(request, plan))

    assert pack.teacher_reply_styles == ["偏好先回应关切，再给出下一步安排。"]
    assert pack.teacher_case_handlings == ["作业量争议先解释目标，再观察完成时长。"]
    assert any("投诉、退费、师资争议" in policy for policy in pack.internal_reply_policies)
    assert "家长：昨天孩子写到很晚，这段只允许本轮参考。" in pack.ephemeral_turn_context


def test_recent_summary_recalls_student_learning_patterns() -> None:
    store = InMemoryMemoryStore(
        [
            MemoryRecord(
                owner_key="student:stu_1",
                memory_type="student_learning_pattern",
                content="近两周计算题稳定，应用题审题漏条件较多。",
            ),
        ]
    )
    service = MemoryService(store)
    request = _request("RECENT_SUMMARY")
    plan = AgentPlanner._fallback_result(request, "fallback").plan

    pack = asyncio.run(service.recall(request, plan))

    assert pack.student_learning_patterns == ["近两周计算题稳定，应用题审题漏条件较多。"]


def test_ephemeral_chat_context_is_not_persisted_on_commit() -> None:
    store = InMemoryMemoryStore()
    service = MemoryService(store)
    request = _request("RECENT_SUMMARY")
    plan = AgentPlanner._fallback_result(request, "fallback").plan
    response = AgentChatResponse(
        request_id="req_1",
        intent="RECENT_SUMMARY",
        status="success",
        title="近7天学习情况总结",
        content="整体表现稳定。",
        sections=[
            AgentSection(
                name="学习表现",
                items=["计算题正确率稳定，应用题审题需要继续关注。"],
            ),
            AgentSection(
                name="临时聊天",
                items=["家长说昨天孩子写到很晚。"],
            ),
        ],
    )

    asyncio.run(service.commit(request, plan, object(), response))

    student_records = store.list(owner_key="student:stu_1")
    assert [record.content for record in student_records] == [
        "学生稳定学习特征：计算题正确率稳定，应用题审题需要继续关注。"
    ]
    assert all("家长说" not in record.content for record in student_records)
    assert all("昨天孩子写到很晚" not in record.content for record in student_records)


def test_prompt_builder_includes_work_context_rules_and_payload() -> None:
    service = MemoryService(
        InMemoryMemoryStore(
            [
                MemoryRecord(
                    owner_key="student:stu_1",
                    memory_type="student_learning_pattern",
                    content="应用题审题漏条件较多。",
                )
            ]
        )
    )
    request = _request("RECENT_SUMMARY")
    plan = AgentPlanner._fallback_result(request, "fallback").plan
    pack = asyncio.run(service.recall(request, plan))

    _, user_prompt = PromptBuilder.build_tool_calling_prompt(
        request,
        execution_plan=plan,
        memory_context=pack,
    )

    assert "可用工作上下文 JSON" in user_prompt
    assert "MCP 工具事实 > 本轮请求/粘贴上下文 > Session Memory > 长期记忆 > Skills 表达规则" in user_prompt
    assert "应用题审题漏条件较多" in user_prompt
    assert "本轮粘贴聊天记录只能用于本轮生成" in user_prompt
