"""STRATLAB Market Data Adapter: TrueData Real-Time Tick Feed.

Normalizes raw tick packets from TrueData Institutional WebSocket/TCP feeds
(NSE Equity, Futures & Options, MCX Commodities) into STRATLAB `TradeTick`
and `OrderBookDepth` domain contracts with exact data quality attribution.
"""

from datetime import datetime, timezone
import time
from typing import Any, Dict, List, Optional, Tuple

from shared.schemas.market_data import OrderBookDepth, TradeTick
from shared.schemas.provenance import AggressorSide, DataQuality, ProvenanceMetadata, SideMethod


class TrueDataTickAdapter:
    """
    Adapter for TrueData real-time tick-by-tick (TBT) and Level 2 feed streams.

    TrueData TBT provides exchange-verified buy/sell flags (Level A, confidence 1.0).
    When connecting to TrueData Level 1/quote streams, it falls back to contemporaneous
    Quote Matching (Level B, confidence 0.95) and the Lee-Ready tick rule (Level C, 0.65).
    """

    def __init__(self, symbol_map: Optional[Dict[str, str]] = None):
        """
        Args:
            symbol_map: Dictionary mapping vendor symbol to STRATLAB instrument_id.
                        e.g. {"RELIANCE": "INS_NSE_RELIANCE", "NIFTY-I": "INS_NSE_NIFTY_FUT"}
        """
        self._symbol_map: Dict[str, str] = dict(symbol_map or {})
        self._last_prices: Dict[str, float] = {}

    def register_symbol(self, vendor_symbol: str, instrument_id: str) -> None:
        """Register or update a vendor symbol mapping."""
        self._symbol_map[vendor_symbol] = instrument_id

    def resolve_instrument_id(self, vendor_symbol: str) -> str:
        """Resolve vendor symbol to internal instrument ID."""
        return self._symbol_map.get(vendor_symbol, f"TRUEDATA_{vendor_symbol}")

    def normalize_tick(self, packet: Dict[str, Any]) -> Optional[Tuple[TradeTick, Optional[OrderBookDepth]]]:
        """
        Parses a single TrueData packet into a (TradeTick, Optional[OrderBookDepth]) tuple.

        Expected fields in packet:
        - 'symbol' or 'symbol_id' (str / int)
        - 'price' or 'ltp' (float)
        - 'size' or 'ltq' or 'volume' or 'qty' (int)
        - 'timestamp' or 'time' (str / int / float)
        - optional 'aggressor' or 'trade_type' ("B", "S", "BUY", "SELL")
        - optional 'bid' / 'ask' (float)
        - optional 'bid_size' / 'ask_size' (int)
        - optional 'seq_no' or 'sequence_id' (int)
        """
        raw_sym = str(packet.get("symbol") or packet.get("symbol_id") or "")
        if not raw_sym:
            return None

        instrument_id = self.resolve_instrument_id(raw_sym)
        price = float(packet.get("price") or packet.get("ltp") or 0.0)
        if price <= 0.0:
            return None

        qty = int(packet.get("size") or packet.get("ltq") or packet.get("quantity") or packet.get("qty") or 0)
        if qty <= 0:
            qty = 1

        # Resolve timestamp to nanoseconds UTC
        raw_ts = packet.get("timestamp") or packet.get("time") or packet.get("timestamp_ns")
        ts_ns = self._parse_timestamp_to_ns(raw_ts)

        # Sequence identifier
        seq_id = packet.get("seq_no") or packet.get("sequence_id")
        seq = int(seq_id) if seq_id is not None else None

        # Best Bid and Ask
        bid = float(packet["bid"]) if "bid" in packet and packet["bid"] is not None else None
        ask = float(packet["ask"]) if "ask" in packet and packet["ask"] is not None else None
        if bid is not None and ask is not None and bid > ask:
            bid, ask = None, None  # Sanitize inverted spread

        # Classify Aggressor and Provenance
        raw_aggr = str(packet.get("aggressor") or packet.get("trade_type") or packet.get("side") or "").upper().strip()
        prev_price = self._last_prices.get(instrument_id, price)
        self._last_prices[instrument_id] = price

        # Case 1: Level A Exchange Verified (TBT Feed flag)
        if raw_aggr in ("B", "BUY", "1"):
            aggressor = AggressorSide.BUY
            provenance = ProvenanceMetadata.exchange_verified(source_id="TRUEDATA_TBT")
        elif raw_aggr in ("S", "SELL", "-1"):
            aggressor = AggressorSide.SELL
            provenance = ProvenanceMetadata.exchange_verified(source_id="TRUEDATA_TBT")
        # Case 2: Level B Quote Match against contemporaneous BBO
        elif bid is not None and ask is not None and ask >= bid:
            if price >= ask:
                aggressor = AggressorSide.BUY
                provenance = ProvenanceMetadata.quote_classified(source_id="TRUEDATA_BBO", confidence=0.95)
            elif price <= bid:
                aggressor = AggressorSide.SELL
                provenance = ProvenanceMetadata.quote_classified(source_id="TRUEDATA_BBO", confidence=0.95)
            else:
                # Inside spread: fallback to Lee-Ready tick rule
                if price > prev_price:
                    aggressor = AggressorSide.BUY
                elif price < prev_price:
                    aggressor = AggressorSide.SELL
                else:
                    aggressor = AggressorSide.UNKNOWN
                provenance = ProvenanceMetadata.tick_rule_estimated(source_id="TRUEDATA_REALTIME", confidence=0.65)
        # Case 3: Level C Tick Rule (Lee-Ready)
        else:
            if price > prev_price:
                aggressor = AggressorSide.BUY
            elif price < prev_price:
                aggressor = AggressorSide.SELL
            else:
                aggressor = AggressorSide.UNKNOWN
            provenance = ProvenanceMetadata.tick_rule_estimated(source_id="TRUEDATA_REALTIME", confidence=0.65)

        trade_tick = TradeTick(
            instrument_id=instrument_id,
            timestamp_ns=ts_ns,
            price=price,
            quantity=qty,
            aggressor=aggressor,
            bid=bid,
            ask=ask,
            sequence_id=seq,
            provenance=provenance,
        )

        # Optional Top-of-Book depth construct if sizes provided
        ob_depth: Optional[OrderBookDepth] = None
        bid_size = int(packet.get("bid_size") or packet.get("bid_qty") or 0)
        ask_size = int(packet.get("ask_size") or packet.get("ask_qty") or 0)
        if bid is not None and ask is not None and bid_size > 0 and ask_size > 0:
            ob_depth = OrderBookDepth(
                instrument_id=instrument_id,
                timestamp_ns=ts_ns,
                bids=[{"price": bid, "quantity": bid_size}],
                asks=[{"price": ask, "quantity": ask_size}],
                sequence_id=seq,
                provenance=ProvenanceMetadata.exchange_verified(source_id="TRUEDATA_BBO"),
            )

        return trade_tick, ob_depth

    def _parse_timestamp_to_ns(self, raw_ts: Any) -> int:
        """Converts strings, datetimes, or numeric epochs to nanoseconds."""
        if raw_ts is None:
            return time.time_ns()
        if isinstance(raw_ts, datetime):
            if raw_ts.tzinfo is None:
                return int(raw_ts.replace(tzinfo=timezone.utc).timestamp() * 1_000_000_000)
            return int(raw_ts.astimezone(timezone.utc).timestamp() * 1_000_000_000)
        if isinstance(raw_ts, (int, float)):
            if raw_ts > 1e16:
                return int(raw_ts)
            if raw_ts > 1e11:
                return int(raw_ts * 1_000_000)
            return int(raw_ts * 1_000_000_000)
        if isinstance(raw_ts, str):
            try:
                clean_str = raw_ts.strip().replace(" ", "T")
                dt = datetime.fromisoformat(clean_str)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return int(dt.timestamp() * 1_000_000_000)
            except ValueError:
                return time.time_ns()
        return time.time_ns()
