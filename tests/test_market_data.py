"""Unit and integration tests for STRATLAB Block 03: Market Data Platform.

Run: .venv/bin/python -m unittest tests/test_market_data.py -v
"""

import shutil
import tempfile
import unittest

from backend.app.database.parquet_manager import ParquetStorageManager
from backend.app.market_data import (
    HistoricalIngestionWorker,
    MonotonicJitterBuffer,
    SequenceGapDetector,
    StreamingIngestionWorker,
    SyntheticClassifier,
    normalize_broker_tick,
    normalize_nse_bhavcopy_row,
    normalize_yahoo_bars,
)
from shared.schemas.market_data import Candle, TradeTick
from shared.schemas.provenance import AggressorSide, DataQuality, ProvenanceMetadata


class TestSyntheticClassifier(unittest.TestCase):
    def setUp(self):
        self.classifier = SyntheticClassifier()

    def test_quote_match_level_b(self):
        # Trade at ask -> aggressive buy
        side, prov = self.classifier.classify_tick("INS_01", price=2501.0, bid=2500.0, ask=2501.0)
        self.assertEqual(side, AggressorSide.BUY)
        self.assertEqual(prov.quality, DataQuality.LEVEL_B_QUOTE_CLASSIFIED)
        self.assertFalse(prov.is_estimated)

        # Trade at bid -> aggressive sell
        side, prov = self.classifier.classify_tick("INS_01", price=2500.0, bid=2500.0, ask=2501.0)
        self.assertEqual(side, AggressorSide.SELL)

    def test_lee_ready_tick_rule_level_c(self):
        # 1st trade: no history -> UNKNOWN
        side, prov = self.classifier.classify_tick("INS_02", price=100.0)
        self.assertEqual(side, AggressorSide.UNKNOWN)
        self.assertEqual(prov.quality, DataQuality.LEVEL_C_TICK_RULE)
        self.assertTrue(prov.is_estimated)

        # 2nd trade: uptick 100.0 -> 101.0 -> BUY
        side, prov = self.classifier.classify_tick("INS_02", price=101.0)
        self.assertEqual(side, AggressorSide.BUY)

        # 3rd trade: zero tick 101.0 -> 101.0 -> inherits BUY
        side, prov = self.classifier.classify_tick("INS_02", price=101.0)
        self.assertEqual(side, AggressorSide.BUY)

        # 4th trade: downtick 101.0 -> 100.5 -> SELL
        side, prov = self.classifier.classify_tick("INS_02", price=100.5)
        self.assertEqual(side, AggressorSide.SELL)

    def test_bvc_candle_decomposition(self):
        prov = ProvenanceMetadata.ohlcv_proxy("TEST")
        # Extremely bullish marubozu bar
        bull_candle = Candle(
            instrument_id="INS_01",
            timestamp_utc=1000,
            timeframe="1m",
            open=100.0,
            high=110.0,
            low=100.0,
            close=110.0,
            volume=1000,
            provenance=prov,
        )
        buy_v, sell_v = SyntheticClassifier.decompose_candle_bvc(bull_candle)
        self.assertEqual(buy_v + sell_v, 1000)
        self.assertGreater(buy_v, 800) # Majority buy volume

        # Flat bar (circuit locked)
        flat_candle = Candle(
            instrument_id="INS_01",
            timestamp_utc=2000,
            timeframe="1m",
            open=100.0,
            high=100.0,
            low=100.0,
            close=100.0,
            volume=500,
            provenance=prov,
        )
        buy_v, sell_v = SyntheticClassifier.decompose_candle_bvc(flat_candle)
        self.assertEqual(buy_v, 250)
        self.assertEqual(sell_v, 250)


class TestSequenceGapDetector(unittest.TestCase):
    def test_gap_and_drop_detection(self):
        det = SequenceGapDetector(reset_threshold=500)
        inst = "INS_01"

        # Packet 1
        res1 = det.check_sequence(inst, 1)
        self.assertFalse(res1["is_gap"])

        # Packet 2
        res2 = det.check_sequence(inst, 2)
        self.assertFalse(res2["is_gap"])

        # Packet 5 (dropped 3 and 4)
        res5 = det.check_sequence(inst, 5)
        self.assertTrue(res5["is_gap"])
        self.assertEqual(res5["dropped_count"], 2)

        # Packet 5 again (duplicate)
        res_dup = det.check_sequence(inst, 5)
        self.assertTrue(res_dup["is_duplicate"])

        # Session reset from 5000 to 1
        det.check_sequence(inst, 5000)
        res_reset = det.check_sequence(inst, 1)
        self.assertTrue(res_reset["is_reset"])


