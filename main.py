"""CLI entrypoint for local development.

The ASGI app lives in ``app.main:app`` so local and deployment commands use the
same import path:

    uv run uvicorn app.main:app --reload
"""

import uvicorn


def main() -> None:
    """Run the local FastAPI development server."""

    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)


if __name__ == "__main__":
    main()
