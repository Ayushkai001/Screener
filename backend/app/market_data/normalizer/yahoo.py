"""STRATLAB Normalizer: Yahoo Finance Daily/Intraday Bars to Normalized Candle.

Converts Yahoo chart JSON payloads into standard Candle entities tagged
with Level D OHLCV Proxy provenance (as Yahoo provides no order book aggressor flags).
"""

from datetime import datetime, timezone
from typing import Any, Dict, List

from shared.schemas.market_data import Candle
from shared.schemas.provenance import ProvenanceMetadata


def normalize_yahoo_bars(
    chart_payload: Dict[str, Any],
    instrument_id: str,
    timeframe: str = "1d",
) -> List[Candle]:
    """
    Parse standard Yahoo Finance chart JSON structure into Candle list.
    """
    try:
        result = chart_payload["chart"]["result"][0]
        timestamps = result.get("timestamp") or []
        quote = result["indicators"]["quote"][0]
        opens = quote.get("open") or []
        highs = quote.get("high") or []
        lows = quote.get("low") or []
        closes = quote.get("close") or []
        volumes = quote.get("volume") or []
    except (KeyError, IndexError, TypeError):
        return []

    prov = ProvenanceMetadata.ohlcv_proxy(source_id="YAHOO_FINANCE", confidence=0.40)
    candles = []

    for ts, o, h, l, c, v in zip(timestamps, opens, highs, lows, closes, volumes):
        if None in (ts, o, h, l, c, v):
            continue
        try:
            o_f, h_f, l_f, c_f = float(o), float(h), float(l), float(c)
            v_i = int(v)
            if o_f <= 0 or h_f <= 0 or l_f <= 0 or c_f <= 0:
                continue

            h_clean = max(h_f, o_f, c_f)
            l_clean = min(l_f, o_f, c_f)
            ts_ms = int(ts * 1000)

            candles.append(Candle(
                instrument_id=instrument_id,
                timestamp_utc=ts_ms,
                timeframe=timeframe,
                open=o_f,
                high=h_clean,
                low=l_clean,
                close=c_f,
                volume=max(0, v_i),
                turnover=round(c_f * max(0, v_i), 2),
                provenance=prov,
            ))
        except (ValueError, TypeError):
            continue

    return candles
