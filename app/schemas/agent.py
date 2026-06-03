"""Agent request schemas."""

from typing import Any, Literal

from pydantic import BaseModel, Field


AgentIntent = Literal[
    "RECENT_SUMMARY",
    "HOMEWORK_DIAGNOSIS",
    "LESSON_FEEDBACK",
    "PARENT_REPLY",
]


class AgentChatParams(BaseModel):
    """Optional frontend parameters for the MVP chat endpoint."""

    intent: AgentIntent = Field(default="RECENT_SUMMARY")
    time_range: str = Field(default="7d")
    subject: str = Field(default="数学")
    lesson_id: str | None = None
    tone: str = Field(default="温和")
    length: str = Field(default="标准版")
    parent_question: str | None = None


class AgentChatRequest(BaseModel):
    """Request body for POST /agent/mvp/chat."""

    teacher_id: str = Field(default="")
    student_id: str = Field(default="")
    message: str = Field(default="")
    scene: str = Field(default="student_detail")
    params: AgentChatParams = Field(default_factory=AgentChatParams)
    context: dict[str, Any] = Field(default_factory=dict)
