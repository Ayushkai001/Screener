"""STRATLAB Analytics: Footprint Aggregator & Imbalance Engine.

Constructs FootprintBar entities from streaming or historical TradeTick records:
- Price quantization into tick-size buckets.
- Bid x Ask volume clustering.
- Diagonal buy/sell imbalance detection (Ask[P] vs Bid[P - 1 tick]).
- Stacked imbalance detection (>= N consecutive levels).
- Unfinished auction detection (non-zero prints at bar extremes).
- Point of Control (POC) and Value Area (VAH/VAL) computation.
"""

from typing import Dict, List, Optional, Tuple
from shared.schemas.market_data import TradeTick
from shared.schemas.order_flow import FootprintBar, PriceCluster
from shared.schemas.provenance import AggressorSide, ProvenanceMetadata


class FootprintAggregator:
    """
    Stateful aggregator building FootprintBar from individual trade ticks.
    """
    def __init__(
        self,
        instrument_id: str,
        timeframe: str = "5m",
        tick_size: float = 0.05,
        imbalance_ratio: float = 3.0, # 300% (3:1) diagonal threshold
        min_imbalance_volume: int = 100,
        stacked_min_count: int = 3, # >= 3 consecutive levels = stacked imbalance
    ):
        self.instrument_id = instrument_id
        self.timeframe = timeframe
        self.tick_size = tick_size
        self.imbalance_ratio = imbalance_ratio
        self.min_imbalance_volume = min_imbalance_volume
        self.stacked_min_count = stacked_min_count

        self._reset_bar_state()

    def _reset_bar_state(self):
        self._clusters: Dict[float, Dict[str, int]] = {}
        self._open: Optional[float] = None
        self._high: Optional[float] = None
        self._low: Optional[float] = None
        self._close: Optional[float] = None
        self._volume: int = 0
        self._turnover: float = 0.0
        self._open_time_utc: Optional[int] = None
        self._close_time_utc: Optional[int] = None
        self._delta: int = 0
        self._delta_min: int = 0
        self._delta_max: int = 0
        self._primary_provenance: Optional[ProvenanceMetadata] = None

    def quantize_price(self, price: float) -> float:
        """Quantize price to nearest tick boundary."""
        return round(round(price / self.tick_size) * self.tick_size, 4)

    def on_tick(self, tick: TradeTick):
        """Accumulate an incoming trade tick into the active candle."""
        p = self.quantize_price(tick.price)
        qty = tick.quantity

        if self._open is None:
            self._open = p
            self._high = p
            self._low = p
            self._open_time_utc = int(tick.timestamp_ns / 1_000_000)
            self._primary_provenance = tick.provenance

        self._high = max(self._high, p)
        self._low = min(self._low, p)
        self._close = p
        self._close_time_utc = int(tick.timestamp_ns / 1_000_000)
        self._volume += qty
        self._turnover += p * qty

        # Price Cluster Update
        if p not in self._clusters:
            self._clusters[p] = {"bid_vol": 0, "ask_vol": 0, "trades": 0}

        node = self._clusters[p]
        node["trades"] += 1

        if tick.aggressor == AggressorSide.BUY:
            node["ask_vol"] += qty
            self._delta += qty
        elif tick.aggressor == AggressorSide.SELL:
            node["bid_vol"] += qty
            self._delta -= qty
        else:
            # Unknown: split 50/50
            half = qty // 2
            node["ask_vol"] += half
            node["bid_vol"] += (qty - half)

        self._delta_min = min(self._delta_min, self._delta)
        self._delta_max = max(self._delta_max, self._delta)

    def finalize_bar(self, session_cum_delta: int = 0) -> Optional[FootprintBar]:
        """
        Finalize the bar, calculate POC, Value Area, imbalances, and return FootprintBar.
        """
        if self._open is None or not self._clusters:
            return None

        sorted_prices = sorted(self._clusters.keys())
        poc_price = max(sorted_prices, key=lambda p: (self._clusters[p]["bid_vol"] + self._clusters[p]["ask_vol"]))

        # 1. Diagonal Imbalance Detection
        # Buy Imbalance: Ask[P] >= Bid[P - 1 tick] * ratio
        # Sell Imbalance: Bid[P] >= Ask[P + 1 tick] * ratio
        imbalance_buy = set()
        imbalance_sell = set()

        price_set = set(sorted_prices)
        for p in sorted_prices:
            node = self._clusters[p]
            lower_p = self.quantize_price(p - self.tick_size)
            higher_p = self.quantize_price(p + self.tick_size)

            # Diagonal Buy Check
            lower_bid = self._clusters[lower_p]["bid_vol"] if lower_p in price_set else 0
            if node["ask_vol"] >= self.min_imbalance_volume:
                if lower_bid == 0 or (node["ask_vol"] / lower_bid >= self.imbalance_ratio):
                    imbalance_buy.add(p)

            # Diagonal Sell Check
            higher_ask = self._clusters[higher_p]["ask_vol"] if higher_p in price_set else 0
            if node["bid_vol"] >= self.min_imbalance_volume:
                if higher_ask == 0 or (node["bid_vol"] / higher_ask >= self.imbalance_ratio):
                    imbalance_sell.add(p)

        # 2. Stacked Imbalance Scanning
        stacked_buys = self._find_stacked(sorted_prices, imbalance_buy)
        stacked_sells = self._find_stacked(sorted_prices, imbalance_sell)

        # 3. Value Area Calculation (70% standard)
        bins = {p: (self._clusters[p]["bid_vol"] + self._clusters[p]["ask_vol"]) for p in sorted_prices}
        vah, val = self._calculate_value_area(sorted_prices, bins, poc_price)

        # 4. Unfinished Auction Checks
        high_node = self._clusters[self._high]
        low_node = self._clusters[self._low]
        unfinished_high = high_node["ask_vol"] > 0
        unfinished_low = low_node["bid_vol"] > 0

        # 5. Build Final PriceCluster Models
        final_clusters = {}
        for p in sorted_prices:
            n = self._clusters[p]
            b_vol, a_vol = n["bid_vol"], n["ask_vol"]
            final_clusters[p] = PriceCluster(
                price=p,
                bid_vol=b_vol,
                ask_vol=a_vol,
                total_vol=b_vol + a_vol,
                delta=a_vol - b_vol,
                trade_count=n["trades"],
                imbalance_buy=(p in imbalance_buy),
                imbalance_sell=(p in imbalance_sell),
                is_poc=(p == poc_price),
                provenance=self._primary_provenance,
            )

        finish_ratio = round(self._delta / self._volume, 4) if self._volume > 0 else 0.0

        bar = FootprintBar(
            instrument_id=self.instrument_id,
            timeframe=self.timeframe,
            open_time_utc=self._open_time_utc,
            close_time_utc=self._close_time_utc,
            open=self._open,
            high=self._high,
            low=self._low,
            close=self._close,
            volume=self._volume,
            turnover=round(self._turnover, 2),
            delta=self._delta,
            cum_delta=session_cum_delta + self._delta,
            delta_min=self._delta_min,
            delta_max=self._delta_max,
            delta_finish=finish_ratio,
            clusters=final_clusters,
            poc_price=poc_price,
            vah=vah,
            val=val,
            stacked_buy_imbalances=stacked_buys,
            stacked_sell_imbalances=stacked_sells,
            unfinished_high=unfinished_high,
            unfinished_low=unfinished_low,
            provenance=self._primary_provenance,
        )

        self._reset_bar_state()
        return bar

    def _find_stacked(self, sorted_prices: List[float], flagged_prices: set) -> List[float]:
        """Find contiguous price levels with imbalances >= stacked_min_count."""
        stacked = []
        current_run = []
        for p in sorted_prices:
            if p in flagged_prices:
                current_run.append(p)
            else:
                if len(current_run) >= self.stacked_min_count:
                    stacked.extend(current_run)
                current_run = []
        if len(current_run) >= self.stacked_min_count:
            stacked.extend(current_run)
        return stacked

    def _calculate_value_area(self, sorted_prices: List[float], bins: Dict[float, int], poc_price: float) -> Tuple[float, float]:
        total_vol = sum(bins.values())
        if not total_vol or len(sorted_prices) <= 2:
            return sorted_prices[-1], sorted_prices[0]

        target_vol = total_vol * 0.70
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