class TestMonotonicJitterBuffer(unittest.TestCase):
    def test_reordering_out_of_order_packets(self):
        buf = MonotonicJitterBuffer(window_ms=50) # 50ms window = 50_000_000 ns

        t0_arrival = 100_000_000
        # Push packet 2 first (simulating network jitter)
        buf.push(timestamp_ns=2000, sequence_id=2, payload="PACKET_2", arrival_ns=t0_arrival + 5_000_000)
        # Push packet 1 second (arrived slightly later, but was generated earlier)
        buf.push(timestamp_ns=1000, sequence_id=1, payload="PACKET_1", arrival_ns=t0_arrival + 10_000_000)

        # Current time within window -> nothing ready yet
        ready = buf.pop_ready(current_time_ns=t0_arrival + 20_000_000)
        self.assertEqual(ready, [])

        # Current time past window -> pops in strictly sorted timestamp order!
        ready = buf.pop_ready(current_time_ns=t0_arrival + 70_000_000)
        self.assertEqual(ready, ["PACKET_1", "PACKET_2"])


class TestNormalizers(unittest.TestCase):
    def test_bhavcopy_normalizer(self):
        row = {
            "SYMBOL": "RELIANCE",
            "OPEN": "2500.0",
            "HIGH": "2510.0",
            "LOW": "2490.0",
            "CLOSE": "2505.0",
            "TOTTRDQTY": "150000",
            "TOTTRDVAL": "375750000.0",
            "TIMESTAMP": "09-NOV-2026",
        }
        candle = normalize_nse_bhavcopy_row(row, "INS_NSE_RELIANCE")
        self.assertIsNotNone(candle)
        self.assertEqual(candle.close, 2505.0)
        self.assertEqual(candle.provenance.quality, DataQuality.LEVEL_A_EXCHANGE_VERIFIED)

    def test_yahoo_normalizer(self):
        chart_data = {
            "chart": {
                "result": [{
                    "timestamp": [1794195900, 1794196200],
                    "indicators": {
                        "quote": [{
                            "open": [2500.0, 2505.0],
                            "high": [2510.0, 2515.0],
                            "low": [2495.0, 2500.0],
                            "close": [2505.0, 2512.0],
                            "volume": [10000, 12000],
                        }]
                    }
                }]
            }
        }
        candles = normalize_yahoo_bars(chart_data, "INS_NSE_RELIANCE", "5m")
        self.assertEqual(len(candles), 2)
        self.assertEqual(candles[0].provenance.quality, DataQuality.LEVEL_D_OHLCV_PROXY)


class TestStreamingPipelineIntegration(unittest.TestCase):
    def test_end_to_end_streaming_worker(self):
        dispatched_ticks = []
        worker = StreamingIngestionWorker(
            jitter_window_ms=50,
            on_tick_callback=lambda t: dispatched_ticks.append(t),
        )

        prov = ProvenanceMetadata.exchange_verified("LIVE_WS")
        # Ingest 3 ticks with sequence gaps and unknown aggressors
        t1 = TradeTick(
            instrument_id="INS_01",
            timestamp_ns=1_000_000_000,
            price=100.0,
            quantity=50,
            aggressor=AggressorSide.UNKNOWN,
            sequence_id=1,
            provenance=prov,
        )
        t2 = TradeTick(
            instrument_id="INS_01",
            timestamp_ns=1_005_000_000,
            price=101.0, # Uptick -> Lee-Ready will classify as BUY
            quantity=75,
            aggressor=AggressorSide.UNKNOWN,
            sequence_id=2,
            provenance=prov,
        )

        arr_t0 = 100_000_000
        worker.on_raw_tick(t1, arrival_ns=arr_t0)
        worker.on_raw_tick(t2, arrival_ns=arr_t0 + 1_000_000)

        # Before aging window
        ready = worker.poll_ready_ticks(current_time_ns=arr_t0 + 10_000_000)
        self.assertEqual(len(ready), 0)

        # After aging window
        ready = worker.poll_ready_ticks(current_time_ns=arr_t0 + 60_000_000)
        self.assertEqual(len(ready), 2)
        self.assertEqual(len(dispatched_ticks), 2)
        self.assertEqual(dispatched_ticks[1].aggressor, AggressorSide.BUY)


if __name__ == "__main__":
    unittest.main()
