"""API response schemas."""

from pydantic import BaseModel, Field


class AgentSection(BaseModel):
    """A named display section for structured frontend rendering."""

    name: str
    items: list[str] = Field(default_factory=list)


class AgentChatResponse(BaseModel):
    """Draft-only Agent response returned to the frontend."""

    request_id: str
    intent: str
    status: str
    title: str
    content: str
    sections: list[AgentSection] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    available_actions: list[str] = Field(default_factory=list)
    is_draft: bool = True
    auto_send: bool = False
    write_database: bool = False
