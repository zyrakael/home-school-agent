"""Prompt builder — formats MCP tool data into LLM prompts for each Agent intent."""

from __future__ import annotations

import json

from pydantic import BaseModel, Field

from app.memory import MemoryPack, SessionState
from app.schemas.agent_contracts import AgentChatRequest, AgentExecutionPlan
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
        memory_context: MemoryPack | None = None,
        session_context: SessionState | None = None,
    ) -> tuple[str, str]:
        """Build prompts for an agent that can call MCP tools itself."""

        payload = {
            "conversation_id": request.conversation_id,
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
        memory_payload = memory_context.model_dump() if memory_context else None
        session_payload = (
            session_context.model_dump()
            if session_context and session_context.has_content()
            else None
        )
        user_prompt = f"""\
        请根据用户请求生成老师可编辑的家校沟通草稿。

        你必须按内部执行计划完成任务。
        Skills 是表达和分析规则；MCP tools 是事实数据来源。
        Session 工作状态是当前对话的短期上下文，用于理解“那”“继续”“帮我改一下”等承接指令。
        可用工作上下文是教辅人员可复用的高价值上下文，不是家长画像，也不是聊天记录库。
        只能调用 allowed_tools 中列出的 MCP 工具，不要尝试调用其他工具。
        优先使用 allowed_tools 获取事实；不要编造未提供的数据。
        如果 student_id 为空且 allowed_tools 包含 user.list_students，应先调用该工具查询可选学生。
        如果查到的学生无法唯一对应本轮请求，最终回复应请老师补充学生姓名或学生 ID，不要继续调用需要 student_id 的工具。
        优先级：MCP 工具事实 > 本轮请求/粘贴上下文 > Session Memory > 长期记忆 > Skills 表达规则。
        本轮粘贴聊天记录只能用于本轮生成，不能作为长期记忆或家长画像使用。
        不得保存、复述或推断家长个人画像、隐私细节、一次性情绪表达。
        投诉、退费、师资争议等敏感问题，按内部处理建议输出，不要生成直接承诺话术。
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

        Session 工作状态 JSON：
        {json.dumps(session_payload, ensure_ascii=False, indent=2, default=str)}

        可用工作上下文 JSON：
        {json.dumps(memory_payload, ensure_ascii=False, indent=2, default=str)}

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
