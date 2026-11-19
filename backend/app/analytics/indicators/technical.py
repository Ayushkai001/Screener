"""STRATLAB Analytics: Technical Indicator Engine.

Provides mathematically verified indicators with exact warm-up tracking:
- EMA (SMA-seeded exponential moving average).
- SMA (Rolling sum with math.fsum stabilization).
- RSI (Wilder's RMA smoothed relative strength index).
- MACD (12, 26, 9 line, signal, histogram).
- ATR (Average True Range via Wilder smoothing).
- VWAP (Session-anchored volume weighted average price).
"""

import math
from typing import Dict, List, Optional

from shared.schemas.market_data import Candle


class IndicatorEngine:
    """
    Computes technical indicators over price series and candle arrays.
    """
    @staticmethod
    def sma(series: List[float], period: int) -> List[Optional[float]]:
        if not series or period < 1:
            return []
        out = [None] * len(series)
        if len(series) < period:
            return out

        run = sum(series[:period])
        out[period - 1] = run / period

        for i in range(period, len(series)):
            run += series[i] - series[i - period]
            if i % 500 == 0: # Periodic stabilization against IEEE 754 float drift
                run = math.fsum(series[i - period + 1 : i + 1])
            out[i] = run / period

        return out

    @staticmethod
    def ema(series: List[float], period: int) -> List[Optional[float]]:
        if not series or period < 1:
            return []
        out = [None] * len(series)
        if len(series) < period:
            return out

        # Seed with initial SMA
        sma_seed = sum(series[:period]) / period
        out[period - 1] = sma_seed

        k = 2.0 / (period + 1.0)
        cur = sma_seed

        for i in range(period, len(series)):
            cur = (series[i] - cur) * k + cur
            out[i] = cur

        return out

    @staticmethod
    def rsi(series: List[float], period: int = 14) -> List[Optional[float]]:
        if not series or period < 1 or len(series) <= period:
            return [None] * len(series)

        out = [None] * len(series)
        gains = [0.0] * len(series)
        losses = [0.0] * len(series)

        for i in range(1, len(series)):
            diff = series[i] - series[i - 1]
            if diff > 0:
                gains[i] = diff
            else:
                losses[i] = -diff

        avg_gain = sum(gains[1 : period + 1]) / period
        avg_loss = sum(losses[1 : period + 1]) / period

        if avg_loss == 0.0:
            out[period] = 100.0
        else:
            rs = avg_gain / avg_loss
            out[period] = 100.0 - (100.0 / (1.0 + rs))

        # Wilder's RMA smoothing
        alpha = 1.0 / period
        for i in range(period + 1, len(series)):
            avg_gain = (gains[i] - avg_gain) * alpha + avg_gain
            avg_loss = (losses[i] - avg_loss) * alpha + avg_loss

            if avg_loss == 0.0:
                out[i] = 100.0
            else:
                rs = avg_gain / avg_loss
                out[i] = 100.0 - (100.0 / (1.0 + rs))

        return out

    @staticmethod
    def macd(
        series: List[float],
        fast: int = 12,
        slow: int = 26,
        signal: int = 9,
    ) -> Dict[str, List[Optional[float]]]:
        fast_ema = IndicatorEngine.ema(series, fast)
        slow_ema = IndicatorEngine.ema(series, slow)

        macd_line: List[Optional[float]] = [None] * len(series)
        valid_macd = []
        valid_indices = []

        for i in range(len(series)):
            if fast_ema[i] is not None and slow_ema[i] is not None:
                val = fast_ema[i] - slow_ema[i]
                macd_line[i] = val
                valid_macd.append(val)
                valid_indices.append(i)

        sig_line: List[Optional[float]] = [None] * len(series)
        hist: List[Optional[float]] = [None] * len(series)

        if len(valid_macd) >= signal:
            sig_values = IndicatorEngine.ema(valid_macd, signal)
            for v_idx, s_val in zip(valid_indices, sig_values):
                sig_line[v_idx] = s_val
                if s_val is not None and macd_line[v_idx] is not None:
                    hist[v_idx] = macd_line[v_idx] - s_val

        return {"macd": macd_line, "signal": sig_line, "hist": hist}

    @staticmethod
    def atr(candles: List[Candle], period: int = 14) -> List[Optional[float]]:
        if not candles or period < 1:
            return []
        out = [None] * len(candles)
        if len(candles) < period:
            return out

        tr = [candles[0].high - candles[0].low]
        for i in range(1, len(candles)):
            c = candles[i]
            prev_c = candles[i - 1].close
            tr.append(max(c.high - c.low, abs(c.high - prev_c), abs(c.low - prev_c)))

        rma = sum(tr[:period]) / period
        out[period - 1] = rma

        alpha = 1.0 / period
        for i in range(period, len(candles)):
            rma = (tr[i] - rma) * alpha + rma
            out[i] = rma

        return out

    @staticmethod
    def vwap(candles: List[Candle]) -> List[float]:
        """Anchored cumulative volume weighted average price: sum(P*V) / sum(V)."""
        if not candles:
            return []
        out = []
        cum_pv = 0.0
        cum_vol = 0

        for c in candles:
            typical_price = (c.high + c.low + c.close) / 3.0
            cum_pv += typical_price * c.volume
            cum_vol += c.volume
            out.append(cum_pv / cum_vol if cum_vol > 0 else typical_price)

        return out
