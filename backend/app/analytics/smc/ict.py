"""STRATLAB Pattern Analytics: ICT (Inner Circle Trader) & Institutional Concepts.

Implements core ICT trading models:
- Kill Zones (London Open, NY Open, Asian, Silver Bullet)
- Premium vs Discount Equilibrium
- Liquidity Pool Sweeps (Buyside BSL & Sellside SSL)
- Optimal Trade Entry (OTE: 62% – 79% equilibrium retrace)
- Institutional Order Blocks (OB)
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from shared.schemas.market_data import Candle


class KillZone(str, Enum):
    ASIAN = "ASIAN"                 # 20:00 - 00:00 EST / 01:00 - 05:00 UTC
    LONDON_OPEN = "LONDON_OPEN"     # 02:00 - 05:00 EST / 07:00 - 10:00 UTC
    NY_OPEN = "NY_OPEN"             # 07:00 - 10:00 EST / 12:00 - 15:00 UTC
    SILVER_BULLET = "SILVER_BULLET" # 10:00 - 11:00 AM EST (NY local morning)
    OUTSIDE = "OUTSIDE"


class LiquidityType(str, Enum):
    BUYSIDE_LIQUIDITY = "BSL"       # Resting buy stops above swing high
    SELLSIDE_LIQUIDITY = "SSL"      # Resting sell stops below swing low


class LiquiditySweep(BaseModel):
    sweep_type: LiquidityType
    candle_idx: int
    level_price: float
    sweep_price: float
    timestamp_utc: int
    is_rejected: bool               # True if candle closed back inside the range


class OrderBlock(BaseModel):
    is_bullish: bool                # True for Bullish OB (down-candle before impulse up)
    candle_idx: int
    top: float
    bottom: float
    timestamp_utc: int
    is_mitigated: bool = False


class ICTMarketState(BaseModel):
    active_killzone: KillZone
    is_silver_bullet_window: bool
    equilibrium_price: float
    in_discount_zone: bool          # < 50% retrace: favorable for institutional buying
    in_premium_zone: bool           # > 50% retrace: favorable for institutional selling
    in_ote_zone: bool               # Optimal Trade Entry: 61.8% to 79.0%
    recent_sweeps: List[LiquiditySweep] = Field(default_factory=list)
    active_order_blocks: List[OrderBlock] = Field(default_factory=list)
    has_bullish_sweep_rejection: bool = False
    has_bearish_sweep_rejection: bool = False


class ICTTradingEngine:
    """
    Evaluates candles for ICT institutional liquidity and timing setups.
    """

    @classmethod
    def evaluate(
        cls,
        candles: List[Candle],
        lookback_swings: int = 30,
    ) -> ICTMarketState:
        """
        Calculates ICT market context: Killzone, Premium/Discount, Sweeps, and Order Blocks.
        """
        if not candles:
            return ICTMarketState(
                active_killzone=KillZone.OUTSIDE,
                is_silver_bullet_window=False,
                equilibrium_price=0.0,
                in_discount_zone=False,
                in_premium_zone=False,
                in_ote_zone=False,
            )

        last_candle = candles[-1]
        dt = datetime.fromtimestamp(last_candle.timestamp_utc / 1000, tz=timezone.utc)

        # 1. Killzone Timing (UTC times)
        hour = dt.hour
        minute = dt.minute

        kz = KillZone.OUTSIDE
        is_sb = False

        if 7 <= hour < 10:
            kz = KillZone.LONDON_OPEN
        elif 12 <= hour < 15:
            kz = KillZone.NY_OPEN
            # Silver Bullet is 10:00 - 11:00 AM NY local = 14:00 - 15:00 UTC (standard time)
            if hour == 14:
                is_sb = True
        elif 1 <= hour < 5:
            kz = KillZone.ASIAN

        # 2. Premium / Discount Equilibrium
        subset = candles[-lookback_swings:] if len(candles) > lookback_swings else candles
        high_c = max(subset, key=lambda c: c.high)
        low_c = min(subset, key=lambda c: c.low)

        h_val = high_c.high
        l_val = low_c.low
        diff = h_val - l_val
        eq_price = (h_val + l_val) / 2.0 if diff > 0 else last_candle.close

        current_px = last_candle.close
        in_discount = current_px < eq_price
        in_premium = current_px > eq_price

        # OTE Zone: 62% to 79% retracement of the bullish impulse
        ote_bottom = h_val - 0.79 * diff if diff > 0 else 0
        ote_top = h_val - 0.62 * diff if diff > 0 else 0
        in_ote = ote_bottom <= current_px <= ote_top if diff > 0 else False

        # 3. Liquidity Sweeps
        # Find swing highs and swing lows in subset
        sweeps: List[LiquiditySweep] = []
        has_bull_sweep = False
        has_bear_sweep = False

        if len(subset) >= 3:
            prev_high = max(c.high for c in subset[:-1])
            prev_low = min(c.low for c in subset[:-1])

            # Buyside Liquidity Sweep (BSL): Price went above previous high but closed back below
            if last_candle.high > prev_high and last_candle.close < prev_high:
                sweeps.append(
                    LiquiditySweep(
                        sweep_type=LiquidityType.BUYSIDE_LIQUIDITY,
                        candle_idx=len(candles) - 1,
                        level_price=prev_high,
                        sweep_price=last_candle.high,
                        timestamp_utc=last_candle.timestamp_utc,
                        is_rejected=True,
                    )
                )
                has_bear_sweep = True

            # Sellside Liquidity Sweep (SSL): Price dipped below previous low but closed back above
            if last_candle.low < prev_low and last_candle.close > prev_low:
                sweeps.append(
                    LiquiditySweep(
                        sweep_type=LiquidityType.SELLSIDE_LIQUIDITY,
                        candle_idx=len(candles) - 1,
                        level_price=prev_low,
                        sweep_price=last_candle.low,
                        timestamp_utc=last_candle.timestamp_utc,
                        is_rejected=True,
                    )
                )
                has_bull_sweep = True

        # 4. Order Blocks (Last opposing candle before strong displacement)
        order_blocks: List[OrderBlock] = []
        for i in range(1, len(subset) - 1):
            c_prev = subset[i - 1]
            c_curr = subset[i]
            c_next = subset[i + 1]

            # Bullish Order Block: Down candle (c_prev or c_curr) followed by large displacement up
            if c_curr.close < c_curr.open and (c_next.close - c_next.open) > (c_curr.open - c_curr.close) * 1.5:
                order_blocks.append(
                    OrderBlock(
                        is_bullish=True,
                        candle_idx=i,
                        top=c_curr.open,
                        bottom=c_curr.low,
                        timestamp_utc=c_curr.timestamp_utc,
                        is_mitigated=last_candle.low < c_curr.low,
                    )
                )

        return ICTMarketState(
            active_killzone=kz,
            is_silver_bullet_window=is_sb,
            equilibrium_price=round(eq_price, 4),
            in_discount_zone=in_discount,
            in_premium_zone=in_premium,
            in_ote_zone=in_ote,
            recent_sweeps=sweeps,
            active_order_blocks=order_blocks,
            has_bullish_sweep_rejection=has_bull_sweep,
            has_bearish_sweep_rejection=has_bear_sweep,
        )
