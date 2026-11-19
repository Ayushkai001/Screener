"""STRATLAB Normalizer: Generic Real-Time Broker Trade Packets to TradeTick.

Transforms raw trade packets from exchange/broker WebSockets into normalized
TradeTick entities, resolving timestamps and aggressor flags.
"""

import time
from typing import Any, Dict, Optional

from shared.schemas.market_data import TradeTick
from shared.schemas.provenance import AggressorSide, ProvenanceMetadata


def normalize_broker_tick(
    raw_packet: Dict[str, Any],
    instrument_id: str,
    provenance: Optional[ProvenanceMetadata] = None,
) -> Optional[TradeTick]:
    """
    Normalizes standard broker trade packet:
    Expected keys: 'price', 'quantity' (or 'volume'/'qty'), optional 'timestamp_ns' (or 'time'),
    optional 'aggressor' (BUY/SELL), 'bid', 'ask', 'sequence_id'.
    """
    try:
        price = float(raw_packet.get("price") or raw_packet.get("last_price") or 0.0)
        qty = int(raw_packet.get("quantity") or raw_packet.get("qty") or raw_packet.get("volume") or 0)
        if price <= 0.0 or qty <= 0:
            return None

        # Resolve timestamp to nanoseconds
        raw_ts = raw_packet.get("timestamp_ns") or raw_packet.get("timestamp") or raw_packet.get("time")
        if raw_ts is None:
            ts_ns = time.time_ns()
        elif raw_ts > 1e16: # Already nanoseconds
            ts_ns = int(raw_ts)
        elif raw_ts > 1e11: # Milliseconds
            ts_ns = int(raw_ts * 1_000_000)
        else: # Seconds
            ts_ns = int(raw_ts * 1_000_000_000)

        # Parse aggressor if explicitly provided
        raw_side = str(raw_packet.get("aggressor") or raw_packet.get("side") or "").upper()
        if raw_side in ("BUY", "B", "1"):
            aggressor = AggressorSide.BUY
        elif raw_side in ("SELL", "S", "-1"):
            aggressor = AggressorSide.SELL
        else:
            aggressor = AggressorSide.UNKNOWN

        bid = float(raw_packet["bid"]) if "bid" in raw_packet and raw_packet["bid"] is not None else None
        ask = float(raw_packet["ask"]) if "ask" in raw_packet and raw_packet["ask"] is not None else None
        seq = int(raw_packet["sequence_id"]) if "sequence_id" in raw_packet and raw_packet["sequence_id"] is not None else None

        # Sane bid/ask check
        if bid is not None and ask is not None and bid > ask:
            bid, ask = None, None

        prov = provenance or ProvenanceMetadata.exchange_verified(source_id="LIVE_STREAM")

        return TradeTick(
            instrument_id=instrument_id,
            timestamp_ns=ts_ns,
            price=price,
            quantity=qty,
            aggressor=aggressor,
            bid=bid,
            ask=ask,
            sequence_id=seq,
            provenance=prov,
        )
    except (ValueError, TypeError):
        return None
