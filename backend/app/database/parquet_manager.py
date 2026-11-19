"""STRATLAB Storage Layer: Parquet Partitioning & Persistence Manager.

Handles high-throughput columnar storage for Candlesticks, Raw Trades,
and Order Flow aggregations with Snappy compression and date-partitioned layouts.
"""

from datetime import datetime, timezone
import json
import os
from typing import List, Optional
import pyarrow as pa
import pyarrow.parquet as pq

from shared.schemas.market_data import Candle, TradeTick
from shared.schemas.order_flow import FootprintBar, PriceCluster
from shared.schemas.provenance import AggressorSide, DataQuality, ProvenanceMetadata, SideMethod


# PyArrow Columnar Schemas
CANDLE_SCHEMA = pa.schema([
    ("instrument_id", pa.string()),
    ("timestamp_utc", pa.int64()),
    ("timeframe", pa.string()),
    ("open", pa.float64()),
    ("high", pa.float64()),
    ("low", pa.float64()),
    ("close", pa.float64()),
    ("volume", pa.int64()),
    ("turnover", pa.float64()),
    # Provenance fields flattened
    ("quality", pa.int32()),
    ("side_method", pa.string()),
    ("source_id", pa.string()),
    ("confidence", pa.float64()),
    ("is_estimated", pa.bool_()),
])

TRADE_SCHEMA = pa.schema([
    ("instrument_id", pa.string()),
    ("timestamp_ns", pa.int64()),
    ("price", pa.float64()),
    ("quantity", pa.int64()),
    ("aggressor", pa.string()),
    ("bid", pa.float64()),
    ("ask", pa.float64()),
    ("sequence_id", pa.int64()),
    # Provenance
    ("quality", pa.int32()),
    ("side_method", pa.string()),
    ("source_id", pa.string()),
    ("confidence", pa.float64()),
    ("is_estimated", pa.bool_()),
])

FOOTPRINT_SCHEMA = pa.schema([
    ("instrument_id", pa.string()),
    ("timeframe", pa.string()),
    ("open_time_utc", pa.int64()),
    ("close_time_utc", pa.int64()),
    ("open", pa.float64()),
    ("high", pa.float64()),
    ("low", pa.float64()),
    ("close", pa.float64()),
    ("volume", pa.int64()),
    ("turnover", pa.float64()),
    ("delta", pa.int64()),
    ("cum_delta", pa.int64()),
    ("delta_min", pa.int64()),
    ("delta_max", pa.int64()),
    ("delta_finish", pa.float64()),
    ("poc_price", pa.float64()),
    ("vah", pa.float64()),
    ("val", pa.float64()),
    ("clusters_json", pa.string()), # Serialized price-clusters
    ("stacked_buy_imbalances", pa.list_(pa.float64())),
    ("stacked_sell_imbalances", pa.list_(pa.float64())),
    ("unfinished_high", pa.bool_()),
    ("unfinished_low", pa.bool_()),
    # Provenance
    ("quality", pa.int32()),
    ("side_method", pa.string()),
    ("source_id", pa.string()),
    ("confidence", pa.float64()),
    ("is_estimated", pa.bool_()),
])


