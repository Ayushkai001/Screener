"""STRATLAB Core Domain: Market Data Entities.

Normalized schemas for Candlestick (OHLCV), Individual Trade Ticks,
and Order Book Market Depth with embedded provenance.
"""

from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field, model_validator

from .provenance import AggressorSide, ProvenanceMetadata


class Candle(BaseModel):
    """
    Standard normalized OHLCV candle entity.
    Timestamps are stored in UTC milliseconds.
    """
    model_config = ConfigDict(frozen=True, extra="forbid")

    instrument_id: str = Field(..., description="Target instrument identifier.")
    timestamp_utc: int = Field(..., description="Start of candle window in UTC epoch milliseconds.")
    timeframe: str = Field(..., pattern=r"^\d+[smhdwM]$", description="Standard timeframe code (e.g. 1m, 5m, 1d).")
    open: float = Field(..., gt=0.0, description="Opening price.")
    high: float = Field(..., gt=0.0, description="Highest price traded.")
    low: float = Field(..., gt=0.0, description="Lowest price traded.")
    close: float = Field(..., gt=0.0, description="Closing price.")
    volume: int = Field(..., ge=0, description="Total traded volume.")
    turnover: float = Field(default=0.0, ge=0.0, description="Total turnover in quote currency.")
    provenance: ProvenanceMetadata = Field(..., description="Data provenance & quality classification.")

    @model_validator(mode="after")
    def validate_ohlc_consistency(self) -> "Candle":
        """Verify standard OHLC envelope invariants."""
        if self.high < self.low:
            raise ValueError(f"High ({self.high}) cannot be lower than Low ({self.low}).")
        if self.high < self.open or self.high < self.close:
            raise ValueError(f"High ({self.high}) must be >= Open ({self.open}) and Close ({self.close}).")
        if self.low > self.open or self.low > self.close:
            raise ValueError(f"Low ({self.low}) must be <= Open ({self.open}) and Close ({self.close}).")
        return self


class TradeTick(BaseModel):
    """
    Normalized individual trade print.
    """
    model_config = ConfigDict(frozen=True, extra="forbid")

    instrument_id: str = Field(..., description="Target instrument identifier.")
    timestamp_ns: int = Field(..., description="Exchange execution timestamp in nanoseconds UTC.")
    price: float = Field(..., gt=0.0, description="Executed trade price.")
    quantity: int = Field(..., gt=0, description="Trade volume.")
    aggressor: AggressorSide = Field(..., description="Trade side (BUY=Ask, SELL=Bid, UNKNOWN).")
    bid: Optional[float] = Field(default=None, gt=0.0, description="Best Bid at execution time.")
    ask: Optional[float] = Field(default=None, gt=0.0, description="Best Ask at execution time.")
    sequence_id: Optional[int] = Field(default=None, description="Monotonic exchange message sequence ID.")
    provenance: ProvenanceMetadata = Field(..., description="Data provenance & quality classification.")

    @model_validator(mode="after")
    def validate_bbo(self) -> "TradeTick":
        """Ensure Best Bid/Offer quotes are sane when supplied."""
        if self.bid is not None and self.ask is not None:
            if self.bid > self.ask:
                raise ValueError(f"Crossed market: Bid ({self.bid}) cannot exceed Ask ({self.ask}).")
        return self


class BookLevel(BaseModel):
    """Single price level in the limit order book."""
    model_config = ConfigDict(frozen=True, extra="forbid")

    price: float = Field(..., gt=0.0, description="Price level.")
    quantity: int = Field(..., ge=0, description="Cumulative volume at price level.")
    orders_count: Optional[int] = Field(default=None, ge=0, description="Number of orders at level.")


class OrderBookDepth(BaseModel):
    """
    Structured snapshot of market depth (DOM / L2).
    """
    model_config = ConfigDict(frozen=True, extra="forbid")

    instrument_id: str = Field(..., description="Target instrument identifier.")
    timestamp_ns: int = Field(..., description="Snapshot timestamp in nanoseconds UTC.")
    bids: List[BookLevel] = Field(default_factory=list, description="Bid levels sorted descending by price.")
    asks: List[BookLevel] = Field(default_factory=list, description="Ask levels sorted ascending by price.")
    sequence_id: Optional[int] = Field(default=None, description="Monotonic depth sequence counter.")
    provenance: ProvenanceMetadata = Field(..., description="Data provenance & quality classification.")

    @model_validator(mode="after")
    def validate_depth_ordering(self) -> "OrderBookDepth":
        """Enforce strict book sorting and non-crossed book check."""
        if self.bids:
            for i in range(len(self.bids) - 1):
                if self.bids[i].price <= self.bids[i + 1].price:
                    raise ValueError(f"Bids must be sorted strictly descending by price.")
        if self.asks:
            for i in range(len(self.asks) - 1):
                if self.asks[i].price >= self.asks[i + 1].price:
                    raise ValueError(f"Asks must be sorted strictly ascending by price.")
        if self.bids and self.asks:
            if self.bids[0].price >= self.asks[0].price:
                raise ValueError(
                    f"Crossed order book: Top bid ({self.bids[0].price}) >= Top ask ({self.asks[0].price})."
                )
        return self
