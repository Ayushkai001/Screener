"""Unit and integration tests for STRATLAB Block 02: Storage Layer & Persistence.

Run: .venv/bin/python -m unittest tests/test_storage.py -v
"""

import os
import shutil
import tempfile
import unittest

from backend.app.database.duck import DuckDBEngine
from backend.app.database.parquet_manager import ParquetStorageManager
from backend.app.database.redis_client import RedisCoordinator
from shared.schemas.market_data import Candle, TradeTick
from shared.schemas.order_flow import FootprintBar, PriceCluster
from shared.schemas.provenance import AggressorSide, ProvenanceMetadata


class TestSQLMigration(unittest.TestCase):
    def test_schema_file_exists_and_contains_domains(self):
        sql_path = os.path.join("database", "migrations", "001_initial_schema.sql")
        self.assertTrue(os.path.exists(sql_path), "Migration file must exist.")
        with open(sql_path, "r", encoding="utf-8") as f:
            sql = f.read()

        expected_tables = [
            "instruments", "exchanges", "data_sources", "dataset_manifests",
            "strategies", "strategy_versions", "backtest_runs", "backtest_trades",
            "paper_accounts", "paper_positions", "paper_orders", "paper_fills",
            "users", "watchlists", "chart_layouts",
        ]
        for tbl in expected_tables:
            self.assertIn(f"CREATE TABLE {tbl}", sql, f"Table {tbl} must be defined in DDL.")


class TestParquetAndDuckDB(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.storage = ParquetStorageManager(root_dir=self.temp_dir)
        self.duck = DuckDBEngine(data_root=self.temp_dir)
        self.prov_real = ProvenanceMetadata.exchange_verified("NSE_TBT")

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_candle_partition_write_and_read(self):
        candles = [
            Candle(
                instrument_id="INS_NSE_RELIANCE",
                timestamp_utc=1794195900000, # 2026-11-09 09:15 UTC (approx)
                timeframe="5m",
                open=2500.0,
                high=2510.0,
                low=2495.0,
                close=2505.0,
                volume=10000,
                turnover=25050000.0,
                provenance=self.prov_real,
            ),
            Candle(
                instrument_id="INS_NSE_RELIANCE",
                timestamp_utc=1794196200000,
                timeframe="5m",
                open=2505.0,
                high=2515.0,
                low=2500.0,
                close=2512.0,
                volume=12000,
                turnover=30144000.0,
                provenance=self.prov_real,
            ),
        ]
        paths = self.storage.write_candles("NSE", "RELIANCE", candles)
        self.assertEqual(len(paths), 1)
        self.assertTrue(os.path.exists(paths[0]))

        # Read back via storage manager
        read_back = self.storage.read_candles("NSE", "RELIANCE", "5m", 2026, 11)
        self.assertEqual(len(read_back), 2)
        self.assertEqual(read_back[0].close, 2505.0)
        self.assertEqual(read_back[1].close, 2512.0)

        # Query via DuckDB
        results = self.duck.query_candles("NSE", "RELIANCE", "5m")
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0]["open"], 2500.0)
        self.assertEqual(results[1]["close"], 2512.0)

    def test_trade_write_and_duckdb_volume_profile(self):
        trades = [
            TradeTick(
                instrument_id="INS_NSE_RELIANCE",
                timestamp_ns=1794195900000000000,
                price=2500.0,
                quantity=100,
                aggressor=AggressorSide.BUY,
                provenance=self.prov_real,
            ),
            TradeTick(
                instrument_id="INS_NSE_RELIANCE",
                timestamp_ns=1794195900100000000,
                price=2500.0,
                quantity=200,
                aggressor=AggressorSide.SELL,
                provenance=self.prov_real,
            ),
            TradeTick(
                instrument_id="INS_NSE_RELIANCE",
                timestamp_ns=1794195900200000000,
                price=2500.05,
                quantity=500,
                aggressor=AggressorSide.BUY,
                provenance=self.prov_real,
            ),
        ]
        path = self.storage.write_trades("NSE", "RELIANCE", "2026-11-19", trades)
        self.assertTrue(os.path.exists(path))

        read_trades = self.storage.read_trades("NSE", "RELIANCE", "2026-11-19")
        self.assertEqual(len(read_trades), 3)

        # Execute high-speed DuckDB volume-at-price aggregation
        vap = self.duck.query_volume_at_price("NSE", "RELIANCE", "2026-11-19", tick_size=0.05)
        self.assertEqual(len(vap), 2)
        
        # Level 2500.0: total 300 (100 buy, 200 sell, delta -100)
        bin_2500 = next(b for b in vap if abs(b["price_bin"] - 2500.0) < 0.01)
        self.assertEqual(bin_2500["total_vol"], 300)
        self.assertEqual(bin_2500["buy_vol"], 100)
        self.assertEqual(bin_2500["sell_vol"], 200)
        self.assertEqual(bin_2500["delta"], -100)

        # Level 2500.05: total 500 (500 buy, 0 sell, delta +500)
        bin_250005 = next(b for b in vap if abs(b["price_bin"] - 2500.05) < 0.01)
        self.assertEqual(bin_250005["total_vol"], 500)
        self.assertEqual(bin_250005["buy_vol"], 500)
        self.assertEqual(bin_250005["delta"], 500)

    def test_footprint_bar_write_and_read(self):
        c1 = PriceCluster(
            price=2500.0,
            bid_vol=100,
            ask_vol=300,
            total_vol=400,
            delta=200,
            trade_count=5,
            imbalance_buy=True,
            provenance=self.prov_real,
        )
        bar = FootprintBar(
            instrument_id="INS_NSE_RELIANCE",
            timeframe="5m",
            open_time_utc=1794195900000,
            close_time_utc=1794196200000,
            open=2500.0,
            high=2505.0,
            low=2495.0,
            close=2502.0,
            volume=400,
            turnover=1000000.0,
            delta=200,
            cum_delta=200,
            delta_min=-50,
            delta_max=200,
            delta_finish=0.50,
            clusters={2500.0: c1},
            poc_price=2500.0,
            vah=2502.0,
            val=2498.0,
            stacked_buy_imbalances=[2500.0],
            stacked_sell_imbalances=[],
            provenance=self.prov_real,
        )
        path = self.storage.write_footprint_bars("NSE", "RELIANCE", "2026-11-19", [bar])
        self.assertTrue(os.path.exists(path))

        read_bars = self.storage.read_footprint_bars("NSE", "RELIANCE", "2026-11-19")
        self.assertEqual(len(read_bars), 1)
        self.assertEqual(read_bars[0].poc_price, 2500.0)
        self.assertIn(2500.0, read_bars[0].clusters)
        self.assertEqual(read_bars[0].clusters[2500.0].delta, 200)


class TestRedisCoordinator(unittest.TestCase):
    def test_fallback_stream_publish_and_read(self):
        coord = RedisCoordinator("redis://invalid_host:6379/0")
        self.assertFalse(coord.is_connected)

        msg_id1 = coord.publish_event("market.ticks.INS_NSE_RELIANCE", {"price": "2500.0", "qty": "100"})
        msg_id2 = coord.publish_event("market.ticks.INS_NSE_RELIANCE", {"price": "2501.0", "qty": "200"})

        events = coord.read_stream("market.ticks.INS_NSE_RELIANCE", last_id="0")
        self.assertEqual(len(events), 2)
        self.assertEqual(events[0]["data"]["price"], "2500.0")
        self.assertEqual(events[1]["data"]["qty"], "200")


if __name__ == "__main__":
    unittest.main()
