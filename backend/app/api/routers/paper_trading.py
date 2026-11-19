"""STRATLAB Paper Trading Management REST Endpoints."""

from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException
from shared.schemas.execution import OrderSide, OrderStatus, OrderType, PaperOrder
from backend.app.execution.paper.matching_engine import SimulatedMatchingEngine
from backend.app.execution.portfolio.ledger import PortfolioLedger


router = APIRouter(prefix="/paper", tags=["Paper Trading"])

# In-memory shared paper trading environment
matching_engine = SimulatedMatchingEngine(slippage_ticks=1, tick_size=0.05)
paper_ledger = PortfolioLedger(initial_cash=100_000.0, cost_profile="india_intraday")


@router.post("/orders", response_model=Dict[str, Any])
def submit_paper_order(order: PaperOrder) -> Dict[str, Any]:
    """Submit a paper trading order with queue-ahead simulation."""
    fill = matching_engine.submit_order(
        order=order,
        best_bid=order.price or 100.0,
        best_ask=(order.price or 100.0) + 0.05,
        level_depth_volume=1000,
    )

    # If immediately filled, update portfolio ledger
    if fill:
        paper_ledger.open_position(
            instrument_id=order.instrument_id,
            symbol=order.instrument_id,
            side="LONG" if order.side == OrderSide.BUY else "SHORT",
            price=fill.price,
            quantity=fill.quantity,
            timestamp_utc=fill.timestamp_utc,
        )

    return {
        "order_id": order.order_id,
        "status": matching_engine.orders[order.order_id].status.value,
        "filled": fill is not None,
        "fill_price": fill.price if fill else None,
    }


@router.get("/orders", response_model=List[Dict[str, Any]])
def list_orders() -> List[Dict[str, Any]]:
    """List all registered simulated orders."""
    return [o.model_dump() for o in matching_engine.orders.values()]


@router.get("/positions", response_model=List[Dict[str, Any]])
def list_positions() -> List[Dict[str, Any]]:
    """List current active open positions."""
    return [p.__dict__ for p in paper_ledger.positions.values()]


@router.get("/account", response_model=Dict[str, Any])
def get_account_summary() -> Dict[str, Any]:
    """Retrieve paper trading account equity, cash balance, and fee summary."""
    return {
        "initial_cash": paper_ledger.initial_cash,
        "cash": round(paper_ledger.cash, 2),
        "equity": round(paper_ledger.equity, 2),
        "realized_pnl": round(paper_ledger.realized_pnl, 2),
        "total_fees": round(paper_ledger.total_fees, 2),
        "open_positions_count": len(paper_ledger.positions),
    }
