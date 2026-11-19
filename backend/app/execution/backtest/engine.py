"""STRATLAB Historical Backtest Simulation Engine.

Replays market events chronologically with zero look-ahead bias, evaluating
compiled Strategy IR logic, tracking equity curves, and computing key metrics.
"""

from __future__ import annotations
import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from shared.schemas.market_data import Candle
from backend.app.analytics.indicators.technical import IndicatorEngine
from backend.app.execution.portfolio.ledger import ClosedTrade, PortfolioLedger
from backend.app.strategy.compiler.compiler import (
    ActionKind,
    CompiledStrategy,
    EvaluationContext,
)


@dataclass
class BacktestMetrics:
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate_pct: float
    profit_factor: float
    net_pnl: float
    total_fees: float
    max_drawdown_pct: float
    sharpe_ratio: float
    final_equity: float


@dataclass
class BacktestResult:
    metrics: BacktestMetrics
    equity_curve: List[Dict[str, Any]]
    closed_trades: List[ClosedTrade]


class BacktestEngine:
    """
    Simulates strategy execution on historical bar data.
    """

    def __init__(self, ledger: Optional[PortfolioLedger] = None):
        self.ledger = ledger or PortfolioLedger()

    def run(self, strategy: CompiledStrategy, candles: List[Candle]) -> BacktestResult:
        """
        Executes historical backtest on ordered list of candles.
        """
        if not candles:
            empty_metrics = BacktestMetrics(0, 0, 0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, self.ledger.initial_cash)
            return BacktestResult(metrics=empty_metrics, equity_curve=[], closed_trades=[])

        ir = strategy.ir
        inst_id = candles[0].instrument_id
        symbol = candles[0].instrument_id

        # Precompute indicators specified in compiled strategy
        indicator_series: Dict[str, List[Optional[float]]] = {}
        closes = [c.close for c in candles]
        highs = [c.high for c in candles]
        lows = [c.low for c in candles]

        for ind_req in strategy.required_indicators:
            name = ind_req["name"]
            params = ind_req.get("params", {})
            if name == "ema":
                p = params.get("period", 20)
                indicator_series[f"ema_{p}"] = IndicatorEngine.ema(closes, p)
            elif name == "sma":
                p = params.get("period", 20)
                indicator_series[f"sma_{p}"] = IndicatorEngine.sma(closes, p)
            elif name == "rsi":
                p = params.get("period", 14)
                indicator_series[f"rsi_{p}"] = IndicatorEngine.rsi(closes, p)
            elif name == "atr":
                p = params.get("period", 14)
                indicator_series[f"atr_{p}"] = IndicatorEngine.atr(highs, lows, closes, p)

        equity_curve: List[Dict[str, Any]] = []
        peak_equity = self.ledger.initial_cash
        max_drawdown_pct = 0.0
        daily_returns: List[float] = []

        pending_entry: Optional[Dict[str, Any]] = None
        bars_held = 0

        # Bar-by-bar chronological execution
        for i in range(len(candles)):
            c = candles[i]
            prev_c = candles[i - 1] if i > 0 else None

            # 1. Process pending entry order on bar open if scheduled
            if pending_entry:
                entry_price = c.open
                stop_loss = pending_entry.get("stop_loss")
                take_profit = pending_entry.get("take_profit")
                qty = self.ledger.calculate_position_size(
                    price=entry_price,
                    stop_price=stop_loss,
                    risk_pct=ir.portfolio.risk_pct,
                )
                if qty > 0:
                    self.ledger.open_position(
                        instrument_id=inst_id,
                        symbol=symbol,
                        side="LONG",
                        price=entry_price,
                        quantity=qty,
                        timestamp_utc=c.timestamp_utc,
                        stop_loss=stop_loss,
                        take_profit=take_profit,
                    )
                pending_entry = None
                bars_held = 0

            # 2. Check position exits (Stop loss, Take profit, Trailing stop, Max hold)
            pos = self.ledger.positions.get(inst_id)
            if pos:
                bars_held += 1

                # Stop loss check
                if pos.stop_loss and c.low <= pos.stop_loss:
                    exit_p = min(c.open, pos.stop_loss)  # Handle gapping below stop
                    self.ledger.close_position(inst_id, exit_p, c.timestamp_utc, reason="STOP")
                    pos = None

                # Take profit check
                elif pos.take_profit and c.high >= pos.take_profit:
                    exit_p = max(c.open, pos.take_profit)
                    self.ledger.close_position(inst_id, exit_p, c.timestamp_utc, reason="TARGET")
                    pos = None

                # Trailing stop ratchet
                elif pos and ir.risk.trailing_stop.mode == "pct":
                    trail_pct = ir.risk.trailing_stop.trail_value or 2.0
                    new_trail = c.high * (1.0 - (trail_pct / 100.0))
                    if pos.trailing_stop is None or new_trail > pos.trailing_stop:
                        pos.trailing_stop = new_trail
                        if pos.stop_loss is None or pos.trailing_stop > pos.stop_loss:
                            pos.stop_loss = pos.trailing_stop

                # Max hold duration
                elif pos and ir.risk.max_hold_bars and bars_held >= ir.risk.max_hold_bars:
                    self.ledger.close_position(inst_id, c.close, c.timestamp_utc, reason="TIMEOUT")
                    pos = None

            # 3. Mark to market & record equity
            self.ledger.mark_to_market({inst_id: c.close})
            cur_equity = self.ledger.equity
            peak_equity = max(peak_equity, cur_equity)
            dd_pct = ((peak_equity - cur_equity) / peak_equity) * 100.0 if peak_equity > 0 else 0.0
            max_drawdown_pct = max(max_drawdown_pct, dd_pct)

            if equity_curve:
                prev_eq = equity_curve[-1]["equity"]
                daily_returns.append((cur_equity - prev_eq) / prev_eq if prev_eq > 0 else 0.0)

            equity_curve.append({
                "timestamp_utc": c.timestamp_utc,
                "equity": round(cur_equity, 2),
                "cash": round(self.ledger.cash, 2),
                "drawdown_pct": round(dd_pct, 2),
            })

            # 4. Evaluate Strategy Rules at Close
            current_inds = {k: indicator_series[k][i] for k in indicator_series if indicator_series[k][i] is not None}
            ctx = EvaluationContext(
                symbol=symbol,
                timestamp_utc=c.timestamp_utc,
                current_candle={"open": c.open, "high": c.high, "low": c.low, "close": c.close, "volume": c.volume},
                previous_candle={"open": prev_c.open, "high": prev_c.high, "low": prev_c.low, "close": prev_c.close, "volume": prev_c.volume} if prev_c else None,
                indicator_values=current_inds,
                active_position="LONG" if pos else None,
            )

            # Check rule-based exits
            if pos:
                exit_action = strategy.evaluate_exit(ctx)
                if exit_action == ActionKind.EXIT_LONG:
                    self.ledger.close_position(inst_id, c.close, c.timestamp_utc, reason="RULE")
                    pos = None

            # Check entry triggers if no position open
            if not pos and not pending_entry:
                entry_action = strategy.evaluate_entry(ctx)
                if entry_action == ActionKind.ENTER_LONG:
                    # Calculate stops and targets
                    stop_p = None
                    target_p = None
                    if ir.risk.stop_loss.mode == "pct":
                        stop_p = c.close * (1.0 - (ir.risk.stop_loss.value / 100.0))
                    elif ir.risk.stop_loss.mode == "atr" and "atr_14" in current_inds:
                        stop_p = c.close - (current_inds["atr_14"] * (ir.risk.stop_loss.value or 1.5))

                    if ir.risk.take_profit.mode == "pct":
                        target_p = c.close * (1.0 + (ir.risk.take_profit.value / 100.0))
                    elif ir.risk.take_profit.mode == "risk_reward" and stop_p is not None:
                        risk_dist = c.close - stop_p
                        target_p = c.close + (risk_dist * (ir.risk.take_profit.value or 2.0))

                    # Schedule execution for next open
                    pending_entry = {
                        "stop_loss": stop_p,
                        "take_profit": target_p,
                    }

        # Calculate summary metrics
        trades = self.ledger.closed_trades
        wins = [t for t in trades if t.net_pnl > 0]
        losses = [t for t in trades if t.net_pnl <= 0]
        total_win = sum(t.net_pnl for t in wins)
        total_loss = abs(sum(t.net_pnl for t in losses))
        profit_factor = round(total_win / total_loss, 2) if total_loss > 0 else (99.0 if total_win > 0 else 0.0)
        win_rate = round((len(wins) / len(trades)) * 100.0, 2) if trades else 0.0

        # Sharpe calculation
        mean_ret = (sum(daily_returns) / len(daily_returns)) if daily_returns else 0.0
        var_ret = (sum((r - mean_ret) ** 2 for r in daily_returns) / len(daily_returns)) if len(daily_returns) > 1 else 0.0
        std_ret = math.sqrt(var_ret) if var_ret > 0 else 0.0
        sharpe = round((mean_ret / std_ret) * math.sqrt(252), 2) if std_ret > 0 else 0.0

        metrics = BacktestMetrics(
            total_trades=len(trades),
            winning_trades=len(wins),
            losing_trades=len(losses),
            win_rate_pct=win_rate,
            profit_factor=profit_factor,
            net_pnl=round(self.ledger.realized_pnl, 2),
            total_fees=round(self.ledger.total_fees, 2),
            max_drawdown_pct=round(max_drawdown_pct, 2),
            sharpe_ratio=sharpe,
            final_equity=round(self.ledger.equity, 2),
        )

        return BacktestResult(
            metrics=metrics,
            equity_curve=equity_curve,
            closed_trades=trades,
        )
