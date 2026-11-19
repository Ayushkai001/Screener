"""Entrypoint alias for STRATLAB API Server.

Re-exports `app` from `backend.app.api.main` for convenient invocation via:
`uvicorn backend.app.main:app --reload --port 8000`
"""

from backend.app.api.main import app, create_app

__all__ = ["app", "create_app"]
