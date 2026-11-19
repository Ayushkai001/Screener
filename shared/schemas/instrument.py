"""STRATLAB Core Domain: Universal Instrument Master.

Defines the universal instrument entity across equities, futures, options,
forex, crypto, and commodities, avoiding reliance on ambiguous tickers.
"""

from datetime import date
from enum import Enum
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class AssetClass(str, Enum):
    """Supported tradable asset classes."""
    EQUITY = "EQUITY"
    FUTURES = "FUTURES"
    OPTIONS = "OPTIONS"
    CRYPTO = "CRYPTO"
    FOREX = "FOREX"
    COMMODITY = "COMMODITY"
    INDEX = "INDEX"


class OptionType(str, Enum):
    """European / American option types."""
    CALL = "CE"
    PUT = "PE"


class InstrumentMaster(BaseModel):
    """
    Normalized instrument specification.
    Primary key is instrument_id, never ticker symbol alone.
    """
    model_config = ConfigDict(frozen=True, extra="forbid")

    instrument_id: str = Field(
        ...,
        pattern=r"^INS_[A-Z0-9_]{3,28}$",
        description="Globally unique canonical instrument identifier (e.g. INS_NSE_RELIANCE)."
    )
    symbol: str = Field(
        ...,
        min_length=1,
        max_length=32,
        description="Local exchange ticker symbol (e.g. RELIANCE, NIFTY26NOVFUT)."
    )
    exchange: str = Field(
        ...,
        min_length=2,
        max_length=16,
        description="Exchange or venue identifier (e.g. NSE, BSE, MCX, BINANCE)."
    )
    asset_class: AssetClass = Field(
        ...,
        description="Asset class classification."
    )
    currency: str = Field(
        default="INR",
        min_length=3,
        max_length=8,
        description="Settlement currency (ISO code or crypto ticker, e.g. INR, USD, USDT)."
    )
    tick_size: float = Field(
        ...,
        gt=0.0,
        description="Minimum price movement increment (e.g. 0.05 for NSE equities)."
    )
    lot_size: int = Field(
        default=1,
        ge=1,
        description="Minimum order contract lot size."
    )
    multiplier: float = Field(
        default=1.0,
        gt=0.0,
        description="Contract price multiplier for notional turnover calculations."
    )
    timezone: str = Field(
        default="Asia/Kolkata",
        description="Market trading session time zone."
    )

    # Derivative Contract Metadata
    expiry: Optional[date] = Field(
        default=None,
        description="Contract expiration date for futures and options."
    )
    strike: Optional[float] = Field(
        default=None,
        gt=0.0,
        description="Option strike price."
    )
    option_type: Optional[OptionType] = Field(
        default=None,
        description="Option right: CE (Call) or PE (Put)."
    )
    underlying_id: Optional[str] = Field(
        default=None,
        description="Reference instrument_id of underlying spot/cash instrument."
    )

    @field_validator("symbol", "exchange")
    @classmethod
    def normalize_upper(cls, v: str) -> str:
        return v.strip().upper()

    @model_validator(mode="after")
    def validate_derivatives(self) -> "InstrumentMaster":
        """Ensure required contract attributes are populated for derivatives."""
        if self.asset_class == AssetClass.OPTIONS:
            if self.expiry is None or self.strike is None or self.option_type is None:
                raise ValueError(
                    f"Options contracts require expiry, strike, and option_type. "
                    f"Got expiry={self.expiry}, strike={self.strike}, option_type={self.option_type}"
                )
        elif self.asset_class == AssetClass.FUTURES:
            if self.expiry is None:
                raise ValueError("Futures contracts require an expiry date.")
        return self
