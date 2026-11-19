"""Unit and mathematical validation tests for STRATLAB Block 04: Analytics & Order Flow Engines.

Run: .venv/bin/python -m unittest tests/test_analytics.py -v
"""

import unittest

from backend.app.analytics import (
    CVDEngine,
    FootprintAggregator,
    IndicatorEngine,
    SMCDetectionEngine,
    VolumeProfileEngine,
)
from shared.schemas.market_data import Candle, TradeTick
from shared.schemas.provenance import AggressorSide, ProvenanceMetadata


class TestFootprintAggregator(unittest.TestCase):
    def setUp(self):
        self.prov = ProvenanceMetadata.exchange_verified("NSE_TBT")
        self.agg = FootprintAggregator(
            instrument_id="INS_NSE_RELIANCE",
            timeframe="5m",
            tick_size=0.05,
            imbalance_ratio=3.0,
            min_imbalance_volume=50,
            stacked_min_count=2,
        )

    def test_diagonal_imbalance_and_clusters(self):
        # Trade 1: 100 units at 2500.00 sold at Bid
        self.agg.on_tick(TradeTick(
            instrument_id="INS_NSE_RELIANCE",
            timestamp_ns=1000,
            price=2500.00,
            quantity=100,
            aggressor=AggressorSide.SELL,
            provenance=self.prov,
        ))
        # Trade 2: 400 units at 2500.05 bought at Ask (400 >= 3 * 100 -> Diagonal Buy Imbalance!)
        self.agg.on_tick(TradeTick(
            instrument_id="INS_NSE_RELIANCE",
            timestamp_ns=2000,
            price=2500.05,
            quantity=400,
            aggressor=AggressorSide.BUY,
            provenance=self.prov,
        ))
        # Trade 3: 500 units at 2500.10 bought at Ask (500 >= 3 * 0 -> Diagonal Buy Imbalance!)
        self.agg.on_tick(TradeTick(
            instrument_id="INS_NSE_RELIANCE",
            timestamp_ns=3000,
            price=2500.10,
            quantity=500,
            aggressor=AggressorSide.BUY,
            provenance=self.prov,
        ))

        bar = self.agg.finalize_bar(session_cum_delta=1000)
        self.assertIsNotNone(bar)
        self.assertEqual(bar.volume, 1000)
        self.assertEqual(bar.delta, 800) # (400 + 500) - 100
        self.assertEqual(bar.cum_delta, 1800)

        # Check clusters
        self.assertIn(2500.05, bar.clusters)
        self.assertTrue(bar.clusters[2500.05].imbalance_buy)
        self.assertTrue(bar.clusters[2500.10].imbalance_buy)

        # Stacked buy imbalances at [2500.05, 2500.10]
        self.assertEqual(bar.stacked_buy_imbalances, [2500.05, 2500.10])

        # Point of control: level 2500.10 has max volume (500)
        self.assertEqual(bar.poc_price, 2500.10)


class TestVolumeProfileEngine(unittest.TestCase):
    def setUp(self):
        self.prov = ProvenanceMetadata.exchange_verified("NSE_TBT")

    def test_volume_profile_70_percent_value_area(self):
        # Create distribution: peak at 100.0
        ticks = [
            TradeTick(instrument_id="INS_01", timestamp_ns=1000, price=99.90, quantity=50, aggressor=AggressorSide.BUY, provenance=self.prov),
            TradeTick(instrument_id="INS_01", timestamp_ns=2000, price=99.95, quantity=150, aggressor=AggressorSide.BUY, provenance=self.prov),
            TradeTick(instrument_id="INS_01", timestamp_ns=3000, price=100.00, quantity=500, aggressor=AggressorSide.BUY, provenance=self.prov), # POC
            TradeTick(instrument_id="INS_01", timestamp_ns=4000, price=100.05, quantity=200, aggressor=AggressorSide.BUY, provenance=self.prov),
            TradeTick(instrument_id="INS_01", timestamp_ns=5000, price=100.10, quantity=100, aggressor=AggressorSide.BUY, provenance=self.prov),
        ]
        vp = VolumeProfileEngine.build_from_ticks(ticks, "INS_01", "2026-11-19", tick_size=0.05)
        self.assertIsNotNone(vp)
        self.assertEqual(vp.total_volume, 1000)
        self.assertEqual(vp.poc_price, 100.00)
        self.assertEqual(vp.poc_volume, 500)

        # Total inside [VAL, VAH] must be >= 70% of 1000 (>= 700)
        self.assertGreaterEqual(vp.vah_price, 100.00)
        self.assertLessEqual(vp.val_price, 100.00)
        enclosed_vol = sum(vol for p, vol in vp.bins.items() if vp.val_price <= p <= vp.vah_price)
        self.assertGreaterEqual(enclosed_vol, 700)


