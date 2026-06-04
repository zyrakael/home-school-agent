"""Gateway for routing Agent tool calls to MCP servers."""

from __future__ import annotations

import json
from contextlib import asynccontextmanager
from functools import lru_cache
from typing import Any, AsyncIterator

import anyio
import httpx

from app.core.config import MCPServerConfig, get_settings
from app.mcp_gateway.schemas import (
    MCPToolDefinition,
    MCPToolError,
    MCPToolResult,
    MCPToolSource,
)


class MCPGateway:
    """Route tool calls to configured MCP servers."""

    def __init__(
        self,
        servers: list[MCPServerConfig] | None = None,
        default_timeout_seconds: float | None = None,
    ) -> None:
        settings = get_settings()
        self.servers = servers if servers is not None else settings.mcp_servers
        self.default_timeout_seconds = (
            default_timeout_seconds
            if default_timeout_seconds is not None
            else settings.mcp_default_timeout_seconds
        )

    async def call_tool(
        self,
        tool_name: str,
        arguments: dict[str, Any] | None = None,
        context: dict[str, Any] | None = None,
    ) -> MCPToolResult:
        """Call a tool on the MCP server selected by tool name prefix."""

        server = self._select_server(tool_name)
        if server is None:
            return self._error(
                server="",
                tool=tool_name,
                code="server_not_configured",
                message=f"No MCP server configured for tool '{tool_name}'.",
            )

        payload = dict(arguments or {})
        if context:
            payload.setdefault("context", context)

        timeout = server.timeout_seconds or self.default_timeout_seconds
        try:
            with anyio.fail_after(timeout):
                async with self._session(server) as session:
                    raw_result = await session.call_tool(tool_name, arguments=payload)
        except TimeoutError:
            return self._error(
                server=server.name,
                tool=tool_name,
                code="timeout",
                message=f"MCP tool '{tool_name}' timed out after {timeout:g}s.",
            )
        except Exception as exc:
            return self._error(
                server=server.name,
                tool=tool_name,
                code=exc.__class__.__name__,
                message=str(exc),
            )

        return self._normalize_result(
            server=server.name,
            tool=tool_name,
            raw_result=raw_result,
        )

    async def list_tools(self) -> list[MCPToolDefinition]:
        """Discover tool metadata from every configured MCP server."""

        discovered: list[MCPToolDefinition] = []
        for server in self.servers:
            try:
                async with self._session(server) as session:
                    result = await session.list_tools()
                for tool in result.tools:
                    discovered.append(
                        MCPToolDefinition(
                            server=server.name,
                            name=tool.name,
                            description=getattr(tool, "description", "") or "",
                            input_schema=self._tool_input_schema(tool),
                        )
                    )
            except Exception:
                continue
        return discovered

    async def list_tool_names(self) -> dict[str, list[str]]:
        """List tool names grouped by MCP server."""

        grouped: dict[str, list[str]] = {}
        for tool in await self.list_tools():
            grouped.setdefault(tool.server, []).append(tool.name)
        return grouped

    def _select_server(self, tool_name: str) -> MCPServerConfig | None:
        domain = tool_name.split(".", 1)[0]
        for server in self.servers:
            if domain in server.tool_prefixes or tool_name in server.tool_prefixes:
                return server
        if len(self.servers) == 1:
            return self.servers[0]
        return None

    @asynccontextmanager
    async def _session(self, server: MCPServerConfig) -> AsyncIterator[Any]:
        from mcp import ClientSession

        if server.transport == "streamable_http":
            if not server.url:
                raise ValueError(f"MCP server '{server.name}' is missing url.")
            from mcp.client.streamable_http import streamable_http_client

            async with httpx.AsyncClient(headers=server.headers) as http_client:
                async with streamable_http_client(
                    server.url,
                    http_client=http_client,
                ) as (read_stream, write_stream, _):
                    async with ClientSession(read_stream, write_stream) as session:
                        await session.initialize()
                        yield session
            return

        if server.transport == "stdio":
            if not server.command:
                raise ValueError(f"MCP server '{server.name}' is missing command.")
            from mcp.client.stdio import StdioServerParameters, stdio_client

            params = StdioServerParameters(
                command=server.command,
                args=server.args,
                env=server.env,
            )
            async with stdio_client(params) as (read_stream, write_stream):
                async with ClientSession(read_stream, write_stream) as session:
                    await session.initialize()
                    yield session
            return

        raise ValueError(f"Unsupported MCP transport: {server.transport}")

    def _normalize_result(
        self,
        *,
        server: str,
        tool: str,
        raw_result: Any,
    ) -> MCPToolResult:
        structured = getattr(raw_result, "structuredContent", None)
        if structured is None:
            structured = getattr(raw_result, "structured_content", None)

        payload = structured
        if payload is None:
            payload = self._content_to_payload(raw_result)

        if isinstance(payload, MCPToolResult):
            return payload

        if isinstance(payload, dict) and {"ok", "data", "source"}.issubset(payload):
            return MCPToolResult.model_validate(payload)

        return MCPToolResult(
            ok=True,
            data=payload,
            evidence=[],
            source=MCPToolSource(server=server, tool=tool),
            error=None,
        )

    @staticmethod
    def _content_to_payload(raw_result: Any) -> Any:
        content = getattr(raw_result, "content", None) or []
        if not content:
            return None

        text = getattr(content[0], "text", None)
        if text is None:
            return content[0]

        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return text

    @staticmethod
    def _tool_input_schema(tool: Any) -> dict[str, Any]:
        schema = getattr(tool, "inputSchema", None)
        if schema is None:
            schema = getattr(tool, "input_schema", None)
        if hasattr(schema, "model_dump"):
            schema = schema.model_dump()
        return schema if isinstance(schema, dict) else {"type": "object", "properties": {}}

    @staticmethod
    def _error(*, server: str, tool: str, code: str, message: str) -> MCPToolResult:
        return MCPToolResult(
            ok=False,
            data=None,
            evidence=[],
            source=MCPToolSource(server=server, tool=tool),
            error=MCPToolError(code=code, message=message),
        )


@lru_cache
def get_mcp_gateway() -> MCPGateway:
    """Return the shared MCP gateway instance."""

    return MCPGateway()
