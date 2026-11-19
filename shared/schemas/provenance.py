"""STRATLAB Core Domain: Data Quality & Provenance Taxonomy.

Defines the 4-level data quality classification, aggressor-side tagging,
and provenance metadata models required to maintain an immutable boundary
between genuine trade records and synthetic estimations.
"""

from enum import Enum, IntEnum
from pydantic import BaseModel, ConfigDict, Field, model_validator


class DataQuality(IntEnum):
    """
    Hierarchical classification of market data fidelity.

    Level A (Exchange Verified): Direct exchange trade prints with aggressor flags.
    Level B (Quote Classified): Actual trades matched against contemporaneous Top-of-Book quotes.
    Level C (Tick Rule Estimated): Direction inferred via Lee-Ready tick rule on trade series.
    Level D (OHLCV Proxy): Synthetic volume distribution derived from aggregate candle geometry.
    """
    LEVEL_A_EXCHANGE_VERIFIED = 1
    LEVEL_B_QUOTE_CLASSIFIED = 2
    LEVEL_C_TICK_RULE = 3
    LEVEL_D_OHLCV_PROXY = 4


class AggressorSide(str, Enum):
    """Execution side of a trade aggressor."""
    BUY = "BUY"         # Aggressive buyer executed at the Ask
    SELL = "SELL"       # Aggressive seller executed at the Bid
    UNKNOWN = "UNKNOWN" # Cross-trade, batch auction match, or unclassified


class SideMethod(str, Enum):
    """Algorithm or source used to determine the aggressor side."""
    EXCHANGE_FLAG = "EXCHANGE_FLAG"
    QUOTE_BBO = "QUOTE_BBO"
    TICK_RULE = "TICK_RULE"
    BVC_SYNTHETIC = "BVC_SYNTHETIC"
    UNKNOWN = "UNKNOWN"


class ProvenanceMetadata(BaseModel):
    """
    Immutable provenance metadata attached to every trade, cluster, and order flow aggregate.
    """
    model_config = ConfigDict(frozen=True, extra="forbid")

    quality: DataQuality = Field(
        ...,
        description="Fidelity tier of the data (Level A to Level D)."
    )
    side_method: SideMethod = Field(
        ...,
        description="Mechanism used to determine buy/sell direction."
    )
    source_id: str = Field(
        ...,
        min_length=1,
        max_length=64,
        description="Identifier of originating feed (e.g. NSE_TBT, ZERODHA_WS, YAHOO_HIST)."
    )
    confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Confidence score (1.0 = exchange certified, 0.35 = proxy model)."
    )
    is_estimated: bool = Field(
        ...,
        description="True for synthetic estimations (Levels C & D); False for genuine data (Levels A & B)."
    )

    @model_validator(mode="after")
    def verify_consistency(self) -> "ProvenanceMetadata":
        """Enforce strict consistency between quality tier and estimation flag."""
        expected_estimated = self.quality in (
            DataQuality.LEVEL_C_TICK_RULE,
            DataQuality.LEVEL_D_OHLCV_PROXY,
        )
        if self.is_estimated != expected_estimated:
            raise ValueError(
                f"Data quality {self.quality.name} requires is_estimated={expected_estimated}, "
                f"got {self.is_estimated}"
            )
        return self

    @classmethod
    def exchange_verified(cls, source_id: str = "EXCHANGE") -> "ProvenanceMetadata":
        return cls(
            quality=DataQuality.LEVEL_A_EXCHANGE_VERIFIED,
            side_method=SideMethod.EXCHANGE_FLAG,
            source_id=source_id,
            confidence=1.0,
            is_estimated=False,
        )

    @classmethod
    def quote_classified(cls, source_id: str = "BBO_MATCH", confidence: float = 0.90) -> "ProvenanceMetadata":
        return cls(
            quality=DataQuality.LEVEL_B_QUOTE_CLASSIFIED,
            side_method=SideMethod.QUOTE_BBO,
            source_id=source_id,
            confidence=confidence,
            is_estimated=False,
        )

    @classmethod
    def tick_rule_estimated(cls, source_id: str = "TICK_RULE", confidence: float = 0.65) -> "ProvenanceMetadata":
        return cls(
            quality=DataQuality.LEVEL_C_TICK_RULE,
            side_method=SideMethod.TICK_RULE,
            source_id=source_id,
            confidence=confidence,
            is_estimated=True,
        )

    @classmethod
    def ohlcv_proxy(cls, source_id: str = "OHLCV_PROXY", confidence: float = 0.35) -> "ProvenanceMetadata":
        return cls(
            quality=DataQuality.LEVEL_D_OHLCV_PROXY,
            side_method=SideMethod.BVC_SYNTHETIC,
            source_id=source_id,
            confidence=confidence,
            is_estimated=True,
        )
