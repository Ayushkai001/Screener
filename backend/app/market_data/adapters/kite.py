"""STRATLAB Market Data Adapter: Zerodha Kite Connect WebSocket Tick Stream.

Normalizes raw binary/dict tick packets from Zerodha Kite Connect (`kiteconnect.Ticker`)
into STRATLAB `TradeTick` and `OrderBookDepth` domain contracts with precise
data quality classification and provenance attribution.
"""

from datetime import datetime, timezone
import time
from typing import Any, Dict, List, Optional, Tuple

from shared.schemas.market_data import OrderBookDepth, TradeTick
from shared.schemas.provenance import AggressorSide, DataQuality, ProvenanceMetadata, SideMethod


class KiteTickAdapter:
    """
    Adapter for Zerodha Kite Connect WebSocket tick feeds.
    
    Kite ticks provide Level 2 market depth (5 bid / 5 ask levels) and last traded
    quantity, but lack explicit exchange aggressor flags. This adapter applies
    BBO Quote Matching (Level B, confidence 0.95) when depth is present, and falls
    back to the Lee-Ready tick rule (Level C, confidence 0.65) when trades occur
    inside the spread or when only LTP/quote mode is available.
    """

    def __init__(self, token_map: Optional[Dict[int, str]] = None):
        """
        Args:
            token_map: Dictionary mapping Kite instrument_token (int) to STRATLAB instrument_id (str).
                       e.g. {256265: "INS_INFY_NSE", 738561: "INS_RELIANCE_NSE"}
        """
        self._token_map: Dict[int, str] = dict(token_map or {})
        self._last_prices: Dict[str, float] = {}
        self._last_volumes: Dict[str, int] = {}

    def register_token(self, token: int, instrument_id: str) -> None:
        """Register or update an instrument token mapping."""
        self._token_map[token] = instrument_id

    def resolve_instrument_id(self, token: int) -> str:
        """Resolve Kite token to internal instrument ID."""
        return self._token_map.get(token, f"KITE_{token}")

    def normalize_tick(self, tick: Dict[str, Any]) -> Optional[Tuple[TradeTick, Optional[OrderBookDepth]]]:
        """
        Parses a single Kite tick dict into a (TradeTick, Optional[OrderBookDepth]) tuple.

        Handles:
        - Mode "full": LTP, last traded qty, cumulative volume, 5-level depth, timestamp
        - Mode "quote": LTP, last traded qty, cumulative volume, OHLC
        - Mode "ltp": LTP only
        """
        token = tick.get("instrument_token")
        if token is None:
            return None

        instrument_id = self.resolve_instrument_id(int(token))
        last_price = float(tick.get("last_price") or 0.0)
        if last_price <= 0.0:
            return None

        # Resolve timestamp to nanoseconds UTC
        raw_ts = tick.get("timestamp") or tick.get("last_trade_time")
        if isinstance(raw_ts, datetime):
            if raw_ts.tzinfo is None:
                ts_ns = int(raw_ts.replace(tzinfo=timezone.utc).timestamp() * 1_000_000_000)
            else:
                ts_ns = int(raw_ts.astimezone(timezone.utc).timestamp() * 1_000_000_000)
        elif isinstance(raw_ts, (int, float)):
            if raw_ts > 1e16:
                ts_ns = int(raw_ts)
            elif raw_ts > 1e11:
                ts_ns = int(raw_ts * 1_000_000)
            else:
                ts_ns = int(raw_ts * 1_000_000_000)
        else:
            ts_ns = time.time_ns()

        # Determine quantity
        qty = int(tick.get("last_traded_quantity") or 0)
        cum_vol = int(tick.get("volume_traded") or 0)

        prev_vol = self._last_volumes.get(instrument_id, 0)
        if qty <= 0 and cum_vol > prev_vol and prev_vol > 0:
            qty = cum_vol - prev_vol
        elif qty <= 0:
            qty = 1

        if cum_vol > 0:
            self._last_volumes[instrument_id] = cum_vol

        # Parse Depth (top of book BBO and full 5-level DOM if available)
        depth = tick.get("depth")
        best_bid: Optional[float] = None
        best_ask: Optional[float] = None
        ob_depth: Optional[OrderBookDepth] = None

        if isinstance(depth, dict):
            buy_depth = depth.get("buy", [])
            sell_depth = depth.get("sell", [])

            bids_list: List[Dict[str, Any]] = []
            asks_list: List[Dict[str, Any]] = []

            for b in buy_depth:
                p = float(b.get("price") or 0.0)
                q = int(b.get("quantity") or 0)
                if p > 0.0 and q > 0:
                    bids_list.append({"price": p, "quantity": q})

            for s in sell_depth:
                p = float(s.get("price") or 0.0)
                q = int(s.get("quantity") or 0)
                if p > 0.0 and q > 0:
                    asks_list.append({"price": p, "quantity": q})

            if bids_list:
                best_bid = bids_list[0]["price"]
            if asks_list:
                best_ask = asks_list[0]["price"]

            if bids_list or asks_list:
                ob_depth = OrderBookDepth(
                    instrument_id=instrument_id,
                    timestamp_ns=ts_ns,
                    bids=bids_list,
                    asks=asks_list,
                    provenance=ProvenanceMetadata.exchange_verified(source_id="ZERODHA_KITE"),
                )

        # Classify Aggressor Side and Provenance
        prev_price = self._last_prices.get(instrument_id, last_price)
        self._last_prices[instrument_id] = last_price

        # Check BBO Quote match first (Level B)
        if best_bid is not None and best_ask is not None and best_ask >= best_bid:
            if last_price >= best_ask:
                aggressor = AggressorSide.BUY
                provenance = ProvenanceMetadata.quote_classified(source_id="ZERODHA_KITE", confidence=0.95)
            elif last_price <= best_bid:
                aggressor = AggressorSide.SELL
                provenance = ProvenanceMetadata.quote_classified(source_id="ZERODHA_KITE", confidence=0.95)
            else:
                # Inside the spread: apply Lee-Ready tick rule (Level C)
                if last_price > prev_price:
                    aggressor = AggressorSide.BUY
                elif last_price < prev_price:
                    aggressor = AggressorSide.SELL
                else:
                    aggressor = AggressorSide.UNKNOWN
                provenance = ProvenanceMetadata.tick_rule_estimated(source_id="ZERODHA_KITE", confidence=0.65)
        else:
            # Depth absent: pure tick rule
            if last_price > prev_price:
                aggressor = AggressorSide.BUY
            elif last_price < prev_price:
                aggressor = AggressorSide.SELL
            else:
                aggressor = AggressorSide.UNKNOWN
            provenance = ProvenanceMetadata.tick_rule_estimated(source_id="ZERODHA_KITE", confidence=0.65)

        trade_tick = TradeTick(
            instrument_id=instrument_id,
            timestamp_ns=ts_ns,
            price=last_price,
            quantity=qty,
            aggressor=aggressor,
            bid=best_bid,
            ask=best_ask,
            sequence_id=None,
            provenance=provenance,
        )

        return trade_tick, ob_depth
