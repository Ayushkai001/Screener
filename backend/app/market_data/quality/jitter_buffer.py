"""STRATLAB Market Data Quality: Monotonic Jitter Buffer.

Buffers streaming trade packets within a microsecond window (default 50ms)
and drains them in strict exchange sequence & timestamp order, eliminating
network-induced out-of-order inversions.
"""

import heapq
import time
from typing import Any, List, Optional, Tuple


class MonotonicJitterBuffer:
    """
    Min-heap priority queue re-ordering jittered network packets.
    """
    def __init__(self, window_ms: int = 50, max_capacity: int = 50000):
        self.window_ns = window_ms * 1_000_000
        self.max_capacity = max_capacity
        # Heap elements: (timestamp_ns, sequence_id, arrival_ns, payload)
        self._heap: List[Tuple[int, int, int, Any]] = []

    def push(self, timestamp_ns: int, sequence_id: Optional[int], payload: Any, arrival_ns: Optional[int] = None) -> bool:
        """
        Enqueue a packet into the jitter buffer.
        """
        if len(self._heap) >= self.max_capacity:
            # Buffer capacity exceeded: force immediate pop
            return False

        arr_ns = arrival_ns if arrival_ns is not None else time.time_ns()
        seq = sequence_id if sequence_id is not None else 0
        heapq.heappush(self._heap, (timestamp_ns, seq, arr_ns, payload))
        return True

    def pop_ready(self, current_time_ns: Optional[int] = None) -> List[Any]:
        """
        Drain all packets that have aged past the jitter window.
        Returns: list of payloads sorted monotonically by timestamp & sequence.
        """
        now_ns = current_time_ns if current_time_ns is not None else time.time_ns()
        ready = []
        while self._heap:
            ts, seq, arrival_ns, payload = self._heap[0]
            if now_ns - arrival_ns >= self.window_ns:
                heapq.heappop(self._heap)
                ready.append(payload)
            else:
                break
        return ready

    def flush_all(self) -> List[Any]:
        """Drain all buffered items regardless of age (e.g. on shutdown)."""
        ready = []
        while self._heap:
            _, _, _, payload = heapq.heappop(self._heap)
            ready.append(payload)
        return ready

    @property
    def size(self) -> int:
        return len(self._heap)
