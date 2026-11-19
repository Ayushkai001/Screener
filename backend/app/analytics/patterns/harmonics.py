"""STRATLAB Pattern Analytics: Harmonic Geometric Pattern Engine.

Calculates 5-point XABCD Fibonacci harmonic formations:
- Gartley (B at 0.618 XA, D at 0.786 XA)
- Bat (B at 0.382 - 0.500 XA, D at 0.886 XA)
- Butterfly (B at 0.786 XA, D at 1.272 XA)
- Crab (B at 0.382 - 0.618 XA, D at 1.618 XA)
"""

from enum import Enum
from typing import Dict, List, Optional
from pydantic import BaseModel, Field

from shared.schemas.market_data import Candle


class HarmonicPatternType(str, Enum):
    GARTLEY = "GARTLEY"
    BAT = "BAT"
    BUTTERFLY = "BUTTERFLY"
    CRAB = "CRAB"
    NONE = "NONE"


class HarmonicMatch(BaseModel):
    pattern: HarmonicPatternType = HarmonicPatternType.NONE
    is_bullish: bool = False
    completion_price: float = 0.0
    ratios: Dict[str, float] = Field(default_factory=dict)
    description: str = ""


class HarmonicPatternEngine:
    """
    Evaluates pivot sequences to identify harmonic PRZ (Potential Reversal Zones).
    """

    @classmethod
    def detect(cls, candles: List[Candle], tolerance: float = 0.08) -> HarmonicMatch:
        if len(candles) < 20:
            return HarmonicMatch()

        # Find 5 recent alternating swing pivots
        pivots: List[Dict[str, float]] = []
        for i in range(2, len(candles) - 2):
            c_prev = candles[i - 1]
            c = candles[i]
            c_next = candles[i + 1]

            if c.high > c_prev.high and c.high > c_next.high:
                pivots.append({"type": 1, "price": c.high, "idx": i})
            elif c.low < c_prev.low and c.low < c_next.low:
                pivots.append({"type": -1, "price": c.low, "idx": i})

        if len(pivots) < 5:
            return HarmonicMatch()

        # Take last 5 pivots: X, A, B, C, D
        x, a, b, c, d = pivots[-5:]
        # Ensure alternating high/low
        if not (x["type"] != a["type"] != b["type"] != c["type"] != d["type"]):
            return HarmonicMatch()

        xa_len = abs(a["price"] - x["price"])
        if xa_len <= 0.0:
            return HarmonicMatch()

        # Ratios
        b_retrace = abs(b["price"] - a["price"]) / xa_len
        d_retrace = abs(d["price"] - x["price"]) / xa_len

        is_bullish = d["type"] == -1  # D is a low -> Bullish reversal expected

        ratios = {
            "B_retrace_XA": round(b_retrace, 3),
            "D_retrace_XA": round(d_retrace, 3),
        }

        # Gartley: B ~ 0.618 XA, D ~ 0.786 XA
        if abs(b_retrace - 0.618) <= tolerance and abs(d_retrace - 0.786) <= tolerance:
            return HarmonicMatch(
                pattern=HarmonicPatternType.GARTLEY,
                is_bullish=is_bullish,
                completion_price=d["price"],
                ratios=ratios,
                description=f"{'Bullish' if is_bullish else 'Bearish'} Gartley Pattern at {d['price']:.2f}",
            )

        # Bat: B ~ 0.382-0.500 XA, D ~ 0.886 XA
        if 0.382 - tolerance <= b_retrace <= 0.500 + tolerance and abs(d_retrace - 0.886) <= tolerance:
            return HarmonicMatch(
                pattern=HarmonicPatternType.BAT,
                is_bullish=is_bullish,
                completion_price=d["price"],
                ratios=ratios,
                description=f"{'Bullish' if is_bullish else 'Bearish'} Bat Pattern at {d['price']:.2f}",
            )

        # Butterfly: B ~ 0.786 XA, D ~ 1.272 XA
        if abs(b_retrace - 0.786) <= tolerance and abs(d_retrace - 1.272) <= tolerance:
            return HarmonicMatch(
                pattern=HarmonicPatternType.BUTTERFLY,
                is_bullish=is_bullish,
                completion_price=d["price"],
                ratios=ratios,
                description=f"{'Bullish' if is_bullish else 'Bearish'} Butterfly Pattern at {d['price']:.2f}",
            )

        return HarmonicMatch()
