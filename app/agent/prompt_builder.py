"""Prompt builder — formats MCP tool data into LLM prompts for each Agent intent."""

from __future__ import annotations

import json

from pydantic import BaseModel, Field

from app.schemas.agent import AgentChatRequest
from app.schemas.response import AgentSection


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
    def build_tool_calling_prompt(request: AgentChatRequest) -> tuple[str, str]:
        """Build prompts for an agent that can call MCP tools itself."""

        payload = {
            "teacher_id": request.teacher_id,
            "student_id": request.student_id,
            "message": request.message,
            "scene": request.scene,
            "params": request.params.model_dump(),
            "context": request.context,
        }
        user_prompt = f"""\
        请根据用户请求生成老师可编辑的家校沟通草稿。

        你可以按需调用 MCP 工具获取学生档案、作业、错题、课堂表现等事实数据。
        优先使用工具获取事实；不要编造未提供的数据。
        如果工具没有查到数据，请在最终 JSON 中自然说明，并给出老师下一步可以怎么做。
        如果家长问题涉及退费、投诉、举报、换老师、不想上课等高风险场景，请生成内部处理建议，不要生成可直接发送给家长的话术。

        用户请求 JSON：
        {json.dumps(payload, ensure_ascii=False, indent=2, default=str)}

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
