"""STRATLAB Shared Domain Schemas Package."""

from .execution import (
    OrderSide,
    OrderStatus,
    OrderType,
    PaperAccount,
    PaperFill,
    PaperOrder,
    PaperPosition,
)
from .instrument import AssetClass, InstrumentMaster, OptionType
from .market_data import BookLevel, Candle, OrderBookDepth, TradeTick
from .order_flow import CVDPoint, FootprintBar, PriceCluster, VolumeProfile
from .provenance import (
    AggressorSide,
    DataQuality,
    ProvenanceMetadata,
    SideMethod,
)

__all__ = [
    # Provenance
    "DataQuality",
    "AggressorSide",
    "SideMethod",
    "ProvenanceMetadata",
    # Instrument
    "AssetClass",
    "OptionType",
    "InstrumentMaster",
    # Market Data
    "Candle",
    "TradeTick",
    "BookLevel",
    "OrderBookDepth",
    # Order Flow
    "PriceCluster",
    "FootprintBar",
    "VolumeProfile",
    "CVDPoint",
    # Execution
    "OrderType",
    "OrderStatus",
    "OrderSide",
    "PaperOrder",
    "PaperFill",
    "PaperPosition",
    "PaperAccount",
]
