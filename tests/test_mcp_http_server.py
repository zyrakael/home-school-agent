"""Tests for MCP Gateway HTTP client behavior."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import Any

import mcp
import mcp.client.streamable_http
from app.core.config import MCPServerConfig
from app.mcp_gateway.gateway import MCPGateway


def test_streamable_http_gateway_passes_configured_headers(monkeypatch: Any) -> None:
    captured: dict[str, str | None] = {}

    class FakeClientSession:
        def __init__(self, read_stream: object, write_stream: object) -> None:
            self.read_stream = read_stream
            self.write_stream = write_stream

        async def __aenter__(self) -> "FakeClientSession":
            return self

        async def __aexit__(self, *args: object) -> None:
            return None

        async def initialize(self) -> None:
            return None

    @asynccontextmanager
    async def fake_streamable_http_client(
        url: str,
        *,
        http_client: Any = None,
        terminate_on_close: bool = True,
    ) -> Any:
        captured["url"] = url
        captured["authorization"] = http_client.headers.get("Authorization")
        yield object(), object(), lambda: None

    monkeypatch.setattr(mcp, "ClientSession", FakeClientSession)
    monkeypatch.setattr(
        mcp.client.streamable_http,
        "streamable_http_client",
        fake_streamable_http_client,
    )

    server = MCPServerConfig(
        name="data",
        transport="streamable_http",
        url="http://mcp-data:8100/mcp",
        headers={"Authorization": "Bearer secret-token"},
    )
    gateway = MCPGateway(servers=[server])

    async def run_session() -> None:
        async with gateway._session(server):
            return None

    asyncio.run(run_session())

    assert captured == {
        "url": "http://mcp-data:8100/mcp",
        "authorization": "Bearer secret-token",
    }
