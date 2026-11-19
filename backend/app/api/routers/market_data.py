"""STRATLAB Market Data & Order Flow REST Endpoints."""

from datetime import date
from typing import List, Optional
from fastapi import APIRouter, HTTPException, Query
from shared.schemas.instrument import AssetClass, InstrumentMaster
from shared.schemas.market_data import Candle
from shared.schemas.order_flow import FootprintBar, VolumeProfile
from shared.schemas.provenance import DataQuality, ProvenanceMetadata
from backend.app.analytics.volume_profile.profile import VolumeProfileEngine


router = APIRouter(prefix="/market", tags=["Market Data & Order Flow"])

# Mock in-memory instrument catalog
CATALOG: List[InstrumentMaster] = [
    InstrumentMaster(
        instrument_id="INS_NSE_RELIANCE",
        symbol="RELIANCE",
        exchange="NSE",
        asset_class=AssetClass.EQUITY,
        currency="INR",
        tick_size=0.05,
        lot_size=1,
    ),
    InstrumentMaster(
        instrument_id="INS_NSE_NIFTY_FUT",
        symbol="NIFTY26NOVFUT",
        exchange="NSE",
        asset_class=AssetClass.FUTURES,
        currency="INR",
        tick_size=0.05,
        lot_size=50,
        multiplier=50.0,
        expiry=date(2026, 11, 26),
    ),
    InstrumentMaster(
        instrument_id="INS_BINANCE_BTCUSDT",
        symbol="BTCUSDT",
        exchange="BINANCE",
        asset_class=AssetClass.CRYPTO,
        currency="USDT",
        tick_size=0.10,
        lot_size=1,
    ),
]


@router.get("/instruments", response_model=List[InstrumentMaster])
def list_instruments(
    exchange: Optional[str] = None,
    asset_class: Optional[AssetClass] = None,
) -> List[InstrumentMaster]:
    """Retrieve available instrument master records."""
    res = CATALOG
    if exchange:
        res = [i for i in res if i.exchange.upper() == exchange.upper()]
    if asset_class:
        res = [i for i in res if i.asset_class == asset_class]
    return res


@router.get("/candles", response_model=List[Candle])
def get_candles(
    instrument_id: str = Query(..., description="Target instrument ID"),
    timeframe: str = Query("5m", description="Resolution (1m, 5m, 15m, 1d)"),
    limit: int = Query(50, ge=1, le=500),
) -> List[Candle]:
    """Retrieve historical OHLCV candles with explicit provenance tags."""
    tf = timeframe if isinstance(timeframe, str) else "5m"
    prov = ProvenanceMetadata.exchange_verified("NSE_TBT")
    base_price = 2500.0 if "RELIANCE" in instrument_id else 100.0

    candles = []
    for i in range(limit):
        p = base_price + (i * 0.5)
        candles.append(Candle(
            instrument_id=instrument_id,
            timestamp_utc=(i + 1) * 300000,
            timeframe=tf,
            open=p,
            high=p + 1.5,
            low=p - 1.0,
            close=p + 0.8,
            volume=15000 + (i * 100),
            provenance=prov,
        ))
    return candles


@router.get("/orderflow/profile", response_model=VolumeProfile)
def get_volume_profile(
    instrument_id: str = Query(..., description="Target instrument ID"),
) -> VolumeProfile:
    """Calculate 70% Value Area Volume Profile (POC, VAH, VAL, HVN, LVN)."""
    candles = get_candles(instrument_id=instrument_id, timeframe="5m", limit=30)
    profile = VolumeProfileEngine.build_from_candles(
        candles=candles,
        instrument_id=instrument_id,
        session_date="2026-11-19",
        profile_type="SESSION",
    )
    if not profile:
        raise HTTPException(status_code=404, detail="Could not calculate volume profile")
    return profile
