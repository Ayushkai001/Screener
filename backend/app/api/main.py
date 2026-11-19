"""STRATLAB Unified API Gateway Application.

Mounts Market Data, Strategy Studio, Paper Trading, and WebSocket Streaming.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from backend.app.api.routers.market_data import router as market_router
from backend.app.api.routers.paper_trading import router as paper_router
from backend.app.api.routers.strategies import router as strategies_router
from backend.app.api.routers.streaming import router as streaming_router


def create_app() -> FastAPI:
    app = FastAPI(
        title="STRATLAB Unified Trading Engine API",
        description="Unified trading research, order flow analytics, and simulation platform.",
        version="1.0.0",
    )

    # Allow cross-origin requests from frontend dev servers
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Health check
    @app.get("/health", tags=["System"])
    def health_check():
        return {"status": "ok", "service": "stratlab-api"}

    # Mount REST Subsystems under /api/v1
    app.include_router(market_router, prefix="/api/v1")
    app.include_router(strategies_router, prefix="/api/v1")
    app.include_router(paper_router, prefix="/api/v1")

    # Mount WebSocket Streaming Multiplexer
    app.include_router(streaming_router)

    return app


app = create_app()
