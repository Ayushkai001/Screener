"""Plain Python Strategy API (Option 1 in Strategy Definitions).

Allows traders and quants to write trading strategies in simple, idiomatic Python
without needing Pine Script or JSON IR.

Example:
    from screener.strategy_api import BaseStrategy, Action, run_strategy

    class EmaCross(BaseStrategy):
        def on_bar(self, bar, position, indicators):
            ema9 = indicators.get("ema9")
            ema21 = indicators.get("ema21")
            if not ema9 or not ema21:
                return Action.HOLD

            if position.side == "flat":
                if ema9 > ema21:
                    return Action.BUY
                elif ema9 < ema21:
                    return Action.SHORT
            elif position.side == "long" and ema9 < ema21:
                return Action.SELL
            elif position.side == "short" and ema9 > ema21:
                return Action.COVER
            return Action.HOLD
"""

from __future__ import annotations

import math
from enum import Enum
from typing import Any, Callable, Dict, List, NamedTuple, Optional, Union


class Action(str, Enum):
    """Actions returned by on_bar(...)."""
    HOLD = "hold"
    BUY = "buy"       # Enter long or switch to long
    SELL = "sell"     # Exit long (close long position)
    SHORT = "short"   # Enter short or switch to short
    COVER = "cover"   # Exit short (close short position)


class PositionSide(str, Enum):
    FLAT = "flat"
    LONG = "long"
    SHORT = "short"


class Bar(NamedTuple):
    index: int
    date: str
    open: float
    high: float
    low: float
    close: float
    volume: float


class Position(NamedTuple):
    side: str              # "flat", "long", "short"
    entry_price: float     # 0.0 if flat
    entry_bar: int         # -1 if flat
    size: float            # shares / contracts
    bars_held: int         # 0 if flat
    unrealized_pnl: float  # profit in currency at current bar close


class BaseStrategy:
    """Base class for all plain Python trading strategies."""

    def on_start(self) -> None:
        """Called once before the backtest loop begins."""
        pass

    def on_bar(self, bar: Bar, position: Position, indicators: Dict[str, Any]) -> Union[Action, str]:
        """Called on every closed bar.
        
        Args:
            bar: The current OHLCV bar.
            position: Current active position state.
            indicators: Dict of computed indicator values up to this bar.

        Returns:
            Action (or string): Action.HOLD, Action.BUY, Action.SELL, Action.SHORT, Action.COVER.
        """
        return Action.HOLD

    def on_finish(self) -> None:
        """Called once after the backtest loop completes."""
        pass


def functional_strategy(fn: Callable[[Bar, Position, Dict[str, Any]], Union[Action, str]]) -> BaseStrategy:
    """Wraps a simple function into a BaseStrategy."""
    class _FuncStrategy(BaseStrategy):
        def on_bar(self, bar: Bar, position: Position, indicators: Dict[str, Any]) -> Union[Action, str]:
            return fn(bar, position, indicators)
    return _FuncStrategy()


