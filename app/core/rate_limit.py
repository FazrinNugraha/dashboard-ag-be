"""Pembatas percobaan sederhana (in-memory).

Cukup untuk 1 instance backend (lihat PRD 6.5). Jika kelak multi-instance,
pindahkan state ke Redis.
"""
import threading
import time
from collections import defaultdict, deque

from app.core.errors import AppError


class SlidingWindowLimiter:
    def __init__(self, max_attempts: int, window_seconds: int) -> None:
        self.max_attempts = max_attempts
        self.window_seconds = window_seconds
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def _prune(self, key: str, now: float) -> deque[float]:
        hits = self._hits[key]
        while hits and now - hits[0] >= self.window_seconds:
            hits.popleft()
        return hits

    def check(self, key: str) -> None:
        """Lempar RATE_LIMITED bila batas sudah tercapai."""
        now = time.monotonic()
        with self._lock:
            hits = self._prune(key, now)
            if len(hits) >= self.max_attempts:
                retry_after = max(1, int(self.window_seconds - (now - hits[0])))
                raise AppError(
                    "RATE_LIMITED",
                    "Terlalu banyak percobaan. Coba lagi sebentar lagi.",
                    429,
                    {"retry_after_seconds": retry_after},
                )

    def hit(self, key: str) -> None:
        with self._lock:
            self._hits[key].append(time.monotonic())

    def reset(self, key: str) -> None:
        with self._lock:
            self._hits.pop(key, None)

    def clear(self) -> None:
        with self._lock:
            self._hits.clear()


# 5 percobaan gagal per menit per IP (PRD 7.1)
login_limiter = SlidingWindowLimiter(max_attempts=5, window_seconds=60)
