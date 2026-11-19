"""Unit tests for STRATLAB Strategy IR, Component Registry, and Compiler."""

import unittest
from shared.schemas.provenance import DataQuality
from backend.app.strategy.ir.models import (
    ActionKind,
    ActionNode,
    ComparisonOperator,
    ConditionGroup,
    ConditionNode,
    LogicalOp,
    Operand,
    OperandKind,
    OrderType,
    StrategyIR,
)
from backend.app.strategy.registry.components import ComponentRegistry
from backend.app.strategy.compiler.compiler import (
    EvaluationContext,
    ProvenanceIncompatibilityError,
    StrategyCompilationError,
    StrategyCompiler,
)


class TestStrategyIRModels(unittest.TestCase):
    def test_operand_validation(self):
        # Constant operand requires value
        with self.assertRaises(ValueError):
            Operand(kind=OperandKind.CONSTANT)

        op_const = Operand(kind=OperandKind.CONSTANT, value=50.0)
        self.assertEqual(op_const.value, 50.0)

        # Indicator operand requires name
        with self.assertRaises(ValueError):
            Operand(kind=OperandKind.INDICATOR)

        op_ind = Operand(kind=OperandKind.INDICATOR, name="ema", params={"period": 20})
        self.assertEqual(op_ind.name, "ema")

    def test_strategy_ir_serialization(self):
        ir = StrategyIR(
            name="Test EMA Cross",
            base_timeframe="5m",
            min_data_quality=DataQuality.LEVEL_D_OHLCV_PROXY,
            entry_long=ConditionGroup(
                operator=LogicalOp.AND,
                nodes=[
                    ConditionNode(
                        left=Operand(kind=OperandKind.PRICE, name="close"),
                        operator=ComparisonOperator.GT,
                        right=Operand(kind=OperandKind.INDICATOR, name="ema", params={"period": 20}),
                    )
                ]
            )
        )
        data = ir.model_dump()
        self.assertEqual(data["name"], "Test EMA Cross")
        self.assertEqual(len(data["entry_long"]["nodes"]), 1)


class TestComponentRegistry(unittest.TestCase):
    def test_built_in_components(self):
        ema = ComponentRegistry.get("ema")
        self.assertIsNotNone(ema)
        self.assertEqual(ema.category, "indicator")
        self.assertEqual(ema.min_data_quality, DataQuality.LEVEL_D_OHLCV_PROXY)

        stacked_imb = ComponentRegistry.get("footprint_stacked_imbalance_buy")
        self.assertIsNotNone(stacked_imb)
        self.assertEqual(stacked_imb.category, "order_flow")
        self.assertEqual(stacked_imb.min_data_quality, DataQuality.LEVEL_A_EXCHANGE_VERIFIED)

    def test_parameter_validation(self):
        # EMA period must be >= 1
        with self.assertRaises(ValueError):
            ComponentRegistry.validate_operand("indicator", "ema", {"period": 0})

        comp = ComponentRegistry.validate_operand("indicator", "ema", {"period": 14})
        self.assertEqual(comp.name, "ema")


class TestStrategyCompiler(unittest.TestCase):
    def test_provenance_enforcement(self):
        # Strategy using stacked order flow imbalances requires LEVEL_A
        ir = StrategyIR(
            name="Order Flow Imbalance Strategy",
            entry_long=ConditionGroup(
                nodes=[
                    ConditionNode(
                        left=Operand(kind=OperandKind.ORDER_FLOW, name="footprint_stacked_imbalance_buy"),
                        operator=ComparisonOperator.GTE,
                        right=Operand(kind=OperandKind.CONSTANT, value=3.0),
                    )
                ]
            )
        )

        # Compiling for an environment with only LEVEL_D (OHLCV proxy) must raise ProvenanceIncompatibilityError
        compiler_low = StrategyCompiler(target_feed_quality=DataQuality.LEVEL_D_OHLCV_PROXY)
        with self.assertRaises(ProvenanceIncompatibilityError):
            compiler_low.compile(ir)

        # Compiling for LEVEL_A must succeed
        compiler_high = StrategyCompiler(target_feed_quality=DataQuality.LEVEL_A_EXCHANGE_VERIFIED)
        compiled = compiler_high.compile(ir)
        self.assertEqual(compiled.highest_required_quality, DataQuality.LEVEL_A_EXCHANGE_VERIFIED)
        self.assertIn("footprint", compiled.required_feeds)

    def test_ast_evaluation_and_entry_triggers(self):
        # Strategy: Buy when close > ema_20 AND rsi_14 > 50
        ir = StrategyIR(
            name="Momentum Breakout",
            entry_long=ConditionGroup(
                operator=LogicalOp.AND,
                nodes=[
                    ConditionNode(
                        left=Operand(kind=OperandKind.PRICE, name="close"),
                        operator=ComparisonOperator.GT,
                        right=Operand(kind=OperandKind.INDICATOR, name="ema", params={"period": 20}),
                    ),
                    ConditionNode(
                        left=Operand(kind=OperandKind.INDICATOR, name="rsi", params={"period": 14}),
                        operator=ComparisonOperator.GT,
                        right=Operand(kind=OperandKind.CONSTANT, value=50.0),
                    ),
                ]
            ),
            exit_long=ConditionGroup(
                nodes=[
                    ConditionNode(
                        left=Operand(kind=OperandKind.PRICE, name="close"),
                        operator=ComparisonOperator.LT,
                        right=Operand(kind=OperandKind.INDICATOR, name="ema", params={"period": 20}),
                    )
                ]
            )
        )

        compiler = StrategyCompiler()
        compiled = compiler.compile(ir)

        # Context 1: close = 105, ema = 100, rsi = 60 -> Trigger Long
        ctx1 = EvaluationContext(
            symbol="RELIANCE",
            timestamp_utc=1000,
            current_candle={"open": 101, "high": 106, "low": 100, "close": 105, "volume": 1000},
            indicator_values={"ema_20": 100.0, "rsi_14": 60.0},
        )
        self.assertEqual(compiled.evaluate_entry(ctx1), ActionKind.ENTER_LONG)

        # Context 2: close = 98, ema = 100, rsi = 40 -> No entry
        ctx2 = EvaluationContext(
            symbol="RELIANCE",
            timestamp_utc=2000,
            current_candle={"open": 101, "high": 102, "low": 97, "close": 98, "volume": 1000},
            indicator_values={"ema_20": 100.0, "rsi_14": 40.0},
        )
        self.assertIsNone(compiled.evaluate_entry(ctx2))

        # Context 2 with active LONG position -> Triggers exit
        ctx2.active_position = "LONG"
        self.assertEqual(compiled.evaluate_exit(ctx2), ActionKind.EXIT_LONG)


if __name__ == "__main__":
    unittest.main()
