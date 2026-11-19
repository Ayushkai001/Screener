"""Unit tests for STRATLAB Simulation and Execution Subsystem."""

import unittest
from shared.schemas.execution import OrderSide, OrderStatus, OrderType, PaperOrder
from shared.schemas.market_data import Candle, TradeTick
from shared.schemas.provenance import AggressorSide, DataQuality, ProvenanceMetadata, SideMethod
from backend.app.execution.backtest.engine import BacktestEngine
from backend.app.execution.paper.matching_engine import SimulatedMatchingEngine
from backend.app.execution.portfolio.costs import CostModel
from backend.app.execution.portfolio.ledger import PortfolioLedger
from backend.app.strategy.compiler.compiler import StrategyCompiler
from backend.app.strategy.ir.models import (
    ComparisonOperator,
    ConditionGroup,
    ConditionNode,
    LogicalOp,
    Operand,
    OperandKind,
    RiskParams,
    StopLossConfig,
    StrategyIR,
    TakeProfitConfig,
    TrailingStopConfig,
)


class TestCostModel(unittest.TestCase):
    def test_india_delivery_statutory_costs(self):
        # 100 shares @ 1000 = Rs 1,00,000 turnover
        # STT = 0.1% = 100
        # Exch = 0.00297% = 2.97
        # Stamp (Buy) = 0.015% = 15.0
        # Sebi = 0.10
        # GST = (2.97 + 0.10) * 0.18 = 0.55
        # Total approx 100 + 2.97 + 15 + 0.10 + 0.55 = 118.62
        buy_costs = CostModel.calculate("india_delivery", "BUY", 1000.0, 100)
        self.assertEqual(buy_costs.stt, 100.0)
        self.assertAlmostEqual(buy_costs.stamp_duty, 15.0, places=2)
        self.assertGreater(buy_costs.total, 118.0)

        # Sell delivery: no stamp duty
        sell_costs = CostModel.calculate("india_delivery", "SELL", 1000.0, 100)
        self.assertEqual(sell_costs.stamp_duty, 0.0)
        self.assertEqual(sell_costs.stt, 100.0)

    def test_crypto_costs(self):
        costs = CostModel.calculate("crypto_futures", "BUY", 50000.0, 1)
        self.assertAlmostEqual(costs.total, 20.0, places=2) # 50,000 * 0.0004


class TestPortfolioLedger(unittest.TestCase):
    def setUp(self):
        self.ledger = PortfolioLedger(initial_cash=100_000.0, cost_profile="zero_fee")

    def test_risk_based_sizing(self):
        # Capital = 100,000; Risk = 1% = Rs 1,000
        # Entry = 100, Stop = 95 -> Risk per share = 5
        # Allowed shares = 1,000 / 5 = 200 shares
        shares = self.ledger.calculate_position_size(price=100.0, stop_price=95.0, risk_pct=1.0)
        self.assertEqual(shares, 200)

    def test_open_and_close_position_pnl(self):
        pos = self.ledger.open_position(
            instrument_id="INS_01",
            symbol="RELIANCE",
            side="LONG",
            price=100.0,
            quantity=100,
            timestamp_utc=1000,
            stop_loss=95.0,
            take_profit=110.0,
        )
        self.assertEqual(self.ledger.cash, 90_000.0) # 100,000 - 10,000
        self.assertIn("INS_01", self.ledger.positions)

        # Close position at 110 (+10/share = +1000 profit)
        closed = self.ledger.close_position("INS_01", exit_price=110.0, timestamp_utc=2000, reason="TARGET")
        self.assertIsNotNone(closed)
        self.assertEqual(closed.gross_pnl, 1000.0)
        self.assertEqual(self.ledger.cash, 101_000.0)
        self.assertEqual(self.ledger.realized_pnl, 1000.0)
        self.assertNotIn("INS_01", self.ledger.positions)


