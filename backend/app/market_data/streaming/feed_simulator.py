"""STRATLAB Real-Time Market Feed Simulator.

Generates realistic high-frequency trade ticks, computes live footprint cluster
updates, checks resting queue orders in the matching engine, and broadcasts
events over WebSocket channels.
"""

from __future__ import annotations
import asyncio
import random
import time
from typing import Dict, Optional
from shared.schemas.market_data import TradeTick
from shared.schemas.provenance import AggressorSide, ProvenanceMetadata, SideMethod
from backend.app.analytics.footprint.aggregator import FootprintAggregator
from backend.app.api.routers.paper_trading import matching_engine, paper_ledger
from backend.app.api.routers.streaming import stream_manager


class MarketFeedSimulator:
    """
    Simulates high-frequency trade flow, live footprint building, and queue execution.
    """

    def __init__(self):
        self.is_running = False
        self._task: Optional[asyncio.Task] = None
        self.aggregators: Dict[str, FootprintAggregator] = {}
        self.current_prices: Dict[str, float] = {
            "INS_NSE_RELIANCE": 2504.0,
            "INS_NSE_NIFTY_FUT": 24200.0,
            "INS_BINANCE_BTCUSDT": 92500.0,
        }
        self.prov = ProvenanceMetadata.exchange_verified("SIMULATED_TBT")

    def start(self, interval_seconds: float = 0.5):
        """Start background tick simulation loop."""
        if not self.is_running:
            self.is_running = True
            self._task = asyncio.create_task(self._simulation_loop(interval_seconds))

    def stop(self):
        """Stop background tick simulation loop."""
        self.is_running = False
        if self._task:
            self._task.cancel()
            self._task = None

    async def _simulation_loop(self, interval_seconds: float):
        seq_id = 1000

        while self.is_running:
            try:
                for inst_id, base_price in list(self.current_prices.items()):
                    # Random price drift (geometric random walk)
                    price_change = random.choice([-0.05, 0.0, 0.05, 0.05, -0.05, 0.10, -0.10])
                    new_price = round(max(1.0, base_price + price_change), 2)
                    self.current_prices[inst_id] = new_price

                    # Random trade quantity and aggressor side
                    qty = random.randint(10, 250)
                    aggressor = random.choice([AggressorSide.BUY, AggressorSide.SELL])
                    now_ns = int(time.time() * 1_000_000_000)

                    tick = TradeTick(
                        instrument_id=inst_id,
                        timestamp_ns=now_ns,
                        price=new_price,
                        quantity=qty,
                        aggressor=aggressor,
                        sequence_id=seq_id,
                        bid=new_price - 0.05,
                        ask=new_price + 0.05,
                        provenance=self.prov,
                    )
                    seq_id += 1

                    # 1. Update Footprint Aggregator
                    if inst_id not in self.aggregators:
                        self.aggregators[inst_id] = FootprintAggregator(
                            instrument_id=inst_id,
                            timeframe="5m",
                            tick_size=0.05,
                            imbalance_ratio=3.0,
                            value_area_pct=0.70,
                        )

                    footprint_bar = self.aggregators[inst_id].process_tick(tick)

                    # 2. Feed tick into Queue-Aware Paper Matching Engine
                    fills = matching_engine.on_trade_tick(tick)
                    for fill in fills:
                        order = matching_engine.orders.get(fill.order_id)
                        if order:
                            paper_ledger.open_position(
                                instrument_id=inst_id,
                                symbol=inst_id,
                                side="LONG" if order.side == "BUY" else "SHORT",
                                price=fill.price,
                                quantity=fill.quantity,
                                timestamp_utc=fill.timestamp_utc,
                            )
                            # Broadcast fill on execution channel
                            await stream_manager.broadcast(
                                f"executions:{order.account_id}",
                                {
                                    "type": "EXECUTION_FILL",
                                    "fill_id": fill.fill_id,
                                    "order_id": fill.order_id,
                                    "price": fill.price,
                                    "quantity": fill.quantity,
                                    "timestamp_utc": fill.timestamp_utc,
                                },
                            )

                    # 3. Broadcast Market Tick & Footprint Updates over WebSocket
                    await stream_manager.broadcast(
                        f"candles:{inst_id}",
                        {
                            "type": "MARKET_TICK",
                            "instrument_id": inst_id,
                            "price": new_price,
                            "quantity": qty,
                            "aggressor": aggressor.value,
                            "timestamp_utc": int(now_ns / 1_000_000),
                        },
                    )

                    await stream_manager.broadcast(
                        f"footprint:{inst_id}",
                        {
                            "type": "FOOTPRINT_UPDATE",
                            "bar": footprint_bar.model_dump(),
                        },
                    )

                await asyncio.sleep(interval_seconds)

            except asyncio.CancelledError:
                break
            except Exception:
                await asyncio.sleep(interval_seconds)


feed_simulator = MarketFeedSimulator()
