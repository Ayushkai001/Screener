"""STRATLAB Ingestion: Historical Bulk Ingestion Worker.

Validates and writes bulk historical candles into partitioned Parquet files,
generating dataset manifests for reproducible backtesting.
"""

import hashlib
from typing import Any, Dict, List, Optional

from backend.app.database.parquet_manager import ParquetStorageManager
from shared.schemas.market_data import Candle


class HistoricalIngestionWorker:
    """
    Ingests, validates, and partitions bulk historical candles.
    """
    def __init__(self, storage_manager: Optional[ParquetStorageManager] = None):
        self.storage = storage_manager or ParquetStorageManager()

    def ingest_candles(
        self,
        exchange: str,
        symbol: str,
        candles: List[Candle],
    ) -> Dict[str, Any]:
        """
        Validate, sort, and store candles into Parquet partitions.
        Returns dataset manifest metadata.
        """
        if not candles:
            return {"record_count": 0, "manifest_id": None}

        # Deduplicate and sort chronologically by timestamp
        seen_ts = set()
        clean_candles = []
        for c in sorted(candles, key=lambda x: x.timestamp_utc):
            if c.timestamp_utc not in seen_ts:
                seen_ts.add(c.timestamp_utc)
                clean_candles.append(c)

        paths = self.storage.write_candles(exchange, symbol, clean_candles)

        # Generate deterministic manifest checksum
        manifest_payload = f"{exchange}:{symbol}:{clean_candles[0].timestamp_utc}:{clean_candles[-1].timestamp_utc}:{len(clean_candles)}"
        manifest_id = hashlib.sha256(manifest_payload.encode()).hexdigest()[:16]

        primary_quality = clean_candles[0].provenance.quality.value
        timeframe = clean_candles[0].timeframe

        return {
            "dataset_manifest_id": f"MAN_{manifest_id}",
            "exchange": exchange.upper(),
            "symbol": symbol.upper(),
            "timeframe": timeframe,
            "start_utc": clean_candles[0].timestamp_utc,
            "end_utc": clean_candles[-1].timestamp_utc,
            "record_count": len(clean_candles),
            "data_quality": primary_quality,
            "files_written": paths,
        }
