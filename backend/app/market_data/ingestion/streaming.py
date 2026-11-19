"""STRATLAB Ingestion: Real-Time Streaming Ingestion Worker.

Coordinates sequence gap detection, microsecond monotonic jitter buffering,
synthetic aggressor classification, and Redis event stream publishing.
"""

from typing import Any, Callable, Dict, List, Optional

from backend.app.database.redis_client import RedisCoordinator
from backend.app.market_data.quality.classifier import SyntheticClassifier
from backend.app.market_data.quality.gap_detector import SequenceGapDetector
from backend.app.market_data.quality.jitter_buffer import MonotonicJitterBuffer
from shared.schemas.market_data import TradeTick
from shared.schemas.provenance import AggressorSide, ProvenanceMetadata


class StreamingIngestionWorker:
    """
    Real-time streaming ingestion pipeline.
    """
    def __init__(
        self,
        jitter_window_ms: int = 50,
        redis_coordinator: Optional[RedisCoordinator] = None,
        on_tick_callback: Optional[Callable[[TradeTick], None]] = None,
    ):
        self.jitter_buffer = MonotonicJitterBuffer(window_ms=jitter_window_ms)
        self.gap_detector = SequenceGapDetector()
        self.classifier = SyntheticClassifier()
        self.redis = redis_coordinator
        self.callback = on_tick_callback

    def on_raw_tick(
        self,
        tick: TradeTick,
        arrival_ns: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Process incoming streaming trade tick through quality filters:
        1. Check sequence monotonicity & detect gaps.
        2. Infer aggressor side if unknown via Lee-Ready / Quote match.
        3. Enqueue in monotonic jitter buffer.
        """
        # 1. Sequence gap analysis
        gap_info = self.gap_detector.check_sequence(tick.instrument_id, tick.sequence_id)

        # 2. Classify aggressor side if unclassified
        if tick.aggressor == AggressorSide.UNKNOWN:
            inferred_side, prov = self.classifier.classify_tick(
                instrument_id=tick.instrument_id,
                price=tick.price,
                bid=tick.bid,
                ask=tick.ask,
                source_id=tick.provenance.source_id,
            )
            # Reconstruct tick with classified aggressor
            tick = TradeTick(
                instrument_id=tick.instrument_id,
                timestamp_ns=tick.timestamp_ns,
                price=tick.price,
                quantity=tick.quantity,
                aggressor=inferred_side,
                bid=tick.bid,
                ask=tick.ask,
                sequence_id=tick.sequence_id,
                provenance=prov,
            )

        # 3. Enqueue into monotonic jitter buffer
        self.jitter_buffer.push(
            timestamp_ns=tick.timestamp_ns,
            sequence_id=tick.sequence_id,
            payload=tick,
            arrival_ns=arrival_ns,
        )

        return gap_info

    def poll_ready_ticks(self, current_time_ns: Optional[int] = None) -> List[TradeTick]:
        """
        Drain all ticks that have aged past the jitter window in strict monotonic order.
        Dispatches to Redis stream and registered callbacks.
        """
        ready_ticks = self.jitter_buffer.pop_ready(current_time_ns)
        for t in ready_ticks:
            if self.redis:
                self.redis.publish_event(
                    stream_key=f"market.ticks.{t.instrument_id}",
                    data=t.model_dump(),
                )
            if self.callback:
                self.callback(t)
        return ready_ticks

    def flush(self) -> List[TradeTick]:
        """Drain all buffered ticks immediately."""
        all_ticks = self.jitter_buffer.flush_all()
        for t in all_ticks:
            if self.redis:
                self.redis.publish_event(
                    stream_key=f"market.ticks.{t.instrument_id}",
                    data=t.model_dump(),
                )
            if self.callback:
                self.callback(t)
        return all_ticks
