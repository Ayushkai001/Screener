"""STRATLAB Analytics: Volume Profile Engine.

Calculates Session, Fixed-Range, and Composite Volume Profiles:
- Price quantization into uniform bins.
- Point of Control (POC) with maximum volume.
- Value Area High (VAH) and Value Area Low (VAL) enclosing 70% of distribution volume.
- High Volume Nodes (HVN: support/resistance shelves) and Low Volume Nodes (LVN: slippage voids).
"""

from typing import Dict, List, Optional, Tuple

from shared.schemas.market_data import Candle, TradeTick
from shared.schemas.order_flow import VolumeProfile
from shared.schemas.provenance import DataQuality, ProvenanceMetadata


class VolumeProfileEngine:
    """
    Computes market profile distributions from trade ticks or candle series.
    """
    @staticmethod
    def build_from_ticks(
        ticks: List[TradeTick],
        instrument_id: str,
        session_date: str,
        tick_size: float = 0.05,
        profile_type: str = "SESSION",
        target_pct: float = 0.70,
    ) -> Optional[VolumeProfile]:
        if not ticks:
            return None

        bins: Dict[float, int] = {}
        total_vol = 0
        start_ts = int(ticks[0].timestamp_ns / 1_000_000)
        end_ts = int(ticks[-1].timestamp_ns / 1_000_000)
        prov = ticks[0].provenance

        for t in ticks:
            p = round(round(t.price / tick_size) * tick_size, 4)
            bins[p] = bins.get(p, 0) + t.quantity
            total_vol += t.quantity

        return VolumeProfileEngine._finalize_profile(
            bins=bins,
            total_vol=total_vol,
            instrument_id=instrument_id,
            session_date=session_date,
            start_ts=start_ts,
            end_ts=end_ts,
            tick_size=tick_size,
            profile_type=profile_type,
            target_pct=target_pct,
            provenance=prov,
        )

    @staticmethod
    def build_from_candles(
        candles: List[Candle],
        instrument_id: str,
        session_date: str,
        tick_size: float = 0.05,
        profile_type: str = "SESSION",
        target_pct: float = 0.70,
    ) -> Optional[VolumeProfile]:
        """
        Build Level D synthetic volume profile by distributing each candle's
        volume across its high-low range.
        """
        if not candles:
            return None

        bins: Dict[float, int] = {}
        total_vol = 0
        start_ts = candles[0].timestamp_utc
        end_ts = candles[-1].timestamp_utc

        for c in candles:
            total_vol += c.volume
            lo = round(round(c.low / tick_size) * tick_size, 4)
            hi = round(round(c.high / tick_size) * tick_size, 4)
            steps = int(round((hi - lo) / tick_size)) + 1

            if steps <= 1:
                bins[lo] = bins.get(lo, 0) + c.volume
            else:
                vol_per_step = c.volume / steps
                for i in range(steps):
                    p = round(lo + i * tick_size, 4)
                    bins[p] = bins.get(p, 0) + int(vol_per_step)

        prov = ProvenanceMetadata.ohlcv_proxy(source_id="CANDLE_DISTRIBUTION", confidence=0.35)

        return VolumeProfileEngine._finalize_profile(
            bins=bins,
            total_vol=total_vol,
            instrument_id=instrument_id,
            session_date=session_date,
            start_ts=start_ts,
            end_ts=end_ts,
            tick_size=tick_size,
            profile_type=profile_type,
            target_pct=target_pct,
            provenance=prov,
        )

    @staticmethod
    def _finalize_profile(
        bins: Dict[float, int],
        total_vol: int,
        instrument_id: str,
        session_date: str,
        start_ts: int,
        end_ts: int,
        tick_size: float,
        profile_type: str,
        target_pct: float,
        provenance: ProvenanceMetadata,
    ) -> VolumeProfile:
        sorted_prices = sorted(bins.keys())
        poc_price = max(sorted_prices, key=lambda p: bins[p])
        poc_vol = bins[poc_price]

        # Value Area 70%
        vah, val = VolumeProfileEngine._calculate_value_area(sorted_prices, bins, poc_price, target_pct)

        # High & Low Volume Nodes
        hvns, lvns = VolumeProfileEngine._detect_nodes(sorted_prices, bins)

        return VolumeProfile(
            instrument_id=instrument_id,
            session_date=session_date,
            profile_type=profile_type,
            start_time_utc=start_ts,
            end_time_utc=end_ts,
            tick_size=tick_size,
            bins=bins,
            total_volume=total_vol,
            poc_price=poc_price,
            poc_volume=poc_vol,
            vah_price=vah,
            val_price=val,
            high_volume_nodes=hvns,
            low_volume_nodes=lvns,
            provenance=provenance,
        )

    @staticmethod
    def _calculate_value_area(
        sorted_prices: List[float],
        bins: Dict[float, int],
        poc_price: float,
        target_pct: float = 0.70,
    ) -> Tuple[float, float]:
        total_vol = sum(bins.values())
        if not total_vol or len(sorted_prices) <= 2:
            return sorted_prices[-1], sorted_prices[0]

        target_vol = total_vol * target_pct
        poc_idx = sorted_prices.index(poc_price)
        cur_vol = bins[poc_price]
        up_idx = poc_idx + 1
        dn_idx = poc_idx - 1

        while cur_vol < target_vol and (up_idx < len(sorted_prices) or dn_idx >= 0):
            up_vol = sum(bins[sorted_prices[i]] for i in range(up_idx, min(up_idx + 2, len(sorted_prices))))
            dn_vol = sum(bins[sorted_prices[i]] for i in range(max(0, dn_idx - 1), dn_idx + 1))

            if up_vol >= dn_vol and up_idx < len(sorted_prices):
                cur_vol += up_vol
                up_idx += 2
            elif dn_idx >= 0:
                cur_vol += dn_vol
                dn_idx -= 2
            else:
                cur_vol += up_vol
                up_idx += 2

        vah = sorted_prices[min(up_idx - 1, len(sorted_prices) - 1)]
        val = sorted_prices[max(dn_idx + 1, 0)]
        return vah, val

    @staticmethod
    def _detect_nodes(sorted_prices: List[float], bins: Dict[float, int]) -> Tuple[List[float], List[float]]:
        """Identify volume peaks (HVNs) and volume valleys (LVNs) using 3-bin window."""
        hvns = []
        lvns = []
        if len(sorted_prices) < 5:
            return hvns, lvns

        avg_vol = sum(bins.values()) / len(sorted_prices)

        for i in range(1, len(sorted_prices) - 1):
            prev_p, cur_p, next_p = sorted_prices[i - 1], sorted_prices[i], sorted_prices[i + 1]
            prev_v, cur_v, next_v = bins[prev_p], bins[cur_p], bins[next_p]

            # High Volume Node: peak higher than neighbors and above average
            if cur_v > prev_v and cur_v > next_v and cur_v > avg_vol * 1.2:
                hvns.append(cur_p)
            # Low Volume Node: valley lower than neighbors and below average
            elif cur_v < prev_v and cur_v < next_v and cur_v < avg_vol * 0.7:
                lvns.append(cur_p)

        return hvns, lvns
