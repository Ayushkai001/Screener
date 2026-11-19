"""Unit and contract validation tests for STRATLAB Block 01 domain models.

Run: .venv/bin/python -m unittest tests/test_contracts.py -v
"""

from datetime import date
import unittest
from pydantic import ValidationError

from shared.schemas import (
    AggressorSide,
    AssetClass,
    BookLevel,
    Candle,
    CVDPoint,
    DataQuality,
    FootprintBar,
    InstrumentMaster,
    OptionType,
    OrderBookDepth,
    OrderSide,
    OrderStatus,
    OrderType,
    PaperAccount,
    PaperFill,
    PaperOrder,
    PaperPosition,
    PriceCluster,
    ProvenanceMetadata,
    SideMethod,
    TradeTick,
    VolumeProfile,
)


class TestProvenanceContracts(unittest.TestCase):
    def test_factory_helpers(self):
        prov_a = ProvenanceMetadata.exchange_verified("NSE_TBT")
        self.assertEqual(prov_a.quality, DataQuality.LEVEL_A_EXCHANGE_VERIFIED)
        self.assertEqual(prov_a.side_method, SideMethod.EXCHANGE_FLAG)
        self.assertEqual(prov_a.confidence, 1.0)
        self.assertFalse(prov_a.is_estimated)

        prov_b = ProvenanceMetadata.quote_classified("ZERODHA_BBO", 0.92)
        self.assertEqual(prov_b.quality, DataQuality.LEVEL_B_QUOTE_CLASSIFIED)
        self.assertFalse(prov_b.is_estimated)
        self.assertEqual(prov_b.confidence, 0.92)

        prov_c = ProvenanceMetadata.tick_rule_estimated("LEE_READY", 0.65)
        self.assertEqual(prov_c.quality, DataQuality.LEVEL_C_TICK_RULE)
        self.assertTrue(prov_c.is_estimated)

        prov_d = ProvenanceMetadata.ohlcv_proxy("BVC_1M", 0.35)
        self.assertEqual(prov_d.quality, DataQuality.LEVEL_D_OHLCV_PROXY)
        self.assertTrue(prov_d.is_estimated)

    def test_estimated_consistency_enforced(self):
        # Level A cannot claim is_estimated=True
        with self.assertRaises(ValidationError):
            ProvenanceMetadata(
                quality=DataQuality.LEVEL_A_EXCHANGE_VERIFIED,
                side_method=SideMethod.EXCHANGE_FLAG,
                source_id="FEED",
                confidence=1.0,
                is_estimated=True,
            )

        # Level C cannot claim is_estimated=False
        with self.assertRaises(ValidationError):
            ProvenanceMetadata(
                quality=DataQuality.LEVEL_C_TICK_RULE,
                side_method=SideMethod.TICK_RULE,
                source_id="FEED",
                confidence=0.65,
                is_estimated=False,
            )

    def test_confidence_bounds(self):
        with self.assertRaises(ValidationError):
            ProvenanceMetadata(
                quality=DataQuality.LEVEL_A_EXCHANGE_VERIFIED,
                side_method=SideMethod.EXCHANGE_FLAG,
                source_id="FEED",
                confidence=1.05,
                is_estimated=False,
            )
        with self.assertRaises(ValidationError):
            ProvenanceMetadata(
                quality=DataQuality.LEVEL_A_EXCHANGE_VERIFIED,
                side_method=SideMethod.EXCHANGE_FLAG,
                source_id="FEED",
                confidence=-0.1,
                is_estimated=False,
            )


class TestInstrumentContracts(unittest.TestCase):
    def test_valid_equity(self):
        inst = InstrumentMaster(
            instrument_id="INS_NSE_RELIANCE",
            symbol="reliance",
            exchange="nse",
            asset_class=AssetClass.EQUITY,
            tick_size=0.05,
            lot_size=1,
        )
        self.assertEqual(inst.symbol, "RELIANCE")
        self.assertEqual(inst.exchange, "NSE")
        self.assertEqual(inst.currency, "INR")

    def test_derivatives_validation(self):
        # Options missing strike/expiry must fail
        with self.assertRaises(ValidationError):
            InstrumentMaster(
                instrument_id="INS_NSE_NIFTY_OPT",
                symbol="NIFTY26D1524000CE",
                exchange="NSE",
                asset_class=AssetClass.OPTIONS,
                tick_size=0.05,
            )

        # Options with all fields succeeds
        opt = InstrumentMaster(
            instrument_id="INS_NSE_NIFTY_OPT",
            symbol="NIFTY26D1524000CE",
            exchange="NSE",
            asset_class=AssetClass.OPTIONS,
            tick_size=0.05,
            expiry=date(2026, 12, 15),
            strike=24000.0,
            option_type=OptionType.CALL,
            underlying_id="INS_NSE_NIFTY",
        )
        self.assertEqual(opt.option_type, OptionType.CALL)


