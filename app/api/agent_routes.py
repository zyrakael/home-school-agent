"""HTTP routes for the draft-only Agent MVP."""

from fastapi import APIRouter

from app.schemas.agent import AgentChatRequest
from app.schemas.response import AgentChatResponse
from app.services.agent_service import AgentService

router = APIRouter()
agent_service = AgentService()


@router.post("/agent/mvp/chat", response_model=AgentChatResponse, tags=["agent"])
async def chat_with_agent(request: AgentChatRequest) -> AgentChatResponse:
    """Generate a teacher-editable draft using real database data.

    This endpoint intentionally performs no writes and does not send messages to
    parents. It only returns a draft response for frontend integration.
    """

    return await agent_service.generate(request)
