"""Prompt builder — formats MCP tool data into LLM prompts for each Agent intent."""

from __future__ import annotations

import json

from pydantic import BaseModel, Field

from app.schemas.agent import AgentChatRequest, AgentExecutionPlan
from app.schemas.response import AgentSection
from app.skills.loader import Skill


# ---------------------------------------------------------------------------
# LLM output schema — the shape we ask the model to return
# ---------------------------------------------------------------------------


class LLMResponsePayload(BaseModel):
    """The JSON object we expect the LLM to return."""

    title: str
    content: str
    sections: list[AgentSection] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Shared system prompt
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """\
你是一位经验丰富的教育沟通助手，帮助老师生成与家长沟通的草稿。

重要规则：
1. 永远不要编造数据 —— 只使用下面提供的事实数据
2. 语气要专业、温和、有建设性
3. 多说"可以关注"、"建议"而不是"很差"、"不好"
4. 不要承诺具体分数或排名
5. 省略号、破折号等标点要规范使用
6. 当家长问题涉及退费、投诉时，回复策略应该是"内部处理"，不要直接回复话术

输出格式为严格的 JSON，不要添加额外的说明文字：
{
"title": "草稿标题",
"content": "正文内容，使用\\n\\n分段",
"sections": [
{"name": "段落名称", "items": ["要点1", "要点2"]}
]
}
"""


# ---------------------------------------------------------------------------
# PromptBuilder
# ---------------------------------------------------------------------------


class PromptBuilder:
    """Build the direct LLM prompt from MCP tool data."""

    @staticmethod
    def build_tool_calling_prompt(
        request: AgentChatRequest,
        *,
        execution_plan: AgentExecutionPlan | None = None,
        selected_skills: list[Skill] | None = None,
        allowed_tools: set[str] | None = None,
    ) -> tuple[str, str]:
        """Build prompts for an agent that can call MCP tools itself."""

        payload = {
            "teacher_id": request.teacher_id,
            "student_id": request.student_id,
            "message": request.message,
            "scene": request.scene,
            "params": request.params.model_dump(),
            "context": request.context,
        }
        plan_payload = execution_plan.model_dump() if execution_plan else None
        skill_payload = [
            {
                "name": skill.name,
                "description": skill.description,
                "instructions": skill.instructions,
            }
            for skill in (selected_skills or [])
        ]
        allowed_tool_list = sorted(allowed_tools or [])
        user_prompt = f"""\
        请根据用户请求生成老师可编辑的家校沟通草稿。

        你必须按内部执行计划完成任务。
        Skills 是表达和分析规则；MCP tools 是事实数据来源。
        只能调用 allowed_tools 中列出的 MCP 工具，不要尝试调用其他工具。
        优先使用 allowed_tools 获取事实；不要编造未提供的数据。
        如果工具没有查到数据，请在最终 JSON 中自然说明，并给出老师下一步可以怎么做。
        如果数据不足，请生成“数据不足版”草稿，并提醒老师补充或确认关键事实。

        用户请求 JSON：
        {json.dumps(payload, ensure_ascii=False, indent=2, default=str)}

        内部执行计划 JSON：
        {json.dumps(plan_payload, ensure_ascii=False, indent=2, default=str)}

        已选 Skills JSON：
        {json.dumps(skill_payload, ensure_ascii=False, indent=2, default=str)}

        allowed_tools JSON：
        {json.dumps(allowed_tool_list, ensure_ascii=False, indent=2)}

        最终只返回严格 JSON，字段必须符合：
        {{
          "title": "草稿标题",
          "content": "正文内容，使用\\n\\n分段",
          "sections": [
            {{"name": "段落名称", "items": ["要点1", "要点2"]}}
          ]
        }}
        """
        return SYSTEM_PROMPT, user_prompt
