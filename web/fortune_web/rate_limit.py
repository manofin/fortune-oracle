"""Bounded process-local request windows; never store raw session cookies."""
from collections import OrderedDict
from dataclasses import dataclass
import math
import threading
import time


@dataclass(frozen=True)
class RateDecision:
    error: str | None = None
    retry_after: int = 0


class FixedWindowLimiter:
    """One window per verified session or unauthenticated transport peer.

    Entries stay in creation order; their start time is never extended by a
    request. This makes expiry bounded without scanning every live bucket.
    Limits apply to this process, not across multiple workers or servers.
    """

    def __init__(self, requests=120, window=60, capacity=4096, *, clock=time.monotonic):
        for name, value in (("requests", requests), ("window", window), ("capacity", capacity)):
            if type(value) is not int or value < 1:
                raise ValueError(f"Rate limit {name} must be a positive integer")
        self.requests, self.window, self.capacity = requests, window, capacity
        self._clock = clock
        self._lock = threading.Lock()
        self._buckets = OrderedDict()

    def consume(self, identity):
        with self._lock:
            now = self._clock()
            while self._buckets:
                oldest, (start, _) = next(iter(self._buckets.items()))
                if now - start < self.window:
                    break
                del self._buckets[oldest]
            if identity not in self._buckets:
                if len(self._buckets) >= self.capacity:
                    start = next(iter(self._buckets.values()))[0]
                    return RateDecision("busy", max(1, math.ceil(start + self.window - now)))
                self._buckets[identity] = (now, 1)
                return RateDecision()
            start, count = self._buckets[identity]
            if count >= self.requests:
                return RateDecision("rate_limited", max(1, math.ceil(start + self.window - now)))
            self._buckets[identity] = (start, count + 1)
            return RateDecision()
