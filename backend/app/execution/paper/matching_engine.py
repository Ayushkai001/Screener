"""STRATLAB Queue-Aware Simulated Matching Engine.

Implements realistic limit order queue modeling where orders at a price level
are only filled after trades exhaust the volume standing ahead in the queue.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Literal, Optional
from shared.schemas.execution import OrderSide, OrderStatus, OrderType, PaperFill, PaperOrder
from shared.schemas.market_data import TradeTick


@dataclass
class PendingQueueOrder:
    order: PaperOrder
    queue_ahead_volume: int
    filled_quantity: int = 0


class SimulatedMatchingEngine:
    """
    Queue-aware order matching simulator.
    """

    def __init__(self, slippage_ticks: int = 1, tick_size: float = 0.05):
        self.slippage_ticks = slippage_ticks
        self.tick_size = tick_size
        self.orders: Dict[str, PaperOrder] = {}
        self.pending_limit_buys: Dict[str, List[PendingQueueOrder]] = {}  # instrument_id -> list
        self.pending_limit_sells: Dict[str, List[PendingQueueOrder]] = {} # instrument_id -> list
        self.fills: List[PaperFill] = []

    def submit_order(
        self,
        order: PaperOrder,
        best_bid: Optional[float] = None,
        best_ask: Optional[float] = None,
        level_depth_volume: int = 0,
    ) -> Optional[PaperFill]:
        """
        Accepts an order and attempts immediate execution or enqueues it.
        """
        self.orders[order.order_id] = order

        if order.order_type == OrderType.MARKET:
            fill_price = 0.0
            if order.side == OrderSide.BUY:
                fill_price = best_ask if best_ask is not None else (order.price or 100.0)
                fill_price += (self.slippage_ticks * self.tick_size)
            else:
                fill_price = best_bid if best_bid is not None else (order.price or 100.0)
                fill_price -= (self.slippage_ticks * self.tick_size)

            return self._record_fill(order, fill_price, order.quantity, order.created_time_utc)

        elif order.order_type == OrderType.LIMIT:
            if order.price is None:
                raise ValueError("Limit order requires price")

            # Check if marketable limit
            if order.side == OrderSide.BUY and best_ask is not None and order.price >= best_ask:
                return self._record_fill(order, best_ask, order.quantity, order.created_time_utc)
            elif order.side == OrderSide.SELL and best_bid is not None and order.price <= best_bid:
                return self._record_fill(order, best_bid, order.quantity, order.created_time_utc)

            # Rest on the book with queue-ahead tracking
            updated_order = order.model_copy(update={"queue_ahead_volume": max(0, level_depth_volume)})
            self.orders[order.order_id] = updated_order
            q_order = PendingQueueOrder(order=updated_order, queue_ahead_volume=updated_order.queue_ahead_volume)

            inst_id = order.instrument_id
            if order.side == OrderSide.BUY:
                self.pending_limit_buys.setdefault(inst_id, []).append(q_order)
            else:
                self.pending_limit_sells.setdefault(inst_id, []).append(q_order)

            return None

        return None

    def on_trade_tick(self, tick: TradeTick) -> List[PaperFill]:
        """
        Process incoming trade tick against resting queue orders.
        """
        fills: List[PaperFill] = []
        inst_id = tick.instrument_id
        ts_ms = tick.timestamp_ns // 1_000_000

        # 1. Evaluate Buy Limit Orders
        if inst_id in self.pending_limit_buys:
            remaining_buys: List[PendingQueueOrder] = []
            for item in self.pending_limit_buys[inst_id]:
                limit_p = item.order.price
                if limit_p is None:
                    continue

                if tick.price < limit_p:
                    # Traded through: Immediate fill!
                    fill = self._record_fill(item.order, limit_p, item.order.quantity, ts_ms)
                    fills.append(fill)
                elif abs(tick.price - limit_p) < 1e-4:
                    # Traded at limit price: exhaust queue-ahead volume
                    if item.queue_ahead_volume > 0:
                        item.queue_ahead_volume = max(0, item.queue_ahead_volume - tick.quantity)

                    if item.queue_ahead_volume <= 0:
                        fill = self._record_fill(item.order, limit_p, item.order.quantity, ts_ms)
                        fills.append(fill)
                    else:
                        remaining_buys.append(item)
                else:
                    # Price above limit, still pending
                    remaining_buys.append(item)
            self.pending_limit_buys[inst_id] = remaining_buys

        # 2. Evaluate Sell Limit Orders
        if inst_id in self.pending_limit_sells:
            remaining_sells: List[PendingQueueOrder] = []
            for item in self.pending_limit_sells[inst_id]:
                limit_p = item.order.price
                if limit_p is None:
                    continue

                if tick.price > limit_p:
                    # Traded through: Immediate fill!
                    fill = self._record_fill(item.order, limit_p, item.order.quantity, ts_ms)
                    fills.append(fill)
                elif abs(tick.price - limit_p) < 1e-4:
                    # Traded at limit price
                    if item.queue_ahead_volume > 0:
                        item.queue_ahead_volume = max(0, item.queue_ahead_volume - tick.quantity)

                    if item.queue_ahead_volume <= 0:
                        fill = self._record_fill(item.order, limit_p, item.order.quantity, ts_ms)
                        fills.append(fill)
                    else:
                        remaining_sells.append(item)
                else:
                    remaining_sells.append(item)
            self.pending_limit_sells[inst_id] = remaining_sells

        return fills

    def _record_fill(self, order: PaperOrder, price: float, quantity: int, timestamp_utc: int) -> PaperFill:
        fill_id = f"FILL_{len(self.fills) + 1:06d}"
        updated_order = order.model_copy(update={
            "status": OrderStatus.FILLED,
            "filled_quantity": quantity,
            "avg_fill_price": price,
            "updated_time_utc": timestamp_utc,
        })
        self.orders[order.order_id] = updated_order

        fill = PaperFill(
            fill_id=fill_id,
            order_id=order.order_id,
            timestamp_utc=timestamp_utc,
            price=price,
            quantity=quantity,
            fee=0.0,
            slippage=abs(price - (order.price or price)),
        )
        self.fills.append(fill)
        return fill
