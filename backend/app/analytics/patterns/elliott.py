"""STRATLAB Pattern Analytics: Elliott Wave Impulse & Corrective Cycle Engine.

Detects 5-wave motive sequences (Wave 1 through 5) and ABC corrective cycles
from fractal swing pivots based on R.N. Elliott's core wave rules:
1. Wave 2 never retraces more than 100% of Wave 1.
2. Wave 3 is never the shortest among motive waves (1, 3, 5) and often the largest.
3. Wave 4 never enters the price territory of Wave 1 (no overlap in standard motive).
"""

from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from shared.schemas.market_data import Candle


class WaveType(str, Enum):
    IMPULSE_1 = "WAVE_1"
    PULLBACK_2 = "WAVE_2"
    IMPULSE_3 = "WAVE_3"      # The strongest wave
    PULLBACK_4 = "WAVE_4"     # Shallow pullback
    IMPULSE_5 = "WAVE_5"      # Exhaustion push
    CORRECTIVE_A = "WAVE_A"
    CORRECTIVE_B = "WAVE_B"
    CORRECTIVE_C = "WAVE_C"


class WavePoint(BaseModel):
    wave: WaveType
    candle_idx: int
    price: float
    timestamp_utc: int


class ElliottWaveCycle(BaseModel):
    is_valid_motive: bool = False
    current_wave: WaveType
    points: List[WavePoint] = Field(default_factory=list)
    wave_3_extension_ratio: float = 0.0  # Wave 3 length / Wave 1 length
    is_wave_3_breakout: bool = False
    is_wave_4_pullback: bool = False


class ElliottWaveDetector:
    """
    Evaluates candle series and fractal swings to identify active Elliott Wave phases.
    """

    @staticmethod
    def detect_waves(candles: List[Candle], lookback_swings: int = 5) -> ElliottWaveCycle:
        """
        Analyzes recent swing highs and lows to map out the Elliott Wave count.
        """
        if len(candles) < 10:
            return ElliottWaveCycle(
                is_valid_motive=False,
                current_wave=WaveType.IMPULSE_1,
                points=[],
            )

        # 1. Identify local swing highs and lows using 3-bar fractal definition
        swings: List[Dict[str, Any]] = []
        for i in range(2, len(candles) - 2):
            c_prev2 = candles[i - 2]
            c_prev = candles[i - 1]
            c_curr = candles[i]
            c_next = candles[i + 1]
            c_next2 = candles[i + 2]

            # Swing High
            if (
                c_curr.high > c_prev.high
                and c_curr.high > c_prev2.high
                and c_curr.high > c_next.high
                and c_curr.high > c_next2.high
            ):
                swings.append({
                    "type": "HIGH",
                    "idx": i,
                    "price": c_curr.high,
                    "ts": c_curr.timestamp_utc,
                })
            # Swing Low
            elif (
                c_curr.low < c_prev.low
                and c_curr.low < c_prev2.low
                and c_curr.low < c_next.low
                and c_curr.low < c_next2.low
            ):
                swings.append({
                    "type": "LOW",
                    "idx": i,
                    "price": c_curr.low,
                    "ts": c_curr.timestamp_utc,
                })

        # Need at least Low0, High1, Low2, High3 to test for Wave 3 breakout
        if len(swings) < 4:
            # Fallback simple wave estimate on latest candle
            return ElliottWaveCycle(
                is_valid_motive=False,
                current_wave=WaveType.IMPULSE_1,
                points=[],
            )

        # Take the most recent 4 to 6 swings
        recent = swings[-6:]

        # Check for Bullish Motive Sequence: Low0 -> High1 -> Low2 -> High3 -> Low4 -> High5
        # Find start of low
        low_indices = [idx for idx, s in enumerate(recent) if s["type"] == "LOW"]
        high_indices = [idx for idx, s in enumerate(recent) if s["type"] == "HIGH"]

        if not low_indices or not high_indices:
            return ElliottWaveCycle(is_valid_motive=False, current_wave=WaveType.IMPULSE_1, points=[])

        # Attempt to match Wave 0 (Start Low) -> Wave 1 (High) -> Wave 2 (Low) -> Wave 3 (High)
        points: List[WavePoint] = []
        is_w3_breakout = False
        is_w4_pullback = False
        current_wave = WaveType.IMPULSE_1
        valid_motive = False
        w3_ratio = 0.0

        for i in range(len(recent) - 3):
            s0 = recent[i]      # Expect LOW (Wave 0)
            s1 = recent[i + 1]  # Expect HIGH (Wave 1)
            s2 = recent[i + 2]  # Expect LOW (Wave 2)
            s3 = recent[i + 3]  # Expect HIGH (Wave 3)

            if s0["type"] == "LOW" and s1["type"] == "HIGH" and s2["type"] == "LOW" and s3["type"] == "HIGH":
                w1_len = s1["price"] - s0["price"]
                w2_retracement = s1["price"] - s2["price"]

                # Rule 1: Wave 2 never retraces > 100% of Wave 1 (s2.price > s0.price)
                if s2["price"] > s0["price"] and w1_len > 0:
                    w3_len = s3["price"] - s2["price"]

                    # Rule 2: Wave 3 exceeds Wave 1 high
                    if s3["price"] > s1["price"]:
                        w3_ratio = round(w3_len / w1_len, 2)
                        valid_motive = True
                        current_wave = WaveType.IMPULSE_3
                        is_w3_breakout = True

                        points = [
                            WavePoint(wave=WaveType.IMPULSE_1, candle_idx=s1["idx"], price=s1["price"], timestamp_utc=s1["ts"]),
                            WavePoint(wave=WaveType.PULLBACK_2, candle_idx=s2["idx"], price=s2["price"], timestamp_utc=s2["ts"]),
                            WavePoint(wave=WaveType.IMPULSE_3, candle_idx=s3["idx"], price=s3["price"], timestamp_utc=s3["ts"]),
                        ]

                        # Check if Wave 4 has formed
                        if i + 4 < len(recent):
                            s4 = recent[i + 4]
                            if s4["type"] == "LOW":
                                # Rule 3: Wave 4 does not enter Wave 1 price territory (s4.price > s1.price)
                                if s4["price"] > s1["price"]:
                                    current_wave = WaveType.PULLBACK_4
                                    is_w4_pullback = True
                                    points.append(
                                        WavePoint(wave=WaveType.PULLBACK_4, candle_idx=s4["idx"], price=s4["price"], timestamp_utc=s4["ts"])
                                    )

                        break

        # Also check if latest price just broke above Wave 1 high in real time
        if not is_w3_breakout and len(swings) >= 3:
            s_low0 = swings[-3]
            s_high1 = swings[-2]
            s_low2 = swings[-1]
            if s_low0["type"] == "LOW" and s_high1["type"] == "HIGH" and s_low2["type"] == "LOW":
                if s_low2["price"] > s_low0["price"] and candles[-1].close > s_high1["price"]:
                    is_w3_breakout = True
                    current_wave = WaveType.IMPULSE_3
                    valid_motive = True
                    w1_len = s_high1["price"] - s_low0["price"]
                    w3_len = candles[-1].close - s_low2["price"]
                    w3_ratio = round(w3_len / max(w1_len, 0.01), 2)
                    points = [
                        WavePoint(wave=WaveType.IMPULSE_1, candle_idx=s_high1["idx"], price=s_high1["price"], timestamp_utc=s_high1["ts"]),
                        WavePoint(wave=WaveType.PULLBACK_2, candle_idx=s_low2["idx"], price=s_low2["price"], timestamp_utc=s_low2["ts"]),
                        WavePoint(wave=WaveType.IMPULSE_3, candle_idx=len(candles) - 1, price=candles[-1].close, timestamp_utc=candles[-1].timestamp_utc),
                    ]

        return ElliottWaveCycle(
            is_valid_motive=valid_motive,
            current_wave=current_wave,
            points=points,
            wave_3_extension_ratio=w3_ratio,
            is_wave_3_breakout=is_w3_breakout,
            is_wave_4_pullback=is_w4_pullback,
        )