def run_strategy(
    strategy: Union[BaseStrategy, Callable],
    bars: List[Dict[str, Any]],
    capital: float = 100000.0,
    stop_pct: Optional[float] = None,
    target_pct: Optional[float] = None,
    trail_pct: Optional[float] = None,
    fee_pct: float = 0.1,
    slippage_pct: float = 0.05,
    indicators_by_bar: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Execute a Python strategy bar-by-bar with realistic order fills, costs, and slippage.

    Args:
        strategy: A BaseStrategy instance or a callable with signature (bar, pos, indicators).
        bars: List of bar dicts or tuples [date, open, high, low, close, volume].
        capital: Initial capital amount.
        stop_pct: Optional fixed stop loss percentage (e.g. 3.0 for 3%).
        target_pct: Optional fixed take profit percentage (e.g. 6.0 for 6%).
        trail_pct: Optional trailing stop percentage.
        fee_pct: One-way fee percentage (e.g. 0.1%).
        slippage_pct: One-way slippage percentage on market orders.
        indicators_by_bar: Optional pre-calculated indicator dict per bar.

    Returns:
        Dict with portfolio stats, equity curve, trade log, and metrics.
    """
    if callable(strategy) and not isinstance(strategy, BaseStrategy):
        strat = functional_strategy(strategy)
    else:
        strat = strategy

    strat.on_start()

    # Normalize bars
    norm_bars: List[Bar] = []
    for i, b in enumerate(bars):
        if isinstance(b, dict):
            norm_bars.append(Bar(
                index=i,
                date=str(b.get("date", b.get("time", i))),
                open=float(b["open"]),
                high=float(b["high"]),
                low=float(b["low"]),
                close=float(b["close"]),
                volume=float(b.get("volume", 0.0)),
            ))
        elif isinstance(b, (list, tuple)):
            norm_bars.append(Bar(
                index=i,
                date=str(b[0]),
                open=float(b[1]),
                high=float(b[2]),
                low=float(b[3]),
                close=float(b[4]),
                volume=float(b[5]) if len(b) > 5 else 0.0,
            ))

    N = len(norm_bars)
    if N == 0:
        return {"trades": [], "equity": [], "capital": capital, "total_return_pct": 0.0}

    cash = float(capital)
    active_pos: Optional[Dict[str, Any]] = None  # None or dict
    trades: List[Dict[str, Any]] = []
    equity_curve: List[tuple[str, float]] = []

    pending_order: Optional[Dict[str, Any]] = None  # action to fill at next open

    cost_factor_buy = 1.0 + (fee_pct + slippage_pct) / 100.0
    cost_factor_sell = 1.0 - (fee_pct + slippage_pct) / 100.0

    for i, b in enumerate(norm_bars):
        # 1. Fill pending orders from previous bar at today's open
        if pending_order is not None:
            action = pending_order["action"]
            fill_price = b.open

            if action in (Action.SELL, "sell") and active_pos and active_pos["side"] == "long":
                # Close long
                proceeds = active_pos["shares"] * fill_price * cost_factor_sell
                pnl = proceeds - active_pos["cost_basis"]
                ret_pct = (fill_price / active_pos["entry_price"] - 1.0) * 100.0
                trades.append({
                    "side": "long",
                    "entry_date": active_pos["entry_date"],
                    "entry": active_pos["entry_price"],
                    "exit_date": b.date,
                    "exit": fill_price,
                    "shares": active_pos["shares"],
                    "pnl": pnl,
                    "pnl_pct": ret_pct,
                    "reason": pending_order.get("reason", "signal"),
                    "bars": i - active_pos["entry_bar"],
                })
                cash += proceeds
                active_pos = None

            elif action in (Action.COVER, "cover") and active_pos and active_pos["side"] == "short":
                # Close short
                cost_to_cover = active_pos["shares"] * fill_price * cost_factor_buy
                pnl = active_pos["cost_basis"] - cost_to_cover
                ret_pct = (1.0 - fill_price / active_pos["entry_price"]) * 100.0
                trades.append({
                    "side": "short",
                    "entry_date": active_pos["entry_date"],
                    "entry": active_pos["entry_price"],
                    "exit_date": b.date,
                    "exit": fill_price,
                    "shares": active_pos["shares"],
                    "pnl": pnl,
                    "pnl_pct": ret_pct,
                    "reason": pending_order.get("reason", "signal"),
                    "bars": i - active_pos["entry_bar"],
                })
                cash += active_pos["collateral"] + pnl
                active_pos = None

            if action in (Action.BUY, "buy") and active_pos is None:
                # Open long
                eff_px = fill_price * cost_factor_buy
                shares = math.floor(cash / eff_px)
                if shares > 0:
                    total_cost = shares * eff_px
                    cash -= total_cost
                    stop_px = fill_price * (1.0 - stop_pct / 100.0) if stop_pct else None
                    tgt_px = fill_price * (1.0 + target_pct / 100.0) if target_pct else None
                    active_pos = {
                        "side": "long",
                        "entry_date": b.date,
                        "entry_price": fill_price,
                        "entry_bar": i,
                        "shares": shares,
                        "cost_basis": total_cost,
                        "stop": stop_px,
                        "target": tgt_px,
                        "peak_px": b.high,
                    }

            elif action in (Action.SHORT, "short") and active_pos is None:
                # Open short
                eff_px = fill_price * cost_factor_sell
                shares = math.floor(cash / fill_price)
                if shares > 0:
                    collateral = shares * fill_price
                    cash -= collateral
                    stop_px = fill_price * (1.0 + stop_pct / 100.0) if stop_pct else None
                    tgt_px = fill_price * (1.0 - target_pct / 100.0) if target_pct else None
                    active_pos = {
                        "side": "short",
                        "entry_date": b.date,
                        "entry_price": fill_price,
                        "entry_bar": i,
                        "shares": shares,
                        "cost_basis": shares * fill_price * cost_factor_sell,
                        "collateral": collateral,
                        "stop": stop_px,
                        "target": tgt_px,
                        "trough_px": b.low,
                    }

            pending_order = None

        # 2. Check intraday stop / target / trail on active position
        if active_pos is not None:
            side = active_pos["side"]
            exit_px = None
            exit_reason = None

            if side == "long":
                # Trailing stop update
                if trail_pct:
                    if b.high > active_pos["peak_px"]:
                        active_pos["peak_px"] = b.high
                    trl_stop = active_pos["peak_px"] * (1.0 - trail_pct / 100.0)
                    if active_pos["stop"] is None or trl_stop > active_pos["stop"]:
                        active_pos["stop"] = trl_stop

                # Check stop loss
                if active_pos["stop"] is not None and b.low <= active_pos["stop"]:
                    exit_px = b.open if b.open <= active_pos["stop"] else active_pos["stop"]
                    exit_reason = "stop"
                # Check target
                elif active_pos["target"] is not None and b.high >= active_pos["target"]:
                    exit_px = b.open if b.open >= active_pos["target"] else active_pos["target"]
                    exit_reason = "target"

                if exit_px is not None:
                    proceeds = active_pos["shares"] * exit_px * cost_factor_sell
                    pnl = proceeds - active_pos["cost_basis"]
                    ret_pct = (exit_px / active_pos["entry_price"] - 1.0) * 100.0
                    trades.append({
                        "side": "long",
                        "entry_date": active_pos["entry_date"],
                        "entry": active_pos["entry_price"],
                        "exit_date": b.date,
                        "exit": exit_px,
                        "shares": active_pos["shares"],
                        "pnl": pnl,
                        "pnl_pct": ret_pct,
                        "reason": exit_reason,
                        "bars": i - active_pos["entry_bar"],
                    })
                    cash += proceeds
                    active_pos = None

            elif side == "short":
                # Trailing stop update
                if trail_pct:
                    if b.low < active_pos["trough_px"]:
                        active_pos["trough_px"] = b.low
                    trl_stop = active_pos["trough_px"] * (1.0 + trail_pct / 100.0)
                    if active_pos["stop"] is None or trl_stop < active_pos["stop"]:
                        active_pos["stop"] = trl_stop

                # Check stop loss
                if active_pos["stop"] is not None and b.high >= active_pos["stop"]:
                    exit_px = b.open if b.open >= active_pos["stop"] else active_pos["stop"]
                    exit_reason = "stop"
                # Check target
                elif active_pos["target"] is not None and b.low <= active_pos["target"]:
                    exit_px = b.open if b.open <= active_pos["target"] else active_pos["target"]
                    exit_reason = "target"

                if exit_px is not None:
                    cost_to_cover = active_pos["shares"] * exit_px * cost_factor_buy
                    pnl = active_pos["cost_basis"] - cost_to_cover
                    ret_pct = (1.0 - exit_px / active_pos["entry_price"]) * 100.0
                    trades.append({
                        "side": "short",
                        "entry_date": active_pos["entry_date"],
                        "entry": active_pos["entry_price"],
                        "exit_date": b.date,
                        "exit": exit_px,
                        "shares": active_pos["shares"],
                        "pnl": pnl,
                        "pnl_pct": ret_pct,
                        "reason": exit_reason,
                        "bars": i - active_pos["entry_bar"],
                    })
                    cash += active_pos["collateral"] + pnl
                    active_pos = None

        # 3. Call strategy.on_bar with current Bar and Position
        if active_pos is None:
            cur_pos = Position(side="flat", entry_price=0.0, entry_bar=-1, size=0.0, bars_held=0, unrealized_pnl=0.0)
        else:
            if active_pos["side"] == "long":
                unrealized = active_pos["shares"] * (b.close - active_pos["entry_price"])
            else:
                unrealized = active_pos["shares"] * (active_pos["entry_price"] - b.close)
            cur_pos = Position(
                side=active_pos["side"],
                entry_price=active_pos["entry_price"],
                entry_bar=active_pos["entry_bar"],
                size=active_pos["shares"],
                bars_held=i - active_pos["entry_bar"],
                unrealized_pnl=unrealized,
            )

        ind_dict = indicators_by_bar[i] if indicators_by_bar and i < len(indicators_by_bar) else {}
        action = strat.on_bar(b, cur_pos, ind_dict)

        # Queue signal for next open
        if action in (Action.BUY, "buy") and cur_pos.side == "flat":
            pending_order = {"action": Action.BUY, "reason": "signal"}
        elif action in (Action.SHORT, "short") and cur_pos.side == "flat":
            pending_order = {"action": Action.SHORT, "reason": "signal"}
        elif action in (Action.SELL, "sell") and cur_pos.side == "long":
            pending_order = {"action": Action.SELL, "reason": "signal"}
        elif action in (Action.COVER, "cover") and cur_pos.side == "short":
            pending_order = {"action": Action.COVER, "reason": "signal"}

        # Record equity
        if active_pos is None:
            cur_equity = cash
        elif active_pos["side"] == "long":
            cur_equity = cash + active_pos["shares"] * b.close * cost_factor_sell
        else:
            pnl_now = active_pos["cost_basis"] - (active_pos["shares"] * b.close * cost_factor_buy)
            cur_equity = cash + active_pos["collateral"] + pnl_now
        equity_curve.append((b.date, cur_equity))

    strat.on_finish()

    # Performance calculations
    final_equity = equity_curve[-1][1] if equity_curve else capital
    total_ret = (final_equity / capital - 1.0) * 100.0

    # Max Drawdown
    peak = capital
    max_dd = 0.0
    for _, eq in equity_curve:
        if eq > peak:
            peak = eq
        dd = (peak - eq) / peak * 100.0 if peak > 0 else 0.0
        if dd > max_dd:
            max_dd = dd

    wins = [t for t in trades if t["pnl"] > 0]
    losses = [t for t in trades if t["pnl"] <= 0]
    win_rate = (len(wins) / len(trades) * 100.0) if trades else 0.0
    gross_profit = sum(t["pnl"] for t in wins)
    gross_loss = abs(sum(t["pnl"] for t in losses))
    profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else (99.0 if gross_profit > 0 else 0.0)

    return {
        "capital": capital,
        "final_equity": round(final_equity, 2),
        "total_return_pct": round(total_ret, 2),
        "max_drawdown_pct": round(max_dd, 2),
        "trades_count": len(trades),
        "win_rate_pct": round(win_rate, 1),
        "profit_factor": round(profit_factor, 2),
        "trades": trades,
        "equity_curve": equity_curve,
    }
