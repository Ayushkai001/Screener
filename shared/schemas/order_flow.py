"""STRATLAB Core Domain: Order Flow Entities.

Data contracts for Footprint price-clusters, diagonal imbalances,
Volume Profiles (POC, VAH, VAL), and Cumulative Volume Delta (CVD).
"""

from typing import Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field, model_validator

from .provenance import ProvenanceMetadata


class PriceCluster(BaseModel):
    """
    Price-level volume breakdown within a single Footprint bar.
    """
    model_config = ConfigDict(frozen=True, extra="forbid")

    price: float = Field(..., gt=0.0, description="Quantized price level.")
    bid_vol: int = Field(default=0, ge=0, description="Volume executed at the Bid (market sells).")
    ask_vol: int = Field(default=0, ge=0, description="Volume executed at the Ask (market buys).")
    total_vol: int = Field(default=0, ge=0, description="Total traded quantity at price.")
    delta: int = Field(default=0, description="Ask volume minus Bid volume.")
    trade_count: int = Field(default=0, ge=0, description="Number of trades executed at this level.")
    imbalance_buy: bool = Field(default=False, description="Diagonal aggressive buying imbalance.")
    imbalance_sell: bool = Field(default=False, description="Diagonal aggressive selling imbalance.")
    is_poc: bool = Field(default=False, description="Point of Control within the candle.")
    provenance: ProvenanceMetadata = Field(..., description="Data provenance & quality classification.")

    @model_validator(mode="after")
    def validate_totals(self) -> "PriceCluster":
        expected_total = self.bid_vol + self.ask_vol
        if self.total_vol != expected_total:
            raise ValueError(f"total_vol ({self.total_vol}) must equal bid_vol + ask_vol ({expected_total}).")
        expected_delta = self.ask_vol - self.bid_vol
        if self.delta != expected_delta:
            raise ValueError(f"delta ({self.delta}) must equal ask_vol - bid_vol ({expected_delta}).")
        return self


class FootprintBar(BaseModel):
    """
    Aggregated footprint candlestick with full order flow cluster matrix.
    """
    model_config = ConfigDict(frozen=True, extra="forbid")

    instrument_id: str = Field(..., description="Target instrument identifier.")
    timeframe: str = Field(..., pattern=r"^\d+[smhdwM]$", description="Bar timeframe.")
    open_time_utc: int = Field(..., description="Bar start timestamp in UTC milliseconds.")
    close_time_utc: int = Field(..., description="Bar close timestamp in UTC milliseconds.")
    open: float = Field(..., gt=0.0)
    high: float = Field(..., gt=0.0)
    low: float = Field(..., gt=0.0)
    close: float = Field(..., gt=0.0)
    volume: int = Field(..., ge=0)
    turnover: float = Field(default=0.0, ge=0.0)

    # Order Flow Metrics
    delta: int = Field(..., description="Bar delta (total ask volume - total bid volume).")
    cum_delta: int = Field(..., description="Session cumulative volume delta at bar close.")
    delta_min: int = Field(..., description="Minimum intraday delta reached during bar formation.")
    delta_max: int = Field(..., description="Maximum intraday delta reached during bar formation.")
    delta_finish: float = Field(..., ge=-1.0, le=1.0, description="Delta / total volume ratio (-1.0 to +1.0).")

    # Clusters & Value Area
    clusters: Dict[float, PriceCluster] = Field(default_factory=dict, description="Price level -> PriceCluster.")
    poc_price: float = Field(..., gt=0.0, description="Point of Control price.")
    vah: float = Field(..., gt=0.0, description="Value Area High (70% threshold).")
    val: float = Field(..., gt=0.0, description="Value Area Low (70% threshold).")

    # Structural Signals
    stacked_buy_imbalances: List[float] = Field(default_factory=list, description="Prices of stacked buy imbalances.")
    stacked_sell_imbalances: List[float] = Field(default_factory=list, description="Prices of stacked sell imbalances.")
    unfinished_high: bool = Field(default=False, description="High has aggressive buyers without auction exhaustion.")
    unfinished_low: bool = Field(default=False, description="Low has aggressive sellers without auction exhaustion.")
    provenance: ProvenanceMetadata = Field(..., description="Data provenance & quality classification.")

    @model_validator(mode="after")
    def validate_va_bounds(self) -> "FootprintBar":
        if self.vah < self.val:
            raise ValueError(f"VAH ({self.vah}) cannot be lower than VAL ({self.val}).")
        return self


class VolumeProfile(BaseModel):
    """
    Session, Fixed-Range, or Composite Volume Profile distribution.
    """
    model_config = ConfigDict(frozen=True, extra="forbid")

    instrument_id: str = Field(..., description="Target instrument identifier.")
    session_date: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$", description="Reference date YYYY-MM-DD.")
    profile_type: str = Field(..., description="SESSION, FIXED_RANGE, DEVELOPING, or COMPOSITE.")
    start_time_utc: int = Field(..., description="Profile start in UTC milliseconds.")
    end_time_utc: int = Field(..., description="Profile end in UTC milliseconds.")
    tick_size: float = Field(..., gt=0.0, description="Price quantization bin width.")
    bins: Dict[float, int] = Field(..., description="Quantized price -> cumulative volume.")
    total_volume: int = Field(..., ge=0, description="Total traded volume across profile.")
    poc_price: float = Field(..., gt=0.0, description="Point of Control price level.")
    poc_volume: int = Field(..., ge=0, description="Volume at Point of Control.")
    vah_price: float = Field(..., gt=0.0, description="Value Area High.")
    val_price: float = Field(..., gt=0.0, description="Value Area Low.")
    high_volume_nodes: List[float] = Field(default_factory=list, description="HVN support/resistance price peaks.")
    low_volume_nodes: List[float] = Field(default_factory=list, description="LVN rapid auction valleys.")
    provenance: ProvenanceMetadata = Field(..., description="Data provenance & quality classification.")


class CVDPoint(BaseModel):
    """
    Cumulative Volume Delta data point.
    """
    model_config = ConfigDict(frozen=True, extra="forbid")

    instrument_id: str = Field(..., description="Target instrument identifier.")
    timestamp_utc: int = Field(..., description="UTC epoch timestamp in milliseconds.")
    delta: int = Field(..., description="Delta for the interval.")
    cumulative_delta: int = Field(..., description="Cumulative delta value.")
    session_reset: bool = Field(default=False, description="True if CVD was reset to 0 at this point.")
    provenance: ProvenanceMetadata = Field(..., description="Data provenance & quality classification.")
