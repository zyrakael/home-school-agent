"""Application services.

Services coordinate schemas and database queries. They are intentionally
kept separate from API routes so LangGraph orchestration can replace them later
without changing the frontend contract.
"""