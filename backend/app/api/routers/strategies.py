"""STRATLAB Strategy Studio and Backtest REST Endpoints."""

from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from shared.schemas.market_data import Candle
from shared.schemas.provenance import DataQuality, ProvenanceMetadata
from backend.app.execution.backtest.engine import BacktestEngine
from backend.app.execution.portfolio.ledger import PortfolioLedger
from backend.app.strategy.compiler.compiler import (
    ProvenanceIncompatibilityError,
    StrategyCompilationError,
    StrategyCompiler,
)
from backend.app.strategy.ir.models import StrategyIR
from backend.app.strategy.registry.components import ComponentDefinition, ComponentRegistry


router = APIRouter(prefix="/strategies", tags=["Strategies & Backtest Lab"])


class CompileRequest(BaseModel):
    strategy: StrategyIR
    target_feed_quality: Optional[DataQuality] = None


class CompileResponse(BaseModel):
    status: str = "ok"
    highest_required_quality: str
    required_feeds: List[str]
    required_indicators: List[Dict[str, Any]]


class BacktestRequest(BaseModel):
    strategy: StrategyIR
    initial_cash: float = 100_000.0
    cost_profile: str = "india_intraday"
    candles: Optional[List[Candle]] = None


@router.get("/components", response_model=List[ComponentDefinition])
def list_available_components() -> List[ComponentDefinition]:
    """Retrieve catalog of available indicators, order flow metrics, and SMC structures."""
    return ComponentRegistry.list_all()


@router.post("/compile", response_model=CompileResponse)
def compile_strategy(payload: CompileRequest) -> CompileResponse:
    """Validate Strategy IR and enforce provenance compatibility."""
    compiler = StrategyCompiler(target_feed_quality=payload.target_feed_quality)
    try:
        compiled = compiler.compile(payload.strategy)
        return CompileResponse(
            highest_required_quality=compiled.highest_required_quality.name,
            required_feeds=sorted(list(compiled.required_feeds)),
            required_indicators=compiled.required_indicators,
        )
    except ProvenanceIncompatibilityError as pie:
        raise HTTPException(status_code=400, detail={"error": "PROVENANCE_INCOMPATIBLE", "message": str(pie)})
    except StrategyCompilationError as sce:
        raise HTTPException(status_code=422, detail={"error": "COMPILATION_ERROR", "message": str(sce)})


@router.post("/backtest")
def run_backtest(payload: BacktestRequest) -> Dict[str, Any]:
    """Execute historical simulation and return metrics, equity curve, and trades."""
    compiler = StrategyCompiler()
    try:
        compiled = compiler.compile(payload.strategy)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    # If no candles provided, generate synthetic sample series for testing
    candles = payload.candles
    if not candles:
        prov = ProvenanceMetadata.exchange_verified("NSE_TBT")
        candles = []
        base_p = 100.0
        for i in range(50):
            p = base_p + (i * 0.4 if i < 20 else i * 0.9)
            candles.append(Candle(
                instrument_id="INS_NSE_RELIANCE",
                timestamp_utc=(i + 1) * 300000,
                timeframe=payload.strategy.base_timeframe,
                open=p,
                high=p + 2.0,
                low=p - 1.0,
                close=p + 1.2,
                volume=10000,
                provenance=prov,
            ))

    ledger = PortfolioLedger(initial_cash=payload.initial_cash, cost_profile=payload.cost_profile) # type: ignore
    engine = BacktestEngine(ledger=ledger)
    result = engine.run(compiled, candles)

    return {
        "metrics": result.metrics.__dict__,
        "equity_curve": result.equity_curve,
        "closed_trades": [t.__dict__ for t in result.closed_trades],
    }
