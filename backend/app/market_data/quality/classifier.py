"""STRATLAB Market Data Quality: Synthetic Order Flow Classifier.

Implements:
1. Quote Matching (Level B): Evaluates trades against Top-of-Book quotes.
2. Lee-Ready Tick Rule (Level C): Infers direction from tick price changes.
3. Bulk Volume Classification (Level D): Decomposes aggregated OHLCV candles
   into estimated aggressive buy/sell volume using normal distribution mapping.
"""

import math
from typing import Optional, Tuple

from shared.schemas.market_data import Candle
from shared.schemas.provenance import AggressorSide, DataQuality, ProvenanceMetadata, SideMethod


class SyntheticClassifier:
    """
    Evaluates order aggressor direction and data quality provenance.
    """
    def __init__(self):
        # State tracking for Lee-Ready tick rule per instrument
        self._last_price: dict[str, float] = {}
        self._last_direction: dict[str, AggressorSide] = {}

    def classify_tick(
        self,
        instrument_id: str,
        price: float,
        bid: Optional[float] = None,
        ask: Optional[float] = None,
        source_id: str = "TICK_FEED",
    ) -> Tuple[AggressorSide, ProvenanceMetadata]:
        """
        Classify individual trade into buy/sell aggressor side.
        Prioritizes Level B Quote Match when valid BBO is present,
        falling back to Level C Lee-Ready Tick Rule.
        """
        # 1. Level B: Contemporaneous Quote Match
        if bid is not None and ask is not None and ask > bid:
            mid = (bid + ask) / 2.0
            if price >= ask:
                side = AggressorSide.BUY
                conf = 0.95
            elif price <= bid:
                side = AggressorSide.SELL
                conf = 0.95
            elif price > mid:
                side = AggressorSide.BUY
                conf = 0.75
            elif price < mid:
                side = AggressorSide.SELL
                conf = 0.75
            else:
                # Exactly at midpoint: use tick rule fallback
                side = self._apply_tick_rule(instrument_id, price)
                conf = 0.60

            self._last_price[instrument_id] = price
            self._last_direction[instrument_id] = side
            return side, ProvenanceMetadata.quote_classified(source_id=source_id, confidence=conf)

        # 2. Level C: Lee-Ready Tick Rule
        side = self._apply_tick_rule(instrument_id, price)
        self._last_price[instrument_id] = price
        self._last_direction[instrument_id] = side
        conf = 0.65 if side != AggressorSide.UNKNOWN else 0.40
        return side, ProvenanceMetadata.tick_rule_estimated(source_id=source_id, confidence=conf)

    def _apply_tick_rule(self, instrument_id: str, price: float) -> AggressorSide:
        """
        Standard Lee-Ready (1991) tick rule:
        - Price > Price[-1] -> Uptick (BUY)
        - Price < Price[-1] -> Downtick (SELL)
        - Price == Price[-1] -> Zero tick: inherit previous non-zero direction
        """
        last_p = self._last_price.get(instrument_id)
        if last_p is None:
            return AggressorSide.UNKNOWN
        if price > last_p:
            return AggressorSide.BUY
        elif price < last_p:
            return AggressorSide.SELL
        else:
            return self._last_direction.get(instrument_id, AggressorSide.UNKNOWN)

    @staticmethod
    def decompose_candle_bvc(candle: Candle) -> Tuple[int, int]:
        """
        Bulk Volume Classification (BVC) algorithm (Easley, López de Prado, O'Hara):
        Maps normalized bar price progress ((Close - Open) / (High - Low)) to cumulative
        standard normal distribution to split aggregate volume into estimated Buy & Sell.

        Returns: (estimated_buy_volume, estimated_sell_volume)
        """
        total_vol = candle.volume
        if total_vol <= 0:
            return 0, 0

        bar_range = candle.high - candle.low
        if bar_range <= 0.0:
            # Flat bar (circuit locked or zero range) -> split 50/50
            half = total_vol // 2
            return half, total_vol - half

        # Normalized price delta in [-1.0, 1.0]
        # Standard deviation scaling: approximately 0.5 * range
        z = (candle.close - candle.open) / (bar_range * 0.5)

        # Cumulative normal distribution approximation via math.erf:
        # Phi(z) = 0.5 * (1 + erf(z / sqrt(2)))
        phi = 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))
        # Clamp to [0.05, 0.95] to prevent unrealistic 100% one-sided volume on normal bars
        phi = max(0.05, min(0.95, phi))

        buy_vol = int(round(total_vol * phi))
        buy_vol = max(0, min(total_vol, buy_vol))
        sell_vol = total_vol - buy_vol
        return buy_vol, sell_vol
