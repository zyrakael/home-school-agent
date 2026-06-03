"""FastAPI application factory for the home-school Agent MVP."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.agent_routes import router as agent_router
from app.api.student_routes import router as student_router


def create_app() -> FastAPI:
    app = FastAPI(
        title="Home-school Agent API",
        version="0.1.0",
        description="MVP API backed by MySQL.",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(agent_router)
    app.include_router(student_router)
    return app


app = create_app()
