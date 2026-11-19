"""STRATLAB Component Registry for Indicators, Order Flow, and SMC Features."""

from __future__ import annotations
from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field
from shared.schemas.provenance import DataQuality


class ParameterDefinition(BaseModel):
    name: str
    type: Literal["int", "float", "string", "bool"]
    default: Any
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    options: Optional[List[str]] = None
    description: Optional[str] = None


class ComponentDefinition(BaseModel):
    name: str
    category: Literal["price", "indicator", "order_flow", "smc"]
    display_name: str
    description: str
    required_feed: Literal["candle", "trade_ticks", "order_book", "footprint"]
    min_data_quality: DataQuality
    parameters: Dict[str, ParameterDefinition] = Field(default_factory=dict)
    output_type: Literal["numeric", "boolean", "level"] = "numeric"


class ComponentRegistry:
    """
    Central registry of available Strategy IR building blocks.
    Enforces required input data feeds and minimum provenance levels.
    """
    _registry: Dict[str, ComponentDefinition] = {}

    @classmethod
    def register(cls, definition: ComponentDefinition) -> None:
        cls._registry[definition.name.lower()] = definition

    @classmethod
    def get(cls, name: str) -> Optional[ComponentDefinition]:
        return cls._registry.get(name.lower())

    @classmethod
    def list_all(cls) -> List[ComponentDefinition]:
        return list(cls._registry.values())

    @classmethod
    def list_by_category(cls, category: str) -> List[ComponentDefinition]:
        return [c for c in cls._registry.values() if c.category == category]

    @classmethod
    def validate_operand(cls, kind: str, name: str, params: Dict[str, Any]) -> ComponentDefinition:
        """Verify that an operand references a known component with valid parameters."""
        comp = cls.get(name)
        if not comp:
            raise ValueError(f"Unknown component '{name}' in category '{kind}'")
        
        # Verify required parameters
        for p_name, p_def in comp.parameters.items():
            if p_name in params:
                val = params[p_name]
                if p_def.min_value is not None and val < p_def.min_value:
                    raise ValueError(f"Parameter '{p_name}' for '{name}' must be >= {p_def.min_value}")
                if p_def.max_value is not None and val > p_def.max_value:
                    raise ValueError(f"Parameter '{p_name}' for '{name}' must be <= {p_def.max_value}")
        return comp


# --- Default Registry Population ---

# 1. Price fields
for p_field in ["open", "high", "low", "close", "volume", "hl2", "hlc3", "ohlc4"]:
    ComponentRegistry.register(ComponentDefinition(
        name=p_field,
        category="price",
        display_name=p_field.upper(),
        description=f"Standard bar {p_field} price/volume",
        required_feed="candle",
        min_data_quality=DataQuality.LEVEL_D_OHLCV_PROXY,
        output_type="numeric" if p_field != "volume" else "numeric",
    ))

# 2. Technical Indicators
ComponentRegistry.register(ComponentDefinition(
    name="sma",
    category="indicator",
    display_name="Simple Moving Average",
    description="Unweighted arithmetic mean of price over period",
    required_feed="candle",
    min_data_quality=DataQuality.LEVEL_D_OHLCV_PROXY,
    parameters={"period": ParameterDefinition(name="period", type="int", default=20, min_value=1)},
    output_type="numeric",
))

ComponentRegistry.register(ComponentDefinition(
    name="ema",
    category="indicator",
    display_name="Exponential Moving Average",
    description="Exponentially weighted moving average giving higher weight to recent prices",
    required_feed="candle",
    min_data_quality=DataQuality.LEVEL_D_OHLCV_PROXY,
    parameters={"period": ParameterDefinition(name="period", type="int", default=20, min_value=1)},
    output_type="numeric",
))

