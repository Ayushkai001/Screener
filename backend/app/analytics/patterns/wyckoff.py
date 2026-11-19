"""STRATLAB Pattern Analytics: Wyckoff Methodology Engine.

Implements structural Wyckoff phases and events:
- Trading Range (TR) determination (Support & Resistance)
- Spring (Phase C shakeout below support with prompt reclaim)
- Upthrust (UT / UTAD false breakout above resistance)
- Sign of Strength (SOS breakout on volume)
- Sign of Weakness (SOW breakdown on volume)
"""

from enum import Enum
from typing import Dict, List, Optional
from pydantic import BaseModel, Field

from shared.schemas.market_data import Candle


class WyckoffEvent(str, Enum):
    SPRING = "SPRING"                       # Bullish shakeout below support
    UPTHRUST = "UPTHRUST"                   # Bearish bull trap above resistance
    SIGN_OF_STRENGTH = "SOS"                # Bullish high-volume expansion
    SIGN_OF_WEAKNESS = "SOW"                # Bearish high-volume expansion
    NONE = "NONE"


class WyckoffAnalysis(BaseModel):
    range_high: float
    range_low: float
    active_event: WyckoffEvent = WyckoffEvent.NONE
    is_spring: bool = False
    is_upthrust: bool = False
    is_sign_of_strength: bool = False
    is_sign_of_weakness: bool = False
    volume_expansion_ratio: float = 1.0


class WyckoffEngine:
    """
    Evaluates trading range consolidation and Wyckoff manipulation events.
    """

    @classmethod
    def analyze(
        cls,
        candles: List[Candle],
        range_lookback: int = 20,
    ) -> WyckoffAnalysis:
        if len(candles) < 5:
            return WyckoffAnalysis(range_high=0.0, range_low=0.0)

        # Baseline trading range from prior bars (excluding the trigger candle)
        prior = candles[-range_lookback:-1] if len(candles) > range_lookback else candles[:-1]
        range_high = max(c.high for c in prior)
        range_low = min(c.low for c in prior)

        last = candles[-1]
        prev = candles[-2] if len(candles) >= 2 else last

        # Average prior volume
        avg_vol = sum(c.volume for c in prior) / len(prior) if prior else 1.0
        vol_ratio = round(last.volume / max(avg_vol, 1.0), 2)

        is_spring = False
        is_ut = False
        is_sos = False
        is_sow = False
        event = WyckoffEvent.NONE

        # 1. Spring Test: Price dipped below range_low, but closed back above range_low
        if (last.low < range_low or prev.low < range_low) and last.close >= range_low:
            is_spring = True
            event = WyckoffEvent.SPRING

        # 2. Upthrust Test: Price spiked above range_high, but closed back below range_high
        elif (last.high > range_high or prev.high > range_high) and last.close <= range_high:
            is_ut = True
            event = WyckoffEvent.UPTHRUST

        # 3. Sign of Strength (SOS): Convincing breakout above range_high on expanding volume
        elif last.close > range_high and vol_ratio >= 1.2:
            is_sos = True
            event = WyckoffEvent.SIGN_OF_STRENGTH

        # 4. Sign of Weakness (SOW): Convincing breakdown below range_low on expanding volume
        elif last.close < range_low and vol_ratio >= 1.2:
            is_sow = True
            event = WyckoffEvent.SIGN_OF_WEAKNESS

        return WyckoffAnalysis(
            range_high=round(range_high, 4),
            range_low=round(range_low, 4),
            active_event=event,
            is_spring=is_spring,
            is_upthrust=is_ut,
            is_sign_of_strength=is_sos,
            is_sign_of_weakness=is_sow,
            volume_expansion_ratio=vol_ratio,
        )
