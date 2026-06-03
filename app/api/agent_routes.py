"""HTTP routes for the draft-only Agent MVP."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.engine import get_db
from app.schemas.agent import AgentChatRequest
from app.schemas.response import AgentChatResponse, HealthResponse
from app.services.agent_service import AgentService

router = APIRouter()
agent_service = AgentService()


@router.get("/health", response_model=HealthResponse, tags=["system"])
async def health_check() -> HealthResponse:
    """Return API health for local frontend-backend integration checks."""

    return HealthResponse(status="ok", service="home-school-agent-api")


@router.post("/agent/mvp/chat", response_model=AgentChatResponse, tags=["agent"])
async def chat_with_agent(
    request: AgentChatRequest, db: AsyncSession = Depends(get_db)
) -> AgentChatResponse:
    """Generate a teacher-editable draft using real database data.

    This endpoint intentionally performs no writes and does not send messages to
    parents. It only returns a draft response for frontend integration.
    """

    return await agent_service.generate(db, request)