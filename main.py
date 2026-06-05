"""CLI entrypoint for local development.

The ASGI app lives in ``app.main:app`` so local and deployment commands use the
same import path:

    uv run uvicorn app.main:app --reload
"""

import os

import uvicorn


def main() -> None:
    """Run the local FastAPI development server."""

    host = os.getenv("AGENT_API_HOST", "127.0.0.1")
    port = int(os.getenv("AGENT_API_PORT", "8000"))
    reload = os.getenv("AGENT_API_RELOAD", "false").lower() == "true"
    uvicorn.run("app.main:app", host=host, port=port, reload=reload)


if __name__ == "__main__":
    main()