class ParquetStorageManager:
    """
    Manages reading and writing partitioned Parquet market data files.
    """
    def __init__(self, root_dir: str = "data"):
        self.root = root_dir

    # ---------------------------------------------------------------- Path Builders
    def candle_partition_path(self, exchange: str, symbol: str, timeframe: str, year: int, month: int) -> str:
        return os.path.join(
            self.root,
            "candles",
            f"exchange={exchange.upper()}",
            f"symbol={symbol.upper()}",
            f"timeframe={timeframe}",
            f"{year}-{month:02d}.parquet"
        )

    def trade_partition_path(self, exchange: str, symbol: str, date_str: str) -> str:
        return os.path.join(
            self.root,
            "trades",
            f"exchange={exchange.upper()}",
            f"symbol={symbol.upper()}",
            f"date={date_str}",
            "data.parquet"
        )

    def footprint_partition_path(self, exchange: str, symbol: str, date_str: str) -> str:
        return os.path.join(
            self.root,
            "orderflow",
            f"exchange={exchange.upper()}",
            f"symbol={symbol.upper()}",
            f"date={date_str}",
            "footprint.parquet"
        )

    # ---------------------------------------------------------------- Candles
    def write_candles(self, exchange: str, symbol: str, candles: List[Candle]) -> List[str]:
        """
        Group candles by month and write them to partition files.
        """
        if not candles:
            return []
        
        # Partition by (timeframe, year, month)
        partitions = {}
        for c in candles:
            dt = datetime.fromtimestamp(c.timestamp_utc / 1000.0, tz=timezone.utc)
            key = (c.timeframe, dt.year, dt.month)
            partitions.setdefault(key, []).append(c)

        written_paths = []
        for (tf, yr, mo), part_candles in partitions.items():
            path = self.candle_partition_path(exchange, symbol, tf, yr, mo)
            os.makedirs(os.path.dirname(path), exist_ok=True)

            arrays = [
                pa.array([c.instrument_id for c in part_candles], pa.string()),
                pa.array([c.timestamp_utc for c in part_candles], pa.int64()),
                pa.array([c.timeframe for c in part_candles], pa.string()),
                pa.array([c.open for c in part_candles], pa.float64()),
                pa.array([c.high for c in part_candles], pa.float64()),
                pa.array([c.low for c in part_candles], pa.float64()),
                pa.array([c.close for c in part_candles], pa.float64()),
                pa.array([c.volume for c in part_candles], pa.int64()),
                pa.array([c.turnover for c in part_candles], pa.float64()),
                pa.array([c.provenance.quality.value for c in part_candles], pa.int32()),
                pa.array([c.provenance.side_method.value for c in part_candles], pa.string()),
                pa.array([c.provenance.source_id for c in part_candles], pa.string()),
                pa.array([c.provenance.confidence for c in part_candles], pa.float64()),
                pa.array([c.provenance.is_estimated for c in part_candles], pa.bool_()),
            ]
            table = pa.Table.from_arrays(arrays, schema=CANDLE_SCHEMA)
            pq.write_table(table, path, compression="snappy")
            written_paths.append(path)

        return written_paths

    def read_candles(self, exchange: str, symbol: str, timeframe: str, year: int, month: int) -> List[Candle]:
        path = self.candle_partition_path(exchange, symbol, timeframe, year, month)
        if not os.path.exists(path):
            return []
        table = pq.read_table(path)
        out = []
        for row in table.to_pylist():
            prov = ProvenanceMetadata(
                quality=DataQuality(row["quality"]),
                side_method=SideMethod(row["side_method"]),
                source_id=row["source_id"],
                confidence=row["confidence"],
                is_estimated=row["is_estimated"],
            )
            out.append(Candle(
                instrument_id=row["instrument_id"],
                timestamp_utc=row["timestamp_utc"],
                timeframe=row["timeframe"],
                open=row["open"],
                high=row["high"],
                low=row["low"],
                close=row["close"],
                volume=row["volume"],
                turnover=row["turnover"],
                provenance=prov,
            ))
        return out

    # ---------------------------------------------------------------- Trades
    def write_trades(self, exchange: str, symbol: str, date_str: str, trades: List[TradeTick]) -> str:
        if not trades:
            return ""
        path = self.trade_partition_path(exchange, symbol, date_str)
        os.makedirs(os.path.dirname(path), exist_ok=True)

        arrays = [
            pa.array([t.instrument_id for t in trades], pa.string()),
            pa.array([t.timestamp_ns for t in trades], pa.int64()),
            pa.array([t.price for t in trades], pa.float64()),
            pa.array([t.quantity for t in trades], pa.int64()),
            pa.array([t.aggressor.value for t in trades], pa.string()),
            pa.array([t.bid for t in trades], pa.float64()),
            pa.array([t.ask for t in trades], pa.float64()),
            pa.array([t.sequence_id for t in trades], pa.int64()),
            pa.array([t.provenance.quality.value for t in trades], pa.int32()),
            pa.array([t.provenance.side_method.value for t in trades], pa.string()),
            pa.array([t.provenance.source_id for t in trades], pa.string()),
            pa.array([t.provenance.confidence for t in trades], pa.float64()),
            pa.array([t.provenance.is_estimated for t in trades], pa.bool_()),
        ]
        table = pa.Table.from_arrays(arrays, schema=TRADE_SCHEMA)
        pq.write_table(table, path, compression="snappy")
        return path

    def read_trades(self, exchange: str, symbol: str, date_str: str) -> List[TradeTick]:
        path = self.trade_partition_path(exchange, symbol, date_str)
        if not os.path.exists(path):
            return []
        table = pq.read_table(path)
        out = []
        for row in table.to_pylist():
            prov = ProvenanceMetadata(
                quality=DataQuality(row["quality"]),
                side_method=SideMethod(row["side_method"]),
                source_id=row["source_id"],
                confidence=row["confidence"],
                is_estimated=row["is_estimated"],
            )
            out.append(TradeTick(
                instrument_id=row["instrument_id"],
                timestamp_ns=row["timestamp_ns"],
                price=row["price"],
                quantity=row["quantity"],
                aggressor=AggressorSide(row["aggressor"]),
                bid=row["bid"],
                ask=row["ask"],
                sequence_id=row["sequence_id"],
                provenance=prov,
            ))
        return out

    # ---------------------------------------------------------------- Footprint
    def write_footprint_bars(self, exchange: str, symbol: str, date_str: str, bars: List[FootprintBar]) -> str:
        if not bars:
            return ""
        path = self.footprint_partition_path(exchange, symbol, date_str)
        os.makedirs(os.path.dirname(path), exist_ok=True)

        clusters_json_list = [
            json.dumps({str(k): v.model_dump() for k, v in b.clusters.items()})
            for b in bars
        ]

        arrays = [
            pa.array([b.instrument_id for b in bars], pa.string()),
            pa.array([b.timeframe for b in bars], pa.string()),
            pa.array([b.open_time_utc for b in bars], pa.int64()),
            pa.array([b.close_time_utc for b in bars], pa.int64()),
            pa.array([b.open for b in bars], pa.float64()),
            pa.array([b.high for b in bars], pa.float64()),
            pa.array([b.low for b in bars], pa.float64()),
            pa.array([b.close for b in bars], pa.float64()),
            pa.array([b.volume for b in bars], pa.int64()),
            pa.array([b.turnover for b in bars], pa.float64()),
            pa.array([b.delta for b in bars], pa.int64()),
            pa.array([b.cum_delta for b in bars], pa.int64()),
            pa.array([b.delta_min for b in bars], pa.int64()),
            pa.array([b.delta_max for b in bars], pa.int64()),
            pa.array([b.delta_finish for b in bars], pa.float64()),
            pa.array([b.poc_price for b in bars], pa.float64()),
            pa.array([b.vah for b in bars], pa.float64()),
            pa.array([b.val for b in bars], pa.float64()),
            pa.array(clusters_json_list, pa.string()),
            pa.array([b.stacked_buy_imbalances for b in bars], pa.list_(pa.float64())),
            pa.array([b.stacked_sell_imbalances for b in bars], pa.list_(pa.float64())),
            pa.array([b.unfinished_high for b in bars], pa.bool_()),
            pa.array([b.unfinished_low for b in bars], pa.bool_()),
            pa.array([b.provenance.quality.value for b in bars], pa.int32()),
            pa.array([b.provenance.side_method.value for b in bars], pa.string()),
            pa.array([b.provenance.source_id for b in bars], pa.string()),
            pa.array([b.provenance.confidence for b in bars], pa.float64()),
            pa.array([b.provenance.is_estimated for b in bars], pa.bool_()),
        ]
        table = pa.Table.from_arrays(arrays, schema=FOOTPRINT_SCHEMA)
        pq.write_table(table, path, compression="snappy")
        return path

    def read_footprint_bars(self, exchange: str, symbol: str, date_str: str) -> List[FootprintBar]:
        path = self.footprint_partition_path(exchange, symbol, date_str)
        if not os.path.exists(path):
            return []
        table = pq.read_table(path)
        out = []
        for row in table.to_pylist():
            prov = ProvenanceMetadata(
                quality=DataQuality(row["quality"]),
                side_method=SideMethod(row["side_method"]),
                source_id=row["source_id"],
                confidence=row["confidence"],
                is_estimated=row["is_estimated"],
            )
            raw_clusters = json.loads(row["clusters_json"])
            clusters = {}
            for k, v in raw_clusters.items():
                c_prov = ProvenanceMetadata(**v["provenance"])
                clusters[float(k)] = PriceCluster(
                    price=v["price"],
                    bid_vol=v["bid_vol"],
                    ask_vol=v["ask_vol"],
                    total_vol=v["total_vol"],
                    delta=v["delta"],
                    trade_count=v["trade_count"],
                    imbalance_buy=v["imbalance_buy"],
                    imbalance_sell=v["imbalance_sell"],
                    is_poc=v["is_poc"],
                    provenance=c_prov,
                )
            out.append(FootprintBar(
                instrument_id=row["instrument_id"],
                timeframe=row["timeframe"],
                open_time_utc=row["open_time_utc"],
                close_time_utc=row["close_time_utc"],
                open=row["open"],
                high=row["high"],
                low=row["low"],
                close=row["close"],
                volume=row["volume"],
                turnover=row["turnover"],
                delta=row["delta"],
                cum_delta=row["cum_delta"],
                delta_min=row["delta_min"],
                delta_max=row["delta_max"],
                delta_finish=row["delta_finish"],
                clusters=clusters,
                poc_price=row["poc_price"],
                vah=row["vah"],
                val=row["val"],
                stacked_buy_imbalances=row["stacked_buy_imbalances"],
                stacked_sell_imbalances=row["stacked_sell_imbalances"],
                unfinished_high=row["unfinished_high"],
                unfinished_low=row["unfinished_low"],
                provenance=prov,
            ))
        return out
