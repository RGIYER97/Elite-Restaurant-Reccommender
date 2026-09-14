"""Small process-wide abuse limiter for Streamlit form submissions."""

from __future__ import annotations

from collections import OrderedDict, deque
from dataclasses import dataclass
from math import ceil
from threading import Lock
import time


MAX_TRACKED_BUCKETS = 30_000


@dataclass(frozen=True, slots=True)
class RateLimitRule:
    name: str
    limit: int
    window_seconds: int


@dataclass(frozen=True, slots=True)
class RateLimitDecision:
    allowed: bool
    retry_after_seconds: int = 0


class RateLimiter:
    """Apply several sliding-window rules atomically within one app process."""

    def __init__(self) -> None:
        self._events: OrderedDict[tuple[str, str], deque[float]] = OrderedDict()
        self._lock = Lock()

    def consume(
        self,
        subject: str,
        rules: tuple[RateLimitRule, ...],
        *,
        now: float | None = None,
    ) -> RateLimitDecision:
        timestamp = time.time() if now is None else now
        with self._lock:
            retry_after = 0
            queues: list[deque[float]] = []
            for rule in rules:
                key = (subject, rule.name)
                queue = self._events.setdefault(key, deque())
                self._events.move_to_end(key)
                cutoff = timestamp - rule.window_seconds
                while queue and queue[0] <= cutoff:
                    queue.popleft()
                queues.append(queue)
                if len(queue) >= rule.limit:
                    retry_after = max(
                        retry_after,
                        ceil(queue[0] + rule.window_seconds - timestamp),
                    )

            if retry_after:
                return RateLimitDecision(False, max(1, retry_after))

            for queue in queues:
                queue.append(timestamp)
            while len(self._events) > MAX_TRACKED_BUCKETS:
                self._events.popitem(last=False)
            return RateLimitDecision(True)
