"""STRATLAB Strategy Compiler Subsystem.

Validates Strategy IR against the Component Registry, enforces data quality
provenance boundaries, and compiles declarative AST condition trees into
high-performance runtime evaluation structures.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Set
from shared.schemas.provenance import DataQuality
from backend.app.strategy.ir.models import (
    ActionKind,
    ComparisonOperator,
    ConditionGroup,
    ConditionNode,
    LogicalOp,
    Operand,
    OperandKind,
    StrategyIR,
)
from backend.app.strategy.registry.components import ComponentRegistry


class ProvenanceIncompatibilityError(ValueError):
    """Raised when strategy requires a higher data quality than available."""
    pass


class StrategyCompilationError(ValueError):
    """Raised when Strategy IR is invalid or fails syntactic validation."""
    pass


@dataclass
class EvaluationContext:
    """
    Market snapshot passed to compiled strategy evaluators at each bar or tick.
    """
    symbol: str
    timestamp_utc: int
    current_candle: Dict[str, float]  # open, high, low, close, volume
    previous_candle: Optional[Dict[str, float]] = None
    indicator_values: Dict[str, float] = field(default_factory=dict)
    order_flow_values: Dict[str, float] = field(default_factory=dict)
    smc_values: Dict[str, Any] = field(default_factory=dict)
    active_position: Optional[str] = None  # None, "LONG", "SHORT"


# Quality rank mapping: Level A is highest quality (most strict), Level D is lowest
QUALITY_RANK = {
    DataQuality.LEVEL_A_EXCHANGE_VERIFIED: 4,
    DataQuality.LEVEL_B_QUOTE_CLASSIFIED: 3,
    DataQuality.LEVEL_C_TICK_RULE: 2,
    DataQuality.LEVEL_D_OHLCV_PROXY: 1,
}


@dataclass
class CompiledStrategy:
    """
    Executable compiled strategy structure ready for historical backtest or live execution.
    """
    ir: StrategyIR
    required_feeds: Set[str]
    highest_required_quality: DataQuality
    required_indicators: List[Dict[str, Any]]
    entry_long_evaluator: Optional[Callable[[EvaluationContext], bool]]
    entry_short_evaluator: Optional[Callable[[EvaluationContext], bool]]
    exit_long_evaluator: Optional[Callable[[EvaluationContext], bool]]
    exit_short_evaluator: Optional[Callable[[EvaluationContext], bool]]

    def evaluate_entry(self, ctx: EvaluationContext) -> Optional[ActionKind]:
        """Evaluate entry triggers on current context."""
        if self.entry_long_evaluator and self.entry_long_evaluator(ctx):
            return ActionKind.ENTER_LONG
        if self.entry_short_evaluator and self.entry_short_evaluator(ctx):
            return ActionKind.ENTER_SHORT
        return None

    def evaluate_exit(self, ctx: EvaluationContext) -> Optional[ActionKind]:
        """Evaluate exit rules on active positions."""
        if ctx.active_position == "LONG" and self.exit_long_evaluator and self.exit_long_evaluator(ctx):
            return ActionKind.EXIT_LONG
        if ctx.active_position == "SHORT" and self.exit_short_evaluator and self.exit_short_evaluator(ctx):
            return ActionKind.EXIT_SHORT
        return None


class StrategyCompiler:
    """
    Compiles Strategy IR specifications into runtime evaluator ASTs.
    """

    def __init__(self, target_feed_quality: Optional[DataQuality] = None):
        """
        :param target_feed_quality: Optional available feed quality in execution environment.
                                    If specified, guarantees strategy does not exceed it.
        """
        self.target_feed_quality = target_feed_quality

    def compile(self, ir: StrategyIR) -> CompiledStrategy:
        """
        Validate, extract dependencies, verify provenance, and compile AST.
        """
        required_feeds: Set[str] = set()
        highest_quality = DataQuality.LEVEL_D_OHLCV_PROXY
        required_indicators: List[Dict[str, Any]] = []

        # 1. Walk and inspect all operand dependencies in the IR
        def inspect_operand(op: Optional[Operand], path: str):
            nonlocal highest_quality
            if op is None or op.kind == OperandKind.CONSTANT:
                return

            if op.kind == OperandKind.PRICE:
                required_feeds.add("candle")
                return

            # Lookup component in registry
            comp = ComponentRegistry.get(op.name or "")
            if not comp:
                raise StrategyCompilationError(f"Component '{op.name}' at path '{path}' is not registered")

            # Check min quality
            if QUALITY_RANK[comp.min_data_quality] > QUALITY_RANK[highest_quality]:
                highest_quality = comp.min_data_quality

            required_feeds.add(comp.required_feed)

            if comp.category == "indicator":
                required_indicators.append({
                    "name": comp.name,
                    "params": op.params,
                    "timeframe": op.timeframe or ir.base_timeframe,
                })

        def inspect_group(group: Optional[ConditionGroup], path: str):
            if not group or not group.nodes:
                return
            for idx, node in enumerate(group.nodes):
                node_path = f"{path}.nodes[{idx}]"
                if isinstance(node, ConditionGroup):
                    inspect_group(node, node_path)
                elif isinstance(node, ConditionNode):
                    inspect_operand(node.left, f"{node_path}.left")
                    inspect_operand(node.right, f"{node_path}.right")
                    inspect_operand(node.right2, f"{node_path}.right2")

        inspect_group(ir.entry_long, "entry_long")
        inspect_group(ir.entry_short, "entry_short")
        inspect_group(ir.exit_long, "exit_long")
        inspect_group(ir.exit_short, "exit_short")

        # 2. Provenance compatibility check
        # Strategy user specified min_data_quality vs actual required quality
        if QUALITY_RANK[highest_quality] > QUALITY_RANK[ir.min_data_quality]:
            # IR requires more stringent quality than declared
            ir.min_data_quality = highest_quality

        if self.target_feed_quality:
            if QUALITY_RANK[highest_quality] > QUALITY_RANK[self.target_feed_quality]:
                raise ProvenanceIncompatibilityError(
                    f"Strategy '{ir.name}' requires data quality {highest_quality.value} "
                    f"due to order flow/components, but available environment feed is only {self.target_feed_quality.value}."
                )

        # 3. Build fast evaluator functions
        entry_long_eval = self._compile_group(ir.entry_long) if ir.entry_long else None
        entry_short_eval = self._compile_group(ir.entry_short) if ir.entry_short else None
        exit_long_eval = self._compile_group(ir.exit_long) if ir.exit_long else None
        exit_short_eval = self._compile_group(ir.exit_short) if ir.exit_short else None

        return CompiledStrategy(
            ir=ir,
            required_feeds=required_feeds,
            highest_required_quality=highest_quality,
            required_indicators=required_indicators,
            entry_long_evaluator=entry_long_eval,
            entry_short_evaluator=entry_short_eval,
            exit_long_evaluator=exit_long_eval,
            exit_short_evaluator=exit_short_eval,
        )

    def _compile_operand_getter(self, op: Operand) -> Callable[[EvaluationContext], Any]:
        """Produce a fast callable resolving the operand against the EvaluationContext."""
        if op.kind == OperandKind.CONSTANT:
            c_val = op.value
            return lambda ctx: c_val

        name = op.name or ""
        offset = op.offset

        if op.kind == OperandKind.PRICE:
            # Resolves from current_candle or previous_candle
            price_field = name.lower()
            if offset == 0:
                return lambda ctx: ctx.current_candle.get(price_field, 0.0)
            elif offset == 1:
                return lambda ctx: (ctx.previous_candle.get(price_field, 0.0) if ctx.previous_candle else 0.0)
            else:
                return lambda ctx: ctx.current_candle.get(price_field, 0.0)

        elif op.kind == OperandKind.INDICATOR:
            # Identifier in ctx.indicator_values, e.g. "ema_20" or "rsi_14"
            key = f"{name}_{op.params.get('period', '')}" if 'period' in op.params else name
            return lambda ctx: ctx.indicator_values.get(key, ctx.indicator_values.get(name, 0.0))

        elif op.kind == OperandKind.ORDER_FLOW:
            key = name
            return lambda ctx: ctx.order_flow_values.get(key, 0.0)

        elif op.kind == OperandKind.SMC:
            key = name
            return lambda ctx: ctx.smc_values.get(key, False)

        return lambda ctx: 0.0

    def _compile_node(self, node: ConditionNode) -> Callable[[EvaluationContext], bool]:
        """Compile a leaf ConditionNode into a boolean predicate."""
        get_left = self._compile_operand_getter(node.left)
        get_right = self._compile_operand_getter(node.right) if node.right else None
        get_right2 = self._compile_operand_getter(node.right2) if node.right2 else None
        op = node.operator

        def predicate(ctx: EvaluationContext) -> bool:
            l_val = get_left(ctx)
            r_val = get_right(ctx) if get_right else None

            if op == ComparisonOperator.GT:
                res = l_val > r_val
            elif op == ComparisonOperator.LT:
                res = l_val < r_val
            elif op == ComparisonOperator.GTE:
                res = l_val >= r_val
            elif op == ComparisonOperator.LTE:
                res = l_val <= r_val
            elif op == ComparisonOperator.EQ:
                res = l_val == r_val
            elif op == ComparisonOperator.NEQ:
                res = l_val != r_val
            elif op == ComparisonOperator.IS_TRUE:
                res = bool(l_val)
            elif op == ComparisonOperator.IS_FALSE:
                res = not bool(l_val)
            elif op == ComparisonOperator.CROSSES_ABOVE:
                # Requires prev bar comparison if tracked or value comparison
                # Standard convention: prev_l <= prev_r and cur_l > cur_r
                prev_l_val = ctx.previous_candle.get(node.left.name, 0.0) if ctx.previous_candle and node.left.kind == OperandKind.PRICE else l_val
                prev_r_val = ctx.previous_candle.get(node.right.name, 0.0) if ctx.previous_candle and node.right and node.right.kind == OperandKind.PRICE else r_val
                res = (l_val > r_val) and (prev_l_val <= prev_r_val)
            elif op == ComparisonOperator.CROSSES_BELOW:
                prev_l_val = ctx.previous_candle.get(node.left.name, 0.0) if ctx.previous_candle and node.left.kind == OperandKind.PRICE else l_val
                prev_r_val = ctx.previous_candle.get(node.right.name, 0.0) if ctx.previous_candle and node.right and node.right.kind == OperandKind.PRICE else r_val
                res = (l_val < r_val) and (prev_l_val >= prev_r_val)
            elif op == ComparisonOperator.WITHIN_RANGE:
                r2_val = get_right2(ctx) if get_right2 else r_val
                res = r_val <= l_val <= r2_val
            elif op == ComparisonOperator.DIVERGENCE_EQUALS:
                res = str(l_val) == str(node.right.name if node.right else r_val)
            else:
                res = False

            return not res if node.negate else res

        return predicate

    def _compile_group(self, group: ConditionGroup) -> Callable[[EvaluationContext], bool]:
        """Recursively compile a ConditionGroup into a single boolean evaluator."""
        compiled_children: List[Callable[[EvaluationContext], bool]] = []

        for child in group.nodes:
            if isinstance(child, ConditionGroup):
                compiled_children.append(self._compile_group(child))
            elif isinstance(child, ConditionNode):
                compiled_children.append(self._compile_node(child))

        is_and = group.operator == LogicalOp.AND
        is_negate = group.negate

        def group_evaluator(ctx: EvaluationContext) -> bool:
            if not compiled_children:
                return True

            if is_and:
                for fn in compiled_children:
                    if not fn(ctx):
                        return True if is_negate else False
                return False if is_negate else True
            else:
                for fn in compiled_children:
                    if fn(ctx):
                        return False if is_negate else True
                return True if is_negate else False

        return group_evaluator