ComponentRegistry.register(ComponentDefinition(
    name="rsi",
    category="indicator",
    display_name="Relative Strength Index",
    description="Momentum oscillator measuring velocity and magnitude of price changes (0-100)",
    required_feed="candle",
    min_data_quality=DataQuality.LEVEL_D_OHLCV_PROXY,
    parameters={"period": ParameterDefinition(name="period", type="int", default=14, min_value=2)},
    output_type="numeric",
))

ComponentRegistry.register(ComponentDefinition(
    name="macd",
    category="indicator",
    display_name="MACD Line",
    description="Moving Average Convergence Divergence line (fast - slow EMA)",
    required_feed="candle",
    min_data_quality=DataQuality.LEVEL_D_OHLCV_PROXY,
    parameters={
        "fast_period": ParameterDefinition(name="fast_period", type="int", default=12, min_value=1),
        "slow_period": ParameterDefinition(name="slow_period", type="int", default=26, min_value=1),
    },
    output_type="numeric",
))

ComponentRegistry.register(ComponentDefinition(
    name="macd_signal",
    category="indicator",
    display_name="MACD Signal",
    description="Signal line of MACD (EMA of MACD line)",
    required_feed="candle",
    min_data_quality=DataQuality.LEVEL_D_OHLCV_PROXY,
    parameters={
        "fast_period": ParameterDefinition(name="fast_period", type="int", default=12, min_value=1),
        "slow_period": ParameterDefinition(name="slow_period", type="int", default=26, min_value=1),
        "signal_period": ParameterDefinition(name="signal_period", type="int", default=9, min_value=1),
    },
    output_type="numeric",
))

ComponentRegistry.register(ComponentDefinition(
    name="atr",
    category="indicator",
    display_name="Average True Range",
    description="Market volatility indicator based on High-Low-Close true ranges",
    required_feed="candle",
    min_data_quality=DataQuality.LEVEL_D_OHLCV_PROXY,
    parameters={"period": ParameterDefinition(name="period", type="int", default=14, min_value=1)},
    output_type="numeric",
))

ComponentRegistry.register(ComponentDefinition(
    name="vwap",
    category="indicator",
    display_name="Volume Weighted Average Price",
    description="Benchmark price representing the average price weighted by volume",
    required_feed="candle",
    min_data_quality=DataQuality.LEVEL_D_OHLCV_PROXY,
    parameters={"reset_period": ParameterDefinition(name="reset_period", type="string", default="session", options=["session", "week", "month"])},
    output_type="numeric",
))

# 3. Order Flow Metrics (Requires genuine ticks or high-confidence quotes)
ComponentRegistry.register(ComponentDefinition(
    name="bar_delta",
    category="order_flow",
    display_name="Bar Delta",
    description="Net aggressive volume (Ask Volume - Bid Volume) of the bar",
    required_feed="trade_ticks",
    min_data_quality=DataQuality.LEVEL_B_QUOTE_CLASSIFIED,
    output_type="numeric",
))

ComponentRegistry.register(ComponentDefinition(
    name="cvd",
    category="order_flow",
    display_name="Cumulative Volume Delta",
    description="Running cumulative sum of bar delta with session resets",
    required_feed="trade_ticks",
    min_data_quality=DataQuality.LEVEL_B_QUOTE_CLASSIFIED,
    parameters={"reset_session": ParameterDefinition(name="reset_session", type="bool", default=True)},
    output_type="numeric",
))

ComponentRegistry.register(ComponentDefinition(
    name="cvd_divergence",
    category="order_flow",
    display_name="CVD Divergence State",
    description="Absorption divergence indicator ('BULLISH_ABSORPTION', 'BEARISH_ABSORPTION', 'NONE')",
    required_feed="trade_ticks",
    min_data_quality=DataQuality.LEVEL_B_QUOTE_CLASSIFIED,
    parameters={"lookback": ParameterDefinition(name="lookback", type="int", default=5, min_value=2)},
    output_type="numeric", # string/enum coded
))

