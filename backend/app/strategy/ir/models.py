"""STRATLAB Strategy IR Models and Domain Contracts."""

from __future__ import annotations
from enum import Enum
from typing import Any, Dict, List, Literal, Optional, Union
from pydantic import BaseModel, Field, model_validator
from shared.schemas.provenance import DataQuality
from shared.schemas.instrument import AssetClass


class OperandKind(str, Enum):
    PRICE = "price"
    INDICATOR = "indicator"
    ORDER_FLOW = "order_flow"
    SMC = "smc"
    CONSTANT = "constant"


class ComparisonOperator(str, Enum):
    GT = ">"
    LT = "<"
    GTE = ">="
    LTE = "<="
    EQ = "=="
    NEQ = "!="
    CROSSES_ABOVE = "crosses_above"
    CROSSES_BELOW = "crosses_below"
    IS_TRUE = "is_true"
    IS_FALSE = "is_false"
    WITHIN_RANGE = "within_range"
    DIVERGENCE_EQUALS = "divergence_equals"


class LogicalOp(str, Enum):
    AND = "AND"
    OR = "OR"


class ActionKind(str, Enum):
    ENTER_LONG = "ENTER_LONG"
    ENTER_SHORT = "ENTER_SHORT"
    EXIT_LONG = "EXIT_LONG"
    EXIT_SHORT = "EXIT_SHORT"
    MODIFY_STOP = "MODIFY_STOP"
    SCALE_IN = "SCALE_IN"
    SCALE_OUT = "SCALE_OUT"


class OrderType(str, Enum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    STOP = "STOP"
    STOP_LIMIT = "STOP_LIMIT"


class SizingMethod(str, Enum):
    PERCENT_RISK = "percent_risk"
    FIXED_QUANTITY = "fixed_quantity"
    FIXED_CASH = "fixed_cash"
    PORTFOLIO_PERCENT = "portfolio_percent"


class Operand(BaseModel):
    """Represents a variable, calculation, or constant in a condition."""
    kind: OperandKind
    name: Optional[str] = None  # e.g. "close", "ema", "delta", "cvd", "bos"
    params: Dict[str, Any] = Field(default_factory=dict)  # e.g. {"period": 14}
    value: Optional[float] = None  # For CONSTANT
    timeframe: Optional[str] = None  # None means inherit base timeframe; allows multi-timeframe
    offset: int = 0  # 0 = current bar, 1 = previous bar, etc.

    @model_validator(mode="after")
    def validate_operand(self) -> "Operand":
        if self.kind == OperandKind.CONSTANT:
            if self.value is None:
                raise ValueError("Operand of kind 'constant' must specify a numeric 'value'")
        else:
            if not self.name:
                raise ValueError(f"Operand of kind '{self.kind.value}' must specify a 'name'")
        return self


class ConditionNode(BaseModel):
    """A leaf condition comparing two operands or checking an assertion."""
    type: Literal["condition"] = "condition"
    left: Operand
    operator: ComparisonOperator
    right: Optional[Operand] = None  # None for unary checks like IS_TRUE / IS_FALSE
    right2: Optional[Operand] = None  # Used for WITHIN_RANGE (lower, upper)
    negate: bool = False
    description: Optional[str] = None


class ConditionGroup(BaseModel):
    """A recursive boolean combination of conditions and sub-groups."""
    type: Literal["group"] = "group"
    operator: LogicalOp = LogicalOp.AND
    negate: bool = False
    nodes: List[Union["ConditionGroup", ConditionNode]] = Field(default_factory=list)


# Update recursive forward references for ConditionGroup
ConditionGroup.model_rebuild()


class ActionNode(BaseModel):
    """The action to perform when trigger conditions are met."""
    action: ActionKind
    order_type: OrderType = OrderType.MARKET
    limit_offset_ticks: Optional[int] = None
    stop_offset_ticks: Optional[int] = None
    time_in_force: str = "DAY"  # "DAY", "GTC", "IOC"


class StopLossConfig(BaseModel):
    mode: Literal["pct", "atr", "swing", "level", "fixed_ticks", "none"] = "none"
    value: float = 0.0
    atr_period: int = 14
    level_operand: Optional[Operand] = None


class TakeProfitConfig(BaseModel):
    mode: Literal["pct", "atr", "risk_reward", "level", "fixed_ticks", "none"] = "none"
    value: float = 0.0  # e.g. 2.0 for 2R if mode == risk_reward
    level_operand: Optional[Operand] = None


class TrailingStopConfig(BaseModel):
    mode: Literal["pct", "atr", "step", "none"] = "none"
    activation_pct: float = 0.0
    trail_value: float = 0.0
    atr_period: int = 14


class RiskParams(BaseModel):
    stop_loss: StopLossConfig = Field(default_factory=StopLossConfig)
    take_profit: TakeProfitConfig = Field(default_factory=TakeProfitConfig)
    trailing_stop: TrailingStopConfig = Field(default_factory=TrailingStopConfig)
    max_hold_bars: Optional[int] = None
    daily_loss_limit: Optional[float] = None


class PortfolioParams(BaseModel):
    initial_capital: float = 100_000.0
    sizing_method: SizingMethod = SizingMethod.PERCENT_RISK
    risk_pct: float = 1.0  # Risk 1% of equity per trade
    fixed_quantity: int = 1
    fixed_cash: float = 10_000.0
    max_open_positions: int = 5
    max_capital_allocation_pct: float = 100.0


class UniverseConfig(BaseModel):
    mode: Literal["symbols", "universe"] = "symbols"
    symbols: List[str] = Field(default_factory=list)
    exchanges: List[str] = Field(default_factory=lambda: ["NSE"])
    asset_classes: List[AssetClass] = Field(default_factory=lambda: [AssetClass.EQUITY])
    min_volume: Optional[float] = None
    min_turnover: Optional[float] = None


class ExecutionParams(BaseModel):
    fill_model: Literal["immediate", "next_open", "queue_aware", "touch"] = "queue_aware"
    slippage_ticks: int = 1
    commission_profile: Literal["india_delivery", "india_intraday", "crypto_futures", "zero_fee"] = "india_intraday"


class StrategyIR(BaseModel):
    """
    STRATLAB Intermediate Representation (IR).
    Universal declarative strategy specification compiled from Visual Blocks or Chart UI.
    """
    version: int = 1
    id: Optional[str] = None
    name: str
    description: Optional[str] = None
    author: Optional[str] = None
    tags: List[str] = Field(default_factory=list)

    # Operational constraints
    universe: UniverseConfig = Field(default_factory=UniverseConfig)
    base_timeframe: str = "5m"
    min_data_quality: DataQuality = DataQuality.LEVEL_C_TICK_RULE  # Minimum required feed quality

    # Strategy rules
    entry_long: Optional[ConditionGroup] = None
    entry_short: Optional[ConditionGroup] = None
    exit_long: Optional[ConditionGroup] = None
    exit_short: Optional[ConditionGroup] = None

    # Execution & Risk
    action: ActionNode = Field(default_factory=lambda: ActionNode(action=ActionKind.ENTER_LONG))
    risk: RiskParams = Field(default_factory=RiskParams)
    portfolio: PortfolioParams = Field(default_factory=PortfolioParams)
    execution: ExecutionParams = Field(default_factory=ExecutionParams)
