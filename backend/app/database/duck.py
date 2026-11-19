"""STRATLAB Storage Layer: DuckDB Columnar Query Engine.

Provides zero-copy, highly optimized analytical queries across partitioned
Parquet directories without requiring heavy pandas/numpy dependencies.
"""

import os
from typing import Any, Dict, List, Optional
import duckdb


class DuckDBEngine:
    """
    DuckDB SQL analytical execution engine over Parquet data lake.
    """
    def __init__(self, data_root: str = "data"):
        self.root = os.path.abspath(data_root)
        self.con = duckdb.connect(database=":memory:")

    def _to_dicts(self, rel: duckdb.DuckDBPyConnection) -> List[Dict[str, Any]]:
        """Convert DuckDB result set directly to list of dictionaries."""
        if not rel.description:
            return []
        cols = [desc[0] for desc in rel.description]
        return [dict(zip(cols, row)) for row in rel.fetchall()]

    def query_candles(
        self,
        exchange: str,
        symbol: str,
        timeframe: str,
        start_utc: Optional[int] = None,
        end_utc: Optional[int] = None,
        limit: int = 50000,
    ) -> List[Dict[str, Any]]:
        """
        Query candles across partition files with predicate pushdown.
        """
        pattern = os.path.join(
            self.root,
            "candles",
            f"exchange={exchange.upper()}",
            f"symbol={symbol.upper()}",
            f"timeframe={timeframe}",
            "*.parquet"
        )
        if not os.path.exists(os.path.dirname(pattern.replace("*.parquet", ""))):
            return []

        sql = ["SELECT * FROM read_parquet(?) WHERE 1=1"]
        params = [pattern]

        if start_utc is not None:
            sql.append("AND timestamp_utc >= ?")
            params.append(start_utc)
        if end_utc is not None:
            sql.append("AND timestamp_utc <= ?")
            params.append(end_utc)

        sql.append("ORDER BY timestamp_utc ASC LIMIT ?")
        params.append(limit)

        try:
            rel = self.con.execute(" ".join(sql), params)
            return self._to_dicts(rel)
        except duckdb.IOException:
            return []

    def query_volume_at_price(
        self,
        exchange: str,
        symbol: str,
        date_str: str,
        tick_size: float = 0.05,
    ) -> List[Dict[str, Any]]:
        """
        Aggregate millions of raw trade prints into volume-at-price bins in milliseconds.
        Returns: list of {"price_bin": float, "total_vol": int, "buy_vol": int, "sell_vol": int, "delta": int}
        """
        path = os.path.join(
            self.root,
            "trades",
            f"exchange={exchange.upper()}",
            f"symbol={symbol.upper()}",
            f"date={date_str}",
            "data.parquet"
        )
        if not os.path.exists(path):
            return []

        sql = """
        SELECT
            ROUND(price / ?, 0) * ? AS price_bin,
            CAST(SUM(quantity) AS BIGINT) AS total_vol,
            CAST(SUM(CASE WHEN aggressor = 'BUY' THEN quantity ELSE 0 END) AS BIGINT) AS buy_vol,
            CAST(SUM(CASE WHEN aggressor = 'SELL' THEN quantity ELSE 0 END) AS BIGINT) AS sell_vol,
            CAST(SUM(CASE WHEN aggressor = 'BUY' THEN quantity ELSE -quantity END) AS BIGINT) AS delta,
            CAST(COUNT(*) AS BIGINT) AS trade_count
        FROM read_parquet(?)
        GROUP BY price_bin
        ORDER BY price_bin ASC
        """
        try:
            rel = self.con.execute(sql, [tick_size, tick_size, path])
            return self._to_dicts(rel)
        except duckdb.IOException:
            return []

    def execute_raw(self, sql: str, params: Optional[List[Any]] = None) -> List[Dict[str, Any]]:
        """Execute arbitrary analytical query against the database."""
        rel = self.con.execute(sql, params or [])
        return self._to_dicts(rel)
