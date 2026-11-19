"""STRATLAB Analytics: Smart Money Concepts (SMC) & Market Structure.

Algorithmic detection of:
- Swing High / Swing Low fractal pivots.
- Break of Structure (BOS: trend continuation).
- Change of Character (CHoCH: structural trend reversal).
- Fair Value Gaps (FVG: 3-candle imbalance voids).
- Liquidity Sweeps: Penetration of key levels with rejection close.
"""

from dataclasses import dataclass
from typing import List, Optional

from shared.schemas.market_data import Candle


@dataclass(slots=True)
class SwingPoint:
    index: int
    timestamp_utc: int
    price: float
    is_high: bool # True = Swing High, False = Swing Low


@dataclass(slots=True)
class FVG:
    index: int
    timestamp_utc: int
    top_price: float
    bottom_price: float
    is_bullish: bool # True = Bullish FVG, False = Bearish FVG


class SMCDetectionEngine:
    """
    Detects market structure shifts, liquidity sweeps, and price imbalances.
    """
    def __init__(self, swing_lookback: int = 3):
        self.swing_lookback = swing_lookback

    def find_swings(self, candles: List[Candle]) -> List[SwingPoint]:
        """Identify fractal swing highs and swing lows."""
        swings = []
        n = len(candles)
        k = self.swing_lookback

        if n < 2 * k + 1:
            return swings

        for i in range(k, n - k):
            c_high = candles[i].high
            c_low = candles[i].low

            # Swing High: candle high > k previous and k subsequent highs
            if all(c_high > candles[i - j].high for j in range(1, k + 1)) and \
               all(c_high >= candles[i + j].high for j in range(1, k + 1)):
                swings.append(SwingPoint(index=i, timestamp_utc=candles[i].timestamp_utc, price=c_high, is_high=True))

            # Swing Low: candle low < k previous and k subsequent lows
            if all(c_low < candles[i - j].low for j in range(1, k + 1)) and \
               all(c_low <= candles[i + j].low for j in range(1, k + 1)):
                swings.append(SwingPoint(index=i, timestamp_utc=candles[i].timestamp_utc, price=c_low, is_high=False))

        return swings

    def detect_structure_breaks(self, candles: List[Candle], swings: List[SwingPoint]) -> List[dict]:
        """
        Detect Break of Structure (BOS) and Change of Character (CHoCH).
        """
        breaks = []
        if not swings or len(candles) < 1:
            return breaks

        last_high = None
        last_low = None
        current_trend = "BULLISH"
        if len(swings) >= 2:
            current_trend = "BULLISH" if swings[-1].price > swings[0].price else "BEARISH"

        for s in swings:
            if s.is_high:
                last_high = s
            else:
                last_low = s

        # Evaluate most recent closed candle against key structure levels
        cur = candles[-1]
        if last_high and cur.close > last_high.price:
            kind = "BOS" if current_trend == "BULLISH" else "CHOCH"
            breaks.append({
                "type": kind,
                "direction": "BULLISH",
                "reference_price": last_high.price,
                "break_price": cur.close,
                "timestamp_utc": cur.timestamp_utc,
            })

        if last_low and cur.close < last_low.price:
            kind = "BOS" if current_trend == "BEARISH" else "CHOCH"
            breaks.append({
                "type": kind,
                "direction": "BEARISH",
                "reference_price": last_low.price,
                "break_price": cur.close,
                "timestamp_utc": cur.timestamp_utc,
            })

        return breaks

    @staticmethod
    def detect_fair_value_gaps(candles: List[Candle]) -> List[FVG]:
        """
        Identify 3-candle Fair Value Gaps (FVG):
        - Bullish FVG: Low[i] > High[i-2] (void between candle 1 high and candle 3 low)
        - Bearish FVG: High[i] < Low[i-2] (void between candle 1 low and candle 3 high)
        """
        fvgs = []
        if len(candles) < 3:
            return fvgs

        for i in range(2, len(candles)):
            c1 = candles[i - 2]
            c3 = candles[i]

            # Bullish FVG
            if c3.low > c1.high:
                fvgs.append(FVG(
                    index=i - 1,
                    timestamp_utc=candles[i - 1].timestamp_utc,
                    top_price=c3.low,
                    bottom_price=c1.high,
                    is_bullish=True,
                ))

            # Bearish FVG
            elif c3.high < c1.low:
                fvgs.append(FVG(
                    index=i - 1,
                    timestamp_utc=candles[i - 1].timestamp_utc,
                    top_price=c1.low,
                    bottom_price=c3.high,
                    is_bullish=False,
                ))

        return fvgs

    @staticmethod
    def detect_liquidity_sweep(candle: Candle, key_level: float, is_high_level: bool) -> bool:
        """
        Determine if candle swept a liquidity level:
        - High Level Sweep: Candle High > key_level, but Candle Close < key_level.
        - Low Level Sweep: Candle Low < key_level, but Candle Close > key_level.
        """
        if is_high_level:
            return candle.high > key_level and candle.close < key_level
        else:
            return candle.low < key_level and candle.close > key_level