ComponentRegistry.register(ComponentDefinition(
    name="footprint_stacked_imbalance_buy",
    category="order_flow",
    display_name="Footprint Stacked Buy Imbalances",
    description="Count of consecutive price levels with ask volume > 3x lower-bid volume",
    required_feed="footprint",
    min_data_quality=DataQuality.LEVEL_A_EXCHANGE_VERIFIED,
    parameters={
        "ratio": ParameterDefinition(name="ratio", type="float", default=3.0, min_value=1.5),
        "min_stacked": ParameterDefinition(name="min_stacked", type="int", default=3, min_value=2),
    },
    output_type="numeric",
))

ComponentRegistry.register(ComponentDefinition(
    name="footprint_stacked_imbalance_sell",
    category="order_flow",
    display_name="Footprint Stacked Sell Imbalances",
    description="Count of consecutive price levels with bid volume > 3x higher-ask volume",
    required_feed="footprint",
    min_data_quality=DataQuality.LEVEL_A_EXCHANGE_VERIFIED,
    parameters={
        "ratio": ParameterDefinition(name="ratio", type="float", default=3.0, min_value=1.5),
        "min_stacked": ParameterDefinition(name="min_stacked", type="int", default=3, min_value=2),
    },
    output_type="numeric",
))

ComponentRegistry.register(ComponentDefinition(
    name="volume_profile_poc",
    category="order_flow",
    display_name="Volume Profile Point of Control",
    description="Price level with the highest accumulated volume",
    required_feed="trade_ticks",
    min_data_quality=DataQuality.LEVEL_C_TICK_RULE,
    output_type="level",
))

ComponentRegistry.register(ComponentDefinition(
    name="volume_profile_vah",
    category="order_flow",
    display_name="Volume Profile Value Area High",
    description="Upper bound of 70% value area",
    required_feed="trade_ticks",
    min_data_quality=DataQuality.LEVEL_C_TICK_RULE,
    output_type="level",
))

ComponentRegistry.register(ComponentDefinition(
    name="volume_profile_val",
    category="order_flow",
    display_name="Volume Profile Value Area Low",
    description="Lower bound of 70% value area",
    required_feed="trade_ticks",
    min_data_quality=DataQuality.LEVEL_C_TICK_RULE,
    output_type="level",
))

# 4. Smart Money Concepts (SMC)
ComponentRegistry.register(ComponentDefinition(
    name="bos",
    category="smc",
    display_name="Break of Structure (BOS)",
    description="Continuation break of swing high or swing low in trend direction",
    required_feed="candle",
    min_data_quality=DataQuality.LEVEL_D_OHLCV_PROXY,
    parameters={"swing_lookback": ParameterDefinition(name="swing_lookback", type="int", default=3, min_value=1)},
    output_type="boolean",
))

ComponentRegistry.register(ComponentDefinition(
    name="choch",
    category="smc",
    display_name="Change of Character (CHoCH)",
    description="Trend reversal break of swing high or swing low against trend direction",
    required_feed="candle",
    min_data_quality=DataQuality.LEVEL_D_OHLCV_PROXY,
    parameters={"swing_lookback": ParameterDefinition(name="swing_lookback", type="int", default=3, min_value=1)},
    output_type="boolean",
))

ComponentRegistry.register(ComponentDefinition(
    name="fvg_bullish",
    category="smc",
    display_name="Bullish Fair Value Gap",
    description="3-candle imbalance void between Candle 1 High and Candle 3 Low",
    required_feed="candle",
    min_data_quality=DataQuality.LEVEL_D_OHLCV_PROXY,
    output_type="boolean",
))

ComponentRegistry.register(ComponentDefinition(
    name="fvg_bearish",
    category="smc",
    display_name="Bearish Fair Value Gap",
    description="3-candle imbalance void between Candle 1 Low and Candle 3 High",
    required_feed="candle",
    min_data_quality=DataQuality.LEVEL_D_OHLCV_PROXY,
    output_type="boolean",
))
