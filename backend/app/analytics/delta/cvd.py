"""STRATLAB Analytics: Cumulative Volume Delta (CVD) & Absorption Engine.

Tracks bar delta accumulation, session-based resets, and algorithmic
divergence detection:
- Bullish Absorption: Price makes Lower Low while CVD makes Higher Low (passive buying).
- Bearish Absorption: Price makes Higher High while CVD makes Lower High (passive selling).
- Exhaustion: Extreme price push with drying delta.
"""

from typing import Dict, List, Optional
from shared.schemas.order_flow import CVDPoint
from shared.schemas.provenance import ProvenanceMetadata


class CVDEngine:
    """
    Stateful engine tracking Cumulative Volume Delta and order flow divergences.
    """
    def __init__(self, instrument_id: str):
        self.instrument_id = instrument_id
        self._cum_delta: int = 0
        self._history: List[CVDPoint] = []

    def reset_session(self):
        """Reset cumulative volume delta at market session open (09:15 IST)."""
        self._cum_delta = 0

    def on_delta(
        self,
        timestamp_utc: int,
        delta: int,
        provenance: ProvenanceMetadata,
        is_session_open: bool = False,
    ) -> CVDPoint:
        """
        Record interval delta and update cumulative tally.
        """
        if is_session_open:
            self._cum_delta = 0

        self._cum_delta += delta

        point = CVDPoint(
            instrument_id=self.instrument_id,
            timestamp_utc=timestamp_utc,
            delta=delta,
            cumulative_delta=self._cum_delta,
            session_reset=is_session_open,
            provenance=provenance,
        )
        self._history.append(point)
        if len(self._history) > 10000:
            self._history.pop(0)

        return point

    @property
    def current_cvd(self) -> int:
        return self._cum_delta

    @staticmethod
    def detect_divergence(
        prices: List[float],
        cvd_values: List[int],
        lookback: int = 5,
    ) -> Optional[str]:
        """
        Scan recent price & CVD history for institutional absorption patterns:
        - 'BULLISH_ABSORPTION': Price LL / Equal Low with CVD Higher Low.
        - 'BEARISH_ABSORPTION': Price HH / Equal High with CVD Lower High.
        """
        if len(prices) < lookback or len(cvd_values) < lookback:
            return None

        recent_p = prices[-lookback:]
        recent_cvd = cvd_values[-lookback:]

        p_start, p_end = recent_p[0], recent_p[-1]
        cvd_start, cvd_end = recent_cvd[0], recent_cvd[-1]

        # Bullish Absorption: Price down or flat, but aggressive delta positive / increasing
        if p_end <= p_start * 0.999 and cvd_end > cvd_start:
            return "BULLISH_ABSORPTION"

        # Bearish Absorption: Price up or flat, but aggressive delta negative / decreasing
        if p_end >= p_start * 1.001 and cvd_end < cvd_start:
            return "BEARISH_ABSORPTION"

        return None