class TestSimulatedMatchingEngine(unittest.TestCase):
    def setUp(self):
        self.engine = SimulatedMatchingEngine(slippage_ticks=1, tick_size=0.05)
        self.prov = ProvenanceMetadata.exchange_verified("NSE_TBT")

    def test_market_order_immediate_fill(self):
        order = PaperOrder(
            order_id="ORD_01",
            account_id="ACC_01",
            instrument_id="INS_01",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=50,
            created_time_utc=1000,
            updated_time_utc=1000,
        )
        fill = self.engine.submit_order(order, best_bid=100.0, best_ask=100.05)
        self.assertIsNotNone(fill)
        # Ask was 100.05 + 1 tick slippage (0.05) = 100.10
        self.assertAlmostEqual(fill.price, 100.10)
        self.assertEqual(self.engine.orders["ORD_01"].status, OrderStatus.FILLED)

    def test_queue_aware_limit_order_fill(self):
        order = PaperOrder(
            order_id="ORD_02",
            account_id="ACC_01",
            instrument_id="INS_01",
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            price=100.0,
            quantity=100,
            created_time_utc=1000,
            updated_time_utc=1000,
        )

        # Submit limit order when 500 shares stand ahead at 100.0
        fill = self.engine.submit_order(order, best_bid=100.0, best_ask=100.20, level_depth_volume=500)
        self.assertIsNone(fill)
        self.assertEqual(self.engine.orders["ORD_02"].status, OrderStatus.PENDING)

        # 1. Trade arrives at 100.0 for 300 shares -> Not enough to exhaust 500 ahead
        tick1 = TradeTick(
            instrument_id="INS_01",
            timestamp_ns=2000 * 1_000_000,
            price=100.0,
            quantity=300,
            aggressor=AggressorSide.SELL,
            provenance=self.prov,
        )
        fills1 = self.engine.on_trade_tick(tick1)
        self.assertEqual(len(fills1), 0)

        # 2. Trade arrives at 100.0 for 250 shares -> Exhausts remaining 200 ahead, fills order!
        tick2 = TradeTick(
            instrument_id="INS_01",
            timestamp_ns=3000 * 1_000_000,
            price=100.0,
            quantity=250,
            aggressor=AggressorSide.SELL,
            provenance=self.prov,
        )
        fills2 = self.engine.on_trade_tick(tick2)
        self.assertEqual(len(fills2), 1)
        self.assertEqual(fills2[0].price, 100.0)
        self.assertEqual(self.engine.orders["ORD_02"].status, OrderStatus.FILLED)


class TestBacktestEngine(unittest.TestCase):
    def test_backtest_simulation_with_target_and_stop(self):
        prov = ProvenanceMetadata.exchange_verified("NSE_TBT")
        candles = []

        # Create 30 candles:
        # Bars 0-10: range 95-99
        # Bar 11: break above 100 (triggers entry at bar 12 open)
        # Bars 12-15: rises to 105 (hits 4% target)
        for i in range(30):
            p = 95.0 + (i * 0.4 if i < 11 else i * 0.8)
            candles.append(Candle(
                instrument_id="INS_01",
                timestamp_utc=(i + 1) * 60000,
                timeframe="5m",
                open=p,
                high=p + 2.0,
                low=p - 1.0,
                close=p + 1.0,
                volume=10000,
                provenance=prov,
            ))

        # Strategy: Buy when close > 100
        ir = StrategyIR(
            name="Breakout Strategy",
            entry_long=ConditionGroup(
                operator=LogicalOp.AND,
                nodes=[
                    ConditionNode(
                        left=Operand(kind=OperandKind.PRICE, name="close"),
                        operator=ComparisonOperator.GT,
                        right=Operand(kind=OperandKind.CONSTANT, value=100.0),
                    )
                ]
            ),
            risk=RiskParams(
                stop_loss=StopLossConfig(mode="pct", value=2.0),
                take_profit=TakeProfitConfig(mode="pct", value=4.0),
                trailing_stop=TrailingStopConfig(mode="none"),
            )
        )

        compiler = StrategyCompiler()
        compiled = compiler.compile(ir)

        ledger = PortfolioLedger(initial_cash=100_000.0, cost_profile="zero_fee")
        engine = BacktestEngine(ledger=ledger)
        result = engine.run(compiled, candles)

        self.assertGreater(result.metrics.total_trades, 0)
        self.assertGreater(result.metrics.winning_trades, 0)
        self.assertGreater(result.metrics.final_equity, 100_000.0)
        self.assertEqual(len(result.equity_curve), len(candles))


if __name__ == "__main__":
    unittest.main()