class TestMarketDataContracts(unittest.TestCase):
    def setUp(self):
        self.prov = ProvenanceMetadata.exchange_verified("TEST")

    def test_candle_envelope_invariants(self):
        # Valid candle
        Candle(
            instrument_id="INS_NSE_RELIANCE",
            timestamp_utc=1794195900000,
            timeframe="5m",
            open=2500.0,
            high=2510.0,
            low=2495.0,
            close=2505.0,
            volume=15000,
            provenance=self.prov,
        )

        # High lower than Low must fail
        with self.assertRaises(ValidationError):
            Candle(
                instrument_id="INS_NSE_RELIANCE",
                timestamp_utc=1794195900000,
                timeframe="5m",
                open=2500.0,
                high=2490.0,
                low=2500.0,
                close=2500.0,
                volume=15000,
                provenance=self.prov,
            )

    def test_trade_tick_and_bbo(self):
        # Crossed market bid > ask must fail
        with self.assertRaises(ValidationError):
            TradeTick(
                instrument_id="INS_NSE_RELIANCE",
                timestamp_ns=1794195900000000000,
                price=2500.0,
                quantity=100,
                aggressor=AggressorSide.BUY,
                bid=2501.0,
                ask=2500.0,
                provenance=self.prov,
            )

    def test_order_book_depth_sorting(self):
        # Crossed book (bid >= ask) must fail
        with self.assertRaises(ValidationError):
            OrderBookDepth(
                instrument_id="INS_NSE_RELIANCE",
                timestamp_ns=1794195900000000000,
                bids=[BookLevel(price=2500.0, quantity=100)],
                asks=[BookLevel(price=2500.0, quantity=100)],
                provenance=self.prov,
            )


class TestOrderFlowContracts(unittest.TestCase):
    def setUp(self):
        self.prov = ProvenanceMetadata.exchange_verified("TEST")

    def test_price_cluster_totals(self):
        # Valid cluster
        c = PriceCluster(
            price=2500.0,
            bid_vol=100,
            ask_vol=300,
            total_vol=400,
            delta=200,
            trade_count=12,
            imbalance_buy=True,
            provenance=self.prov,
        )
        self.assertEqual(c.delta, 200)

        # Mismatched total volume must fail
        with self.assertRaises(ValidationError):
            PriceCluster(
                price=2500.0,
                bid_vol=100,
                ask_vol=300,
                total_vol=500,
                delta=200,
                provenance=self.prov,
            )

    def test_footprint_va_bounds(self):
        with self.assertRaises(ValidationError):
            FootprintBar(
                instrument_id="INS_NSE_RELIANCE",
                timeframe="5m",
                open_time_utc=1794195900000,
                close_time_utc=1794196200000,
                open=2500.0,
                high=2510.0,
                low=2495.0,
                close=2505.0,
                volume=1000,
                delta=200,
                cum_delta=500,
                delta_min=-50,
                delta_max=300,
                delta_finish=0.20,
                poc_price=2502.0,
                vah=2498.0,
                val=2506.0, # VAH < VAL invalid
                provenance=self.prov,
            )


class TestExecutionContracts(unittest.TestCase):
    def test_paper_order_validation(self):
        # Limit order requires price
        with self.assertRaises(ValidationError):
            PaperOrder(
                order_id="ORD_001",
                account_id="ACC_001",
                instrument_id="INS_NSE_RELIANCE",
                side=OrderSide.BUY,
                order_type=OrderType.LIMIT,
                quantity=100,
                created_time_utc=1794195900000,
                updated_time_utc=1794195900000,
            )

        # Valid limit order
        order = PaperOrder(
            order_id="ORD_001",
            account_id="ACC_001",
            instrument_id="INS_NSE_RELIANCE",
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            price=2500.0,
            quantity=100,
            queue_ahead_volume=14200,
            created_time_utc=1794195900000,
            updated_time_utc=1794195900000,
        )
        self.assertEqual(order.status, OrderStatus.PENDING)
        self.assertEqual(order.queue_ahead_volume, 14200)


if __name__ == "__main__":
    unittest.main()
