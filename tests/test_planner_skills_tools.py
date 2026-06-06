"""Tests for Planner, Skills, and ToolRouter."""

from __future__ import annotations

import asyncio
from pathlib import Path

from app.agent.planner import AgentPlanner
from app.agent.tool_router import ToolRouter
from app.llm.chat_client import ChatResult
from app.schemas.agent_contracts import AgentChatParams, AgentChatRequest
from app.skills.loader import SkillLoader
from app.skills.registry import SkillRegistry
from app.skills.selector import SkillSelector


class FakeGenerateClient:
    def __init__(self, results: list[ChatResult]) -> None:
        self.results = results
        self.calls: list[dict[str, object]] = []

    async def generate(self, **kwargs):
        self.calls.append(kwargs)
        return self.results.pop(0)


def _request(intent: str = "RECENT_SUMMARY") -> AgentChatRequest:
    return AgentChatRequest(
        teacher_id="teacher_1",
        student_id="stu_1",
        message="总结一下最近学习情况",
        params=AgentChatParams(intent=intent),
    )


def test_planner_parses_data_needs_without_tools() -> None:
    planner = AgentPlanner(
        chat_client=FakeGenerateClient(  # type: ignore[arg-type]
            [
                ChatResult(
                    ok=True,
                    content=(
                        '{"intent":"HOMEWORK_DIAGNOSIS","task_goal":"诊断错题",'
                        '"steps":[{"step_id":"step_1","goal":"看错题",'
                        '"data_needs":["wrong_question_stats"],'
                        '"output_requirements":["给出建议"]}],'
                        '"data_needs":["student_profile","wrong_question_stats"],'
                        '"response_requirements":["温和"],'
                        '"planner_reason":"用户要求诊断"}'
                    ),
                )
            ]
        )
    )

    result = asyncio.run(planner.plan(_request()))

    assert result.plan.intent == "HOMEWORK_DIAGNOSIS"
    assert result.plan.data_needs == ["student_profile", "wrong_question_stats"]
    assert "user.get_student_profile" not in result.plan.model_dump_json()
    assert result.request.params.intent == "HOMEWORK_DIAGNOSIS"


def test_planner_falls_back_on_invalid_json() -> None:
    planner = AgentPlanner(
        chat_client=FakeGenerateClient(  # type: ignore[arg-type]
            [ChatResult(ok=True, content="not json")]
        )
    )

    result = asyncio.run(planner.plan(_request("PARENT_REPLY")))

    assert result.plan.intent == "PARENT_REPLY"
    assert "student_profile" in result.plan.data_needs
    assert result.warnings


def test_skill_loader_and_selector(tmp_path: Path) -> None:
    root = tmp_path / "skills"
    (root / "recent-summary").mkdir(parents=True)
    (root / "home-school-communication").mkdir(parents=True)
    (root / "recent-summary" / "SKILL.md").write_text(
        "# Recent Summary\n\n## Description\nA\n\n## Instructions\nB",
        encoding="utf-8",
    )
    (root / "home-school-communication" / "SKILL.md").write_text(
        "# Communication\n\n## Description\nC\n\n## Instructions\nD",
        encoding="utf-8",
    )
    registry = SkillRegistry(SkillLoader(root))
    selector = SkillSelector(registry)

    result = selector.select("RECENT_SUMMARY")

    assert [skill.name for skill in result.skills] == [
        "recent-summary",
        "home-school-communication",
    ]
    assert not result.warnings


def test_tool_router_maps_data_needs_to_allowed_tools() -> None:
    plan = AgentPlanner._fallback_result(_request("HOMEWORK_DIAGNOSIS"), "fallback").plan

    result = ToolRouter().route(plan)

    assert "user.get_student_profile" in result.allowed_tools
    assert "wrong_question.get_stats" in result.allowed_tools
    assert "wrong_question.list_recent" in result.allowed_tools
