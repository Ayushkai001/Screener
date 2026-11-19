"""STRATLAB Unit Tests: Real Broker Live Tick Adapters (Zerodha Kite & TrueData)."""

import unittest
from datetime import datetime, timezone

from backend.app.market_data.adapters.kite import KiteTickAdapter
from backend.app.market_data.adapters.truedata import TrueDataTickAdapter
from shared.schemas.provenance import AggressorSide, DataQuality, SideMethod


class TestKiteTickAdapter(unittest.TestCase):
    """Verifies Zerodha Kite Connect WebSocket adapter normalization and provenance."""

    def setUp(self):
        self.adapter = KiteTickAdapter(token_map={256265: "INS_NSE_INFY", 738561: "INS_NSE_RELIANCE"})

    def test_kite_full_depth_quote_match_buy(self):
        """Tick hitting Ask price is classified as Level B Quote Match BUY."""
        packet = {
            "instrument_token": 738561,
            "mode": "full",
            "last_price": 2505.0,
            "last_traded_quantity": 50,
            "volume_traded": 10000,
            "timestamp": datetime(2026, 11, 19, 9, 15, 5, tzinfo=timezone.utc),
            "depth": {
                "buy": [{"price": 2504.5, "quantity": 200, "orders": 5}],
                "sell": [{"price": 2505.0, "quantity": 150, "orders": 3}],
            },
        }

        tick, depth = self.adapter.normalize_tick(packet)
        self.assertIsNotNone(tick)
        self.assertEqual(tick.instrument_id, "INS_NSE_RELIANCE")
        self.assertEqual(tick.price, 2505.0)
        self.assertEqual(tick.quantity, 50)
        self.assertEqual(tick.aggressor, AggressorSide.BUY)
        self.assertEqual(tick.provenance.quality, DataQuality.LEVEL_B_QUOTE_CLASSIFIED)
        self.assertEqual(tick.provenance.side_method, SideMethod.QUOTE_BBO)
        self.assertEqual(tick.provenance.confidence, 0.95)
        self.assertFalse(tick.provenance.is_estimated)

        # Verify Depth contract
        self.assertIsNotNone(depth)
        self.assertEqual(depth.bids[0].price, 2504.5)
        self.assertEqual(depth.asks[0].price, 2505.0)

    def test_kite_full_depth_quote_match_sell(self):
        """Tick hitting Bid price is classified as Level B Quote Match SELL."""
        packet = {
            "instrument_token": 738561,
            "last_price": 2504.5,
            "last_traded_quantity": 100,
            "volume_traded": 10100,
            "depth": {
                "buy": [{"price": 2504.5, "quantity": 300}],
                "sell": [{"price": 2505.0, "quantity": 150}],
            },
        }

        tick, _ = self.adapter.normalize_tick(packet)
        self.assertIsNotNone(tick)
        self.assertEqual(tick.aggressor, AggressorSide.SELL)
        self.assertEqual(tick.provenance.quality, DataQuality.LEVEL_B_QUOTE_CLASSIFIED)

    def test_kite_inside_spread_tick_rule_fallback(self):
        """Tick between Bid and Ask falls back to Level C Tick Rule."""
        # Prime previous price
        self.adapter.normalize_tick({
            "instrument_token": 738561,
            "last_price": 2500.0,
            "depth": {"buy": [{"price": 2498.0, "quantity": 10}], "sell": [{"price": 2502.0, "quantity": 10}]},
        })

        # Higher price inside spread (2500.5 > 2500.0) -> Level C BUY
        packet = {
            "instrument_token": 738561,
            "last_price": 2500.5,
            "last_traded_quantity": 25,
            "depth": {"buy": [{"price": 2498.0, "quantity": 10}], "sell": [{"price": 2502.0, "quantity": 10}]},
        }
        tick, _ = self.adapter.normalize_tick(packet)
        self.assertIsNotNone(tick)
        self.assertEqual(tick.aggressor, AggressorSide.BUY)
        self.assertEqual(tick.provenance.quality, DataQuality.LEVEL_C_TICK_RULE)
        self.assertEqual(tick.provenance.side_method, SideMethod.TICK_RULE)
        self.assertTrue(tick.provenance.is_estimated)

    def test_invalid_kite_packets(self):
        """Rejects ticks missing token or invalid price."""
        self.assertIsNone(self.adapter.normalize_tick({}))
        self.assertIsNone(self.adapter.normalize_tick({"instrument_token": 123, "last_price": 0.0}))


class TestTrueDataTickAdapter(unittest.TestCase):
    """Verifies TrueData WebSocket/TCP adapter normalization and provenance."""

    def setUp(self):
        self.adapter = TrueDataTickAdapter(symbol_map={"RELIANCE": "INS_NSE_RELIANCE", "NIFTY-I": "INS_NSE_NIFTY_FUT"})

    def test_truedata_tbt_exchange_flag(self):
        """TrueData TBT feed with trade_type 'B' produces Level A Exchange Verified."""
        packet = {
            "symbol": "RELIANCE",
            "price": 2510.0,
            "size": 150,
            "trade_type": "B",
            "timestamp": "2026-11-19 09:15:30.500000",
            "seq_no": 987654,
        }

        tick, _ = self.adapter.normalize_tick(packet)
        self.assertIsNotNone(tick)
        self.assertEqual(tick.instrument_id, "INS_NSE_RELIANCE")
        self.assertEqual(tick.price, 2510.0)
        self.assertEqual(tick.quantity, 150)
        self.assertEqual(tick.aggressor, AggressorSide.BUY)
        self.assertEqual(tick.provenance.quality, DataQuality.LEVEL_A_EXCHANGE_VERIFIED)
        self.assertEqual(tick.provenance.side_method, SideMethod.EXCHANGE_FLAG)
        self.assertEqual(tick.provenance.confidence, 1.0)
        self.assertFalse(tick.provenance.is_estimated)
        self.assertEqual(tick.sequence_id, 987654)

    def test_truedata_level_b_quote_match(self):
        """TrueData L1 quote stream matching Ask produces Level B Quote Match."""
        packet = {
            "symbol": "RELIANCE",
            "price": 2510.0,
            "size": 75,
            "bid": 2509.5,
            "ask": 2510.0,
            "bid_size": 500,
            "ask_size": 300,
        }

        tick, depth = self.adapter.normalize_tick(packet)
        self.assertIsNotNone(tick)
        self.assertEqual(tick.aggressor, AggressorSide.BUY)
        self.assertEqual(tick.provenance.quality, DataQuality.LEVEL_B_QUOTE_CLASSIFIED)
        self.assertIsNotNone(depth)
        self.assertEqual(depth.bids[0].quantity, 500)
        self.assertEqual(depth.asks[0].quantity, 300)

    def test_truedata_level_c_tick_rule(self):
        """No depth or trade flags falls back to Level C Tick Rule."""
        # Prime
        self.adapter.normalize_tick({"symbol": "NIFTY-I", "price": 24000.0, "size": 50})
        # Drop
        packet = {"symbol": "NIFTY-I", "price": 23995.0, "size": 25}
        tick, _ = self.adapter.normalize_tick(packet)
        self.assertIsNotNone(tick)
        self.assertEqual(tick.aggressor, AggressorSide.SELL)
        self.assertEqual(tick.provenance.quality, DataQuality.LEVEL_C_TICK_RULE)
        self.assertTrue(tick.provenance.is_estimated)


if __name__ == "__main__":
    unittest.main()
