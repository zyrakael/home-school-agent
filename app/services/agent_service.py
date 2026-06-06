"""Agent service — run the LangGraph Agent workflow."""

from __future__ import annotations

from app.agent.agent_graph import AgentGraphRunner
from app.agent.planner import AgentPlanner
from app.agent.tool_router import ToolRouter
from app.llm.chat_client import ChatClient
from app.mcp_gateway import MCPGateway
from app.memory import MemoryService, SessionMemoryService
from app.schemas.agent_contracts import AgentChatRequest
from app.schemas.response import AgentChatResponse
from app.skills.selector import SkillSelector


class AgentService:
    """Stateless Agent service backed by a LangGraph workflow."""

    def __init__(
        self,
        *,
        gateway: MCPGateway | None = None,
        chat_client: ChatClient | None = None,
        planner: AgentPlanner | None = None,
        skill_selector: SkillSelector | None = None,
        tool_router: ToolRouter | None = None,
        memory_service: MemoryService | None = None,
        session_memory_service: SessionMemoryService | None = None,
        max_tool_rounds: int = 4,
    ) -> None:
        self.graph_runner = AgentGraphRunner(
            gateway=gateway,
            chat_client=chat_client,
            planner=planner or AgentPlanner(),
            skill_selector=skill_selector or SkillSelector(),
            tool_router=tool_router or ToolRouter(),
            memory_service=memory_service or MemoryService(),
            session_memory_service=session_memory_service or SessionMemoryService(),
            max_tool_rounds=max_tool_rounds,
        )

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    async def generate(self, request: AgentChatRequest) -> AgentChatResponse:
        """Generate a draft from a plan, local skills, and MCP tools."""

        return await self.graph_runner.run(request)