class TestCVDEngine(unittest.TestCase):
    def setUp(self):
        self.prov = ProvenanceMetadata.exchange_verified("NSE_TBT")

    def test_cvd_accumulation_and_reset(self):
        cvd = CVDEngine("INS_01")
        p1 = cvd.on_delta(1000, delta=100, provenance=self.prov, is_session_open=True)
        self.assertEqual(p1.cumulative_delta, 100)

        p2 = cvd.on_delta(2000, delta=-40, provenance=self.prov)
        self.assertEqual(p2.cumulative_delta, 60)

        # Next session open -> resets to 0 + delta
        p3 = cvd.on_delta(3000, delta=50, provenance=self.prov, is_session_open=True)
        self.assertEqual(p3.cumulative_delta, 50)

    def test_absorption_divergence_detection(self):
        # Bullish Absorption: Price falling, but CVD rising
        prices = [100.0, 99.5, 99.0, 98.5, 98.0]
        cvd_vals = [-500, -300, -100, 100, 300]
        div = CVDEngine.detect_divergence(prices, cvd_vals, lookback=5)
        self.assertEqual(div, "BULLISH_ABSORPTION")

        # Bearish Absorption: Price rising, but CVD falling
        prices_up = [100.0, 100.5, 101.0, 101.5, 102.0]
        cvd_down = [500, 300, 100, -100, -300]
        div2 = CVDEngine.detect_divergence(prices_up, cvd_down, lookback=5)
        self.assertEqual(div2, "BEARISH_ABSORPTION")


class TestSMCDetectionEngine(unittest.TestCase):
    def setUp(self):
        self.prov = ProvenanceMetadata.exchange_verified("NSE_TBT")
        self.engine = SMCDetectionEngine(swing_lookback=2)

    def _make_candles(self, highs, lows, closes=None, opens=None):
        candles = []
        for i, (h, l) in enumerate(zip(highs, lows)):
            c = closes[i] if closes else (h + l) / 2.0
            o = opens[i] if opens else (h + l) / 2.0
            candles.append(Candle(
                instrument_id="INS_01",
                timestamp_utc=(i + 1) * 60000,
                timeframe="1m",
                open=o,
                high=h,
                low=l,
                close=c,
                volume=1000,
                provenance=self.prov,
            ))
        return candles

    def test_swing_and_structure_break(self):
        # 5 candles forming an obvious swing high at index 2 (high=110)
        highs = [100, 105, 110, 104, 102]
        lows = [95, 99, 102, 98, 96]
        candles = self._make_candles(highs, lows)

        swings = self.engine.find_swings(candles)
        self.assertTrue(any(s.is_high and s.price == 110 for s in swings))

        # Add a 6th candle breaking 110
        break_candle = Candle(
            instrument_id="INS_01",
            timestamp_utc=6 * 60000,
            timeframe="1m",
            open=105,
            high=115,
            low=104,
            close=112, # Closed above 110 -> BOS / CHoCH
            volume=5000,
            provenance=self.prov,
        )
        candles.append(break_candle)
        breaks = self.engine.detect_structure_breaks(candles, swings)
        self.assertEqual(len(breaks), 1)
        self.assertEqual(breaks[0]["reference_price"], 110)

    def test_fair_value_gap(self):
        # Bullish FVG: Candle 1 High = 100, Candle 3 Low = 102 (Void between 100 and 102)
        c1 = Candle(instrument_id="INS_01", timestamp_utc=1000, timeframe="1m", open=95, high=100, low=94, close=99, volume=100, provenance=self.prov)
        c2 = Candle(instrument_id="INS_01", timestamp_utc=2000, timeframe="1m", open=99, high=108, low=98, close=107, volume=500, provenance=self.prov)
        c3 = Candle(instrument_id="INS_01", timestamp_utc=3000, timeframe="1m", open=107, high=110, low=102, close=109, volume=300, provenance=self.prov)

        fvgs = SMCDetectionEngine.detect_fair_value_gaps([c1, c2, c3])
        self.assertEqual(len(fvgs), 1)
        self.assertTrue(fvgs[0].is_bullish)
        self.assertEqual(fvgs[0].bottom_price, 100)
        self.assertEqual(fvgs[0].top_price, 102)


class TestIndicatorEngine(unittest.TestCase):
    def test_technical_indicators(self):
        prices = [10.0, 11.0, 12.0, 11.0, 10.0, 11.0, 12.0, 13.0, 14.0, 13.0, 12.0, 11.0, 10.0, 9.0, 10.0, 11.0]
        sma3 = IndicatorEngine.sma(prices, 3)
        self.assertAlmostEqual(sma3[2], 11.0) # (10 + 11 + 12)/3
        self.assertAlmostEqual(sma3[3], 11.3333, places=3) # (11 + 12 + 11)/3

        ema3 = IndicatorEngine.ema(prices, 3)
        self.assertIsNotNone(ema3[2])

        rsi = IndicatorEngine.rsi(prices, 5)
        self.assertIsNotNone(rsi[5])


if __name__ == "__main__":
    unittest.main()
