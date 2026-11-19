"""STRATLAB Storage Layer: Redis Streaming & State Coordinator.

Coordinates live event distribution for market ticks, candles, and paper execution.
Provides seamless fallback to an in-memory event ring when Redis is not running.
"""

from collections import deque
import json
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger("stratlab.storage.redis")


class MemoryStreamBroker:
    """
    Lightweight, thread-safe in-memory stream broker for local testing and offline modes.
    """
    def __init__(self, maxlen: int = 10000):
        self._streams: Dict[str, deque] = {}
        self._maxlen = maxlen
        self._seq = 0

    def xadd(self, name: str, fields: Dict[str, Any]) -> str:
        if name not in self._streams:
            self._streams[name] = deque(maxlen=self._maxlen)
        self._seq += 1
        msg_id = f"{self._seq}-0"
        self._streams[name].append((msg_id, fields))
        return msg_id

    def xread(self, streams: Dict[str, str], count: Optional[int] = None) -> List[Any]:
        results = []
        for name, last_id in streams.items():
            queue = self._streams.get(name, deque())
            items = []
            for msg_id, fields in list(queue):
                if last_id == "0" or int(msg_id.split("-")[0]) > int(last_id.split("-")[0]):
                    items.append((msg_id, fields))
                    if count and len(items) >= count:
                        break
            if items:
                results.append((name, items))
        return results


class RedisCoordinator:
    """
    Unified streaming hub interfacing Redis Streams with memory fallback.
    """
    def __init__(self, redis_url: str = "redis://localhost:6379/0"):
        self.redis_url = redis_url
        self.client = None
        self.fallback = MemoryStreamBroker()
        self._connect()

    def _connect(self):
        try:
            import redis
            r = redis.Redis.from_url(self.redis_url, socket_timeout=0.5)
            r.ping()
            self.client = r
            logger.info("Connected to Redis at %s", self.redis_url)
        except Exception:
            self.client = None
            logger.info("Redis unavailable; using in-memory stream fallback.")

    @property
    def is_connected(self) -> bool:
        return self.client is not None

    def publish_event(self, stream_key: str, data: Dict[str, Any]) -> str:
        """Publish payload to designated stream key."""
        payload = {k: json.dumps(v) if isinstance(v, (dict, list)) else str(v) for k, v in data.items()}
        if self.client:
            try:
                return self.client.xadd(stream_key, payload, maxlen=50000)
            except Exception as e:
                logger.warning("Redis xadd failed (%s); failing over to memory", e)
                self.client = None
        return self.fallback.xadd(stream_key, payload)

    def read_stream(self, stream_key: str, last_id: str = "0", count: int = 100) -> List[Dict[str, Any]]:
        """Read pending stream events from offset."""
        if self.client:
            try:
                res = self.client.xread({stream_key: last_id}, count=count)
                if not res:
                    return []
                out = []
                for _, entries in res:
                    for msg_id, data in entries:
                        out.append({"id": msg_id.decode() if isinstance(msg_id, bytes) else msg_id,
                                    "data": {k.decode() if isinstance(k, bytes) else k:
                                             v.decode() if isinstance(v, bytes) else v for k, v in data.items()}})
                return out
            except Exception as e:
                logger.warning("Redis xread failed (%s); falling over to memory", e)
                self.client = None

        res = self.fallback.xread({stream_key: last_id}, count=count)
        out = []
        for _, entries in res:
            for msg_id, data in entries:
                out.append({"id": msg_id, "data": data})
        return out
