"""STRATLAB Pattern Analytics: Candlestick Pattern Engine.

Detects single and multi-bar price action patterns:
- Hammer / Bullish Pin Bar
- Shooting Star / Bearish Pin Bar
- Bullish Engulfing
- Bearish Engulfing
- Morning Star
- Inside Bar
- Doji
"""

from enum import Enum
from typing import List, Optional
from pydantic import BaseModel

from shared.schemas.market_data import Candle


class CandlestickPattern(str, Enum):
    HAMMER_PIN_BAR = "HAMMER_PIN_BAR"
    SHOOTING_STAR = "SHOOTING_STAR"
    BULLISH_ENGULFING = "BULLISH_ENGULFING"
    BEARISH_ENGULFING = "BEARISH_ENGULFING"
    MORNING_STAR = "MORNING_STAR"
    INSIDE_BAR = "INSIDE_BAR"
    DOJI = "DOJI"
    NONE = "NONE"


class CandlestickMatch(BaseModel):
    pattern: CandlestickPattern = CandlestickPattern.NONE
    is_bullish: bool = False
    is_bearish: bool = False
    description: str = ""


class CandlestickPatternEngine:
    """
    Evaluates geometric proportions of candle bodies, wicks, and adjacent bars.
    """

    @classmethod
    def detect_latest(cls, candles: List[Candle]) -> CandlestickMatch:
        if not candles:
            return CandlestickMatch()

        curr = candles[-1]
        prev = candles[-2] if len(candles) >= 2 else None
        prev2 = candles[-3] if len(candles) >= 3 else None

        body = abs(curr.close - curr.open)
        rng = max(curr.high - curr.low, 0.0001)
        upper_wick = curr.high - max(curr.close, curr.open)
        lower_wick = min(curr.close, curr.open) - curr.low

        # 1. Hammer / Bullish Pin Bar (Lower wick >= 2 * body and small upper wick)
        if lower_wick >= 2.0 * max(body, 0.001) and upper_wick <= 0.25 * rng:
            return CandlestickMatch(
                pattern=CandlestickPattern.HAMMER_PIN_BAR,
                is_bullish=True,
                is_bearish=False,
                description="Bullish Hammer / Pin Bar with strong lower price rejection",
            )

        # 2. Shooting Star / Bearish Pin Bar (Upper wick >= 2 * body and small lower wick)
        if upper_wick >= 2.0 * max(body, 0.001) and lower_wick <= 0.25 * rng:
            return CandlestickMatch(
                pattern=CandlestickPattern.SHOOTING_STAR,
                is_bullish=False,
                is_bearish=True,
                description="Bearish Shooting Star with strong upper price rejection",
            )

        # 3. Doji (Body <= 5% of total range with wicks on both sides)
        if body / rng <= 0.05:
            return CandlestickMatch(
                pattern=CandlestickPattern.DOJI,
                is_bullish=False,
                is_bearish=False,
                description="Indecision Doji candle with tight body",
            )

        # 4. Multi-candle: Engulfing patterns
        if prev:
            prev_body = abs(prev.close - prev.open)
            # Bullish Engulfing: Prior candle red, current candle green, current body engulfs prior
            if (
                prev.close < prev.open
                and curr.close > curr.open
                and curr.open <= prev.close
                and curr.close >= prev.open
                and body > prev_body
            ):
                return CandlestickMatch(
                    pattern=CandlestickPattern.BULLISH_ENGULFING,
                    is_bullish=True,
                    is_bearish=False,
                    description="Bullish Engulfing candle completely overtaking prior red candle",
                )

            # Bearish Engulfing: Prior candle green, current candle red, current body engulfs prior
            if (
                prev.close > prev.open
                and curr.close < curr.open
                and curr.open >= prev.close
                and curr.close <= prev.open
                and body > prev_body
            ):
                return CandlestickMatch(
                    pattern=CandlestickPattern.BEARISH_ENGULFING,
                    is_bullish=False,
                    is_bearish=True,
                    description="Bearish Engulfing candle completely overtaking prior green candle",
                )

            # Inside Bar
            if curr.high < prev.high and curr.low > prev.low:
                return CandlestickMatch(
                    pattern=CandlestickPattern.INSIDE_BAR,
                    is_bullish=False,
                    is_bearish=False,
                    description="Inside Bar consolidating inside prior candle range",
                )

        # 5. Morning Star: prev2 is red, prev is small/doji, curr is strong green
        if prev and prev2:
            prev2_body = prev2.open - prev2.close
            curr_body = curr.close - curr.open
            if prev2.close < prev2.open and abs(prev.close - prev.open) / max(prev.high - prev.low, 0.001) < 0.3 and curr.close > curr.open and curr.close > (prev2.open + prev2.close) / 2.0:
                return CandlestickMatch(
                    pattern=CandlestickPattern.MORNING_STAR,
                    is_bullish=True,
                    is_bearish=False,
                    description="3-bar Bullish Morning Star reversal formation",
                )

        return CandlestickMatch()
