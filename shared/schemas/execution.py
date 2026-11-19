"""STRATLAB Core Domain: Execution & Simulation Ledgers.

Data contracts for Paper Trading orders, volume-at-price queue positions,
fills, positions, and account state.
"""

from enum import Enum
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field, model_validator


class OrderType(str, Enum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    STOP_LOSS = "STOP_LOSS"
    STOP_LIMIT = "STOP_LIMIT"


class OrderStatus(str, Enum):
    PENDING = "PENDING"
    QUEUED = "QUEUED"
    FILLED = "FILLED"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"


class OrderSide(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class PaperOrder(BaseModel):
    """
    Simulated order with queue-ahead tracking for realistic limit matching.
    """
    model_config = ConfigDict(frozen=True, extra="forbid")

    order_id: str = Field(..., description="Unique order identifier.")
    account_id: str = Field(..., description="Target paper account identifier.")
    instrument_id: str = Field(..., description="Target instrument identifier.")
    side: OrderSide = Field(..., description="Order side (BUY or SELL).")
    order_type: OrderType = Field(..., description="Order type.")
    price: Optional[float] = Field(default=None, gt=0.0, description="Limit price if applicable.")
    stop_price: Optional[float] = Field(default=None, gt=0.0, description="Trigger price for stop orders.")
    quantity: int = Field(..., gt=0, description="Requested total order volume.")
    filled_quantity: int = Field(default=0, ge=0, description="Accumulated filled volume.")
    avg_fill_price: Optional[float] = Field(default=None, gt=0.0, description="Volume-weighted average fill price.")
    status: OrderStatus = Field(default=OrderStatus.PENDING, description="Order lifecycle state.")
    queue_ahead_volume: int = Field(default=0, ge=0, description="Simulated volume that must trade before fill.")
    created_time_utc: int = Field(..., description="Submission timestamp in UTC milliseconds.")
    updated_time_utc: int = Field(..., description="Last state change in UTC milliseconds.")

    @model_validator(mode="after")
    def validate_order_params(self) -> "PaperOrder":
        if self.order_type in (OrderType.LIMIT, OrderType.STOP_LIMIT) and self.price is None:
            raise ValueError(f"{self.order_type.name} orders require a limit price.")
        if self.order_type in (OrderType.STOP_LOSS, OrderType.STOP_LIMIT) and self.stop_price is None:
            raise ValueError(f"{self.order_type.name} orders require a stop_price.")
        if self.filled_quantity > self.quantity:
            raise ValueError(f"filled_quantity ({self.filled_quantity}) cannot exceed quantity ({self.quantity}).")
        return self


class PaperFill(BaseModel):
    """
    Individual execution fill event.
    """
    model_config = ConfigDict(frozen=True, extra="forbid")

    fill_id: str = Field(..., description="Unique fill transaction identifier.")
    order_id: str = Field(..., description="Parent order identifier.")
    timestamp_utc: int = Field(..., description="Execution timestamp in UTC milliseconds.")
    price: float = Field(..., gt=0.0, description="Execution price.")
    quantity: int = Field(..., gt=0, description="Executed quantity.")
    fee: float = Field(default=0.0, ge=0.0, description="Total statutory fees, taxes, and commissions.")
    slippage: float = Field(default=0.0, description="Signed execution slippage vs requested price.")


class PaperPosition(BaseModel):
    """
    Open or closed instrument position in a paper account.
    """
    model_config = ConfigDict(frozen=True, extra="forbid")

    account_id: str = Field(..., description="Parent paper account identifier.")
    instrument_id: str = Field(..., description="Target instrument identifier.")
    quantity: int = Field(..., description="Signed position size: positive=long, negative=short, zero=flat.")
    avg_entry_price: float = Field(default=0.0, ge=0.0, description="Average entry price.")
    current_price: float = Field(default=0.0, ge=0.0, description="Latest market mark price.")
    unrealized_pnl: float = Field(default=0.0, description="Unrealized profit/loss.")
    realized_pnl: float = Field(default=0.0, description="Closed realized profit/loss.")
    updated_time_utc: int = Field(..., description="Last update timestamp in UTC milliseconds.")


class PaperAccount(BaseModel):
    """
    Simulated trading account state.
    """
    model_config = ConfigDict(frozen=True, extra="forbid")

    account_id: str = Field(..., description="Unique paper account identifier.")
    user_id: str = Field(..., description="Owner user identifier.")
    name: str = Field(..., min_length=1, max_length=64, description="Display name for account.")
    currency: str = Field(default="INR", description="Base accounting currency.")
    balance: float = Field(..., description="Available settled cash balance.")
    equity: float = Field(..., description="Total portfolio equity: balance + unrealized PnL.")
    margin_used: float = Field(default=0.0, ge=0.0, description="Current margin allocated to open positions.")
    created_time_utc: int = Field(..., description="Creation timestamp in UTC milliseconds.")
