"""Shared schemas for MCP tool calls."""

from typing import Any

from pydantic import BaseModel, Field


class MCPToolSource(BaseModel):
    """The MCP server and tool that produced a result."""

    server: str
    tool: str


class MCPToolError(BaseModel):
    """Normalized MCP tool error."""

    code: str
    message: str


class MCPToolResult(BaseModel):
    """Normalized result shape returned by every tool call."""

    ok: bool
    data: Any = None
    evidence: list[str] = Field(default_factory=list)
    source: MCPToolSource
    error: MCPToolError | None = None


class MCPToolDefinition(BaseModel):
    """Tool metadata discovered from an MCP server."""

    server: str
    name: str
    description: str = ""
    input_schema: dict[str, Any] = Field(default_factory=dict)


def ok_result(
    *,
    server: str,
    tool: str,
    data: Any,
    evidence: list[str] | None = None,
) -> dict[str, Any]:
    """Build a serializable successful MCP tool result."""

    return {
        "ok": True,
        "data": data,
        "evidence": evidence or [],
        "source": {"server": server, "tool": tool},
        "error": None,
    }


def error_result(
    *,
    server: str,
    tool: str,
    code: str,
    message: str,
) -> dict[str, Any]:
    """Build a serializable failed MCP tool result."""

    return {
        "ok": False,
        "data": None,
        "evidence": [],
        "source": {"server": server, "tool": tool},
        "error": {"code": code, "message": message},
    }
