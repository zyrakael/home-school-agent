"""Route planner data needs to an MCP tool allow-list."""

from dataclasses import dataclass, field

from app.agent.tool_policy import ToolPolicy
from app.schemas.agent import AgentExecutionPlan


@dataclass
class ToolRouteResult:
    """Allowed tools and non-fatal routing warnings."""

    allowed_tools: set[str] = field(default_factory=set)
    warnings: list[str] = field(default_factory=list)


class ToolRouter:
    """Map abstract data needs to concrete MCP tool names."""

    def __init__(self, policy: ToolPolicy | None = None) -> None:
        self.policy = policy or ToolPolicy()

    def route(self, plan: AgentExecutionPlan) -> ToolRouteResult:
        result = ToolRouteResult()
        for need in plan.data_needs:
            tools = self.policy.tools_for_need(need)
            if not tools:
                result.warnings.append(f"未知数据需求已忽略：{need}")
                continue
            result.allowed_tools.update(tools)
        return result
