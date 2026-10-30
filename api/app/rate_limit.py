from __future__ import annotations

import threading
import time
from collections import OrderedDict, deque


class RateLimiter:
    """Small bounded process-local limiter for the intentional single API instance."""

    MAX_KEYS = 2048

    def __init__(self) -> None:
        self._entries: OrderedDict[str, deque[float]] = OrderedDict()
        self._lock = threading.Lock()

    def allow(self, key: str, *, limit: int, window_seconds: int) -> tuple[bool, int]:
        now = time.monotonic()
        cutoff = now - window_seconds
        with self._lock:
            timestamps = self._entries.get(key)
            if timestamps is None:
                timestamps = deque()
                self._entries[key] = timestamps
            else:
                self._entries.move_to_end(key)
            while timestamps and timestamps[0] <= cutoff:
                timestamps.popleft()
            if len(timestamps) >= limit:
                retry_after = max(1, int(timestamps[0] + window_seconds - now) + 1)
                return False, retry_after
            timestamps.append(now)
            if len(self._entries) > self.MAX_KEYS:
                self._prune(now)
            while len(self._entries) > self.MAX_KEYS:
                self._entries.popitem(last=False)
            return True, 0

    def _prune(self, now: float) -> None:
        expiry = now - 3600
        expired = [key for key, values in self._entries.items() if not values or values[-1] <= expiry]
        for key in expired:
            self._entries.pop(key, None)


__all__ = ["RateLimiter"]
