"""STRATLAB Normalizer: Official NSE/BSE Bhavcopy to Normalized Candle.

Parses official exchange daily closing files into validated Candle models
with Level A Exchange-Verified provenance.
"""

from datetime import datetime, timezone
from typing import Any, Dict, Optional

from shared.schemas.market_data import Candle
from shared.schemas.provenance import ProvenanceMetadata


def normalize_nse_bhavcopy_row(row: Dict[str, Any], instrument_id: str) -> Optional[Candle]:
    """
    Transform raw NSE Bhavcopy CSV dictionary row into a Candle object.
    Expected keys: OPEN, HIGH, LOW, CLOSE, TOTTRDQTY, TOTTRDVAL, TIMESTAMP.
    """
    try:
        o = float(row["OPEN"])
        h = float(row["HIGH"])
        l = float(row["LOW"])
        c = float(row["CLOSE"])
        v = int(float(row["TOTTRDQTY"]))
        val = float(row.get("TOTTRDVAL", 0.0))

        # Parse date YYYY-MM-DD or DD-MMM-YYYY
        raw_date = str(row["TIMESTAMP"]).strip()
        try:
            dt = datetime.strptime(raw_date, "%d-%b-%Y").replace(tzinfo=timezone.utc)
        except ValueError:
            dt = datetime.fromisoformat(raw_date).replace(tzinfo=timezone.utc)

        ts_utc = int(dt.timestamp() * 1000)

        # Ensure High/Low envelope invariants defensively for zero-trade holiday edge cases
        h = max(h, o, c)
        l = min(l, o, c)

        return Candle(
            instrument_id=instrument_id,
            timestamp_utc=ts_utc,
            timeframe="1d",
            open=o,
            high=h,
            low=l,
            close=c,
            volume=v,
            turnover=val,
            provenance=ProvenanceMetadata.exchange_verified(source_id="NSE_BHAVCOPY"),
        )
    except (KeyError, ValueError, TypeError):
        return None
