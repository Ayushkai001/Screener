"""STRATLAB Portfolio Ledger and Position Tracker."""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Literal, Optional
from backend.app.execution.portfolio.costs import CostModel, CostProfile


@dataclass
class Position:
    instrument_id: str
    symbol: str
    side: Literal["LONG", "SHORT"]
    quantity: int
    entry_price: float
    current_price: float
    unrealized_pnl: float = 0.0
    realized_pnl: float = 0.0
    entry_timestamp_utc: int = 0
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    trailing_stop: Optional[float] = None


@dataclass
class ClosedTrade:
    instrument_id: str
    symbol: str
    side: Literal["LONG", "SHORT"]
    quantity: int
    entry_price: float
    exit_price: float
    entry_time_utc: int
    exit_time_utc: int
    gross_pnl: float
    net_pnl: float
    total_fees: float
    exit_reason: str  # "TARGET", "STOP", "RULE", "TIMEOUT"


class PortfolioLedger:
    """
    Maintains cash balances, open positions, closed trade history, and portfolio equity.
    """

    def __init__(self, initial_cash: float = 100_000.0, cost_profile: CostProfile = "india_intraday"):
        self.initial_cash = initial_cash
        self.cash = initial_cash
        self.cost_profile = cost_profile
        self.positions: Dict[str, Position] = {}
        self.closed_trades: List[ClosedTrade] = []
        self.total_fees: float = 0.0
        self.realized_pnl: float = 0.0

    @property
    def equity(self) -> float:
        """Total account equity = Cash + market value of open positions."""
        position_value = sum(
            (p.current_price * p.quantity) if p.side == "LONG" else ((2 * p.entry_price - p.current_price) * p.quantity)
            for p in self.positions.values()
        )
        return self.cash + position_value

    def calculate_position_size(
        self,
        price: float,
        stop_price: Optional[float],
        risk_pct: float = 1.0,
        max_alloc_pct: float = 100.0,
    ) -> int:
        """
        Calculates safe position size based on capital risk and stop loss distance.
        """
        if price <= 0:
            return 0

        # Max cash allowable for this single trade
        max_capital_for_trade = self.equity * (max_alloc_pct / 100.0)
        max_shares_by_capital = int(max_capital_for_trade // price)

        if stop_price is None or stop_price <= 0 or abs(price - stop_price) < 1e-4:
            return max(1, min(max_shares_by_capital, int(self.cash // price)))

        # Risk-based sizing: Risk_Amount = Equity * risk_pct%
        risk_amount = self.equity * (risk_pct / 100.0)
        per_share_risk = abs(price - stop_price)
        shares_by_risk = int(risk_amount // per_share_risk)

        # Conservative bound: min of risk shares, capital shares, and available cash
        max_affordable = int(self.cash // price)
        allowed_shares = min(shares_by_risk, max_shares_by_capital, max_affordable)
        return max(0, allowed_shares)

    def open_position(
        self,
        instrument_id: str,
        symbol: str,
        side: Literal["LONG", "SHORT"],
        price: float,
        quantity: int,
        timestamp_utc: int,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
    ) -> Position:
        """Open or add to a position and deduct costs."""
        costs = CostModel.calculate(self.cost_profile, "BUY" if side == "LONG" else "SELL", price, quantity)
        self.total_fees += costs.total

        total_cost = (price * quantity) + costs.total
        self.cash -= total_cost

        pos = Position(
            instrument_id=instrument_id,
            symbol=symbol,
            side=side,
            quantity=quantity,
            entry_price=price,
            current_price=price,
            entry_timestamp_utc=timestamp_utc,
            stop_loss=stop_loss,
            take_profit=take_profit,
        )
        self.positions[instrument_id] = pos
        return pos

    def close_position(
        self,
        instrument_id: str,
        exit_price: float,
        timestamp_utc: int,
        reason: str = "RULE",
    ) -> Optional[ClosedTrade]:
        """Close an existing position and realize PnL."""
        pos = self.positions.pop(instrument_id, None)
        if not pos:
            return None

        costs = CostModel.calculate(self.cost_profile, "SELL" if pos.side == "LONG" else "BUY", exit_price, pos.quantity)
        self.total_fees += costs.total

        gross_pnl = (exit_price - pos.entry_price) * pos.quantity if pos.side == "LONG" else (pos.entry_price - exit_price) * pos.quantity
        net_pnl = gross_pnl - costs.total

        # Return capital + net PnL back to cash
        returned_capital = (pos.entry_price * pos.quantity) + gross_pnl - costs.total
        self.cash += returned_capital
        self.realized_pnl += net_pnl

        closed = ClosedTrade(
            instrument_id=instrument_id,
            symbol=pos.symbol,
            side=pos.side,
            quantity=pos.quantity,
            entry_price=pos.entry_price,
            exit_price=exit_price,
            entry_time_utc=pos.entry_timestamp_utc,
            exit_time_utc=timestamp_utc,
            gross_pnl=round(gross_pnl, 2),
            net_pnl=round(net_pnl, 2),
            total_fees=round(costs.total, 2),
            exit_reason=reason,
        )
        self.closed_trades.append(closed)
        return closed

    def mark_to_market(self, prices: Dict[str, float]) -> None:
        """Update unrealized PnL based on latest market prices."""
        for inst_id, pos in self.positions.items():
            if inst_id in prices:
                cur = prices[inst_id]
                pos.current_price = cur
                if pos.side == "LONG":
                    pos.unrealized_pnl = (cur - pos.entry_price) * pos.quantity
                else:
                    pos.unrealized_pnl = (pos.entry_price - cur) * pos.quantity
