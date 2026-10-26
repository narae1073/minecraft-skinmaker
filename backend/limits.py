"""Public-demo guards: per-IP rate limiting and upload size limit.

The deployment is public with no login, so keep two cheap guards:
- a sliding-window request limit per client IP on the expensive endpoint;
- a hard upload size cap before the image is parsed.

Both are configurable by environment and can be disabled for tests
(``SKINMAKER_RATE_LIMIT_PER_MIN=0``).
"""
from __future__ import annotations

import os
import time
from collections import defaultdict, deque
from threading import Lock

WINDOW_SECONDS = 60.0
DEFAULT_PER_MIN = 6
DEFAULT_MAX_UPLOAD_MB = 15.0
TRUSTED_PROXIES = frozenset({"127.0.0.1", "::1"})


def rate_limit_per_min() -> int:
    raw = os.environ.get("SKINMAKER_RATE_LIMIT_PER_MIN", str(DEFAULT_PER_MIN))
    try:
        return max(0, int(raw))
    except (TypeError, ValueError):
        return DEFAULT_PER_MIN


def max_upload_bytes() -> int:
    raw = os.environ.get("SKINMAKER_MAX_UPLOAD_MB", str(DEFAULT_MAX_UPLOAD_MB))
    try:
        mb = float(raw)
    except (TypeError, ValueError):
        mb = DEFAULT_MAX_UPLOAD_MB
    return int(max(1.0, mb) * 1024 * 1024)


class RateLimiter:
    """Sliding-window limiter. One process (uvicorn --workers 1), in memory."""

    def __init__(self, limit: int | None = None, window: float = WINDOW_SECONDS):
        self.limit = rate_limit_per_min() if limit is None else max(0, int(limit))
        self.window = window
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = Lock()

    def allow(self, key: str, now: float | None = None) -> bool:
        if self.limit <= 0:
            return True
        t = time.monotonic() if now is None else now
        with self._lock:
            hits = self._hits[key]
            while hits and t - hits[0] >= self.window:
                hits.popleft()
            if len(hits) >= self.limit:
                return False
            hits.append(t)
            return True


def client_ip(request) -> str:
    """Real client IP behind cloudflared, but only trust headers from loopback.

    uvicorn binds 127.0.0.1 and only cloudflared connects to it. If someone
    reaches the app from another interface, headers are ignored.
    """
    peer = request.client.host if request.client else ""
    if peer in TRUSTED_PROXIES:
        cf = (request.headers.get("cf-connecting-ip") or "").strip()
        if cf:
            return cf
        forwarded = (request.headers.get("x-forwarded-for") or "").split(",")[0].strip()
        if forwarded:
            return forwarded
    return peer or "unknown"
