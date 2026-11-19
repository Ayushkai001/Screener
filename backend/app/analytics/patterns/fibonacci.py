"""STRATLAB Pattern Analytics: Dynamic Fibonacci Retracement & Extension Engine.

Calculates key Fibonacci ratios based on the most recent significant swing:
- Retracements: 0.236, 0.382, 0.500 (Equilibrium), 0.618 (Golden Ratio), 0.786 (Deep Retrace)
- Golden Pocket Zone: [0.618, 0.786]
- Extensions: 1.272, 1.618, 2.000, 2.618
"""

from typing import Dict, List, Optional
from pydantic import BaseModel, Field

from shared.schemas.market_data import Candle


class FibonacciLevels(BaseModel):
    swing_high: float
    swing_low: float
    is_bullish_impulse: bool  # True if measuring retrace of an upward impulse
    levels: Dict[str, float] = Field(default_factory=dict)
    in_golden_pocket: bool = False
    is_at_50_percent: bool = False
    is_at_618_level: bool = False
    distance_to_golden_pocket_pct: float = 0.0


class FibonacciEngine:
    """
    Computes dynamic Fibonacci retracements and golden pocket zones.
    """

    FIB_RATIOS = [0.236, 0.382, 0.500, 0.618, 0.786, 1.000, 1.272, 1.618, 2.000]

    @classmethod
    def calculate_levels(
        cls,
        candles: List[Candle],
        lookback: int = 50,
        current_price: Optional[float] = None,
    ) -> FibonacciLevels:
        """
        Extracts recent Swing High and Swing Low to build the dynamic Fibonacci ladder.
        """
        if not candles:
            return FibonacciLevels(swing_high=0.0, swing_low=0.0, is_bullish_impulse=True)

        subset = candles[-lookback:] if len(candles) > lookback else candles
        highest_candle = max(subset, key=lambda c: c.high)
        lowest_candle = min(subset, key=lambda c: c.low)

        high_val = highest_candle.high
        low_val = lowest_candle.low
        diff = high_val - low_val

        # Determine impulse direction:
        # If low happened before high -> Bullish impulse (measuring retrace down from high)
        # If high happened before low -> Bearish impulse (measuring retrace up from low)
        is_bullish = lowest_candle.timestamp_utc <= highest_candle.timestamp_utc

        levels: Dict[str, float] = {}
        if diff <= 0.0:
            return FibonacciLevels(swing_high=high_val, swing_low=low_val, is_bullish_impulse=is_bullish)

        if is_bullish:
            # Retracement down from high toward low
            for r in cls.FIB_RATIOS:
                if r <= 1.0:
                    # e.g. 0.618 level = High - 0.618 * diff
                    levels[f"retrace_{r}"] = round(high_val - r * diff, 4)
                else:
                    # Extensions above high
                    levels[f"ext_{r}"] = round(low_val + r * diff, 4)
        else:
            # Retracement up from low toward high
            for r in cls.FIB_RATIOS:
                if r <= 1.0:
                    levels[f"retrace_{r}"] = round(low_val + r * diff, 4)
                else:
                    levels[f"ext_{r}"] = round(high_val - r * diff, 4)

        # Check Golden Pocket: [0.618, 0.786]
        price = current_price if current_price is not None else candles[-1].close
        gp_top = max(levels.get("retrace_0.618", 0), levels.get("retrace_0.786", 0))
        gp_bottom = min(levels.get("retrace_0.618", 0), levels.get("retrace_0.786", 0))

        in_gp = False
        dist_gp = 0.0
        if gp_bottom > 0 and gp_top > 0:
            in_gp = (gp_bottom <= price <= gp_top) or (candles[-1].low <= gp_top and candles[-1].high >= gp_bottom)
            if price > gp_top:
                dist_gp = (price - gp_top) / gp_top * 100
            elif price < gp_bottom:
                dist_gp = (gp_bottom - price) / gp_bottom * 100

        fib_50 = levels.get("retrace_0.500", 0.0)
        fib_618 = levels.get("retrace_0.618", 0.0)
        at_50 = abs(price - fib_50) / max(price, 1) < 0.003
        at_618 = abs(price - fib_618) / max(price, 1) < 0.003

        return FibonacciLevels(
            swing_high=high_val,
            swing_low=low_val,
            is_bullish_impulse=is_bullish,
            levels=levels,
            in_golden_pocket=in_gp,
            is_at_50_percent=at_50,
            is_at_618_level=at_618,
            distance_to_golden_pocket_pct=round(dist_gp, 2),
        )
