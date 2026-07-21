"""In-memory per-IP rate limiting for the expensive endpoints (LLM + scrape).

Single-instance, best-effort — right-sized for a public no-auth demo on one machine.
Each guarded POST triggers Anthropic and/or Browserbase spend, so we cap per-IP
requests per minute and per day. State is in-memory (resets on restart), which is fine.
"""

from __future__ import annotations

import time
from collections import defaultdict, deque

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

# POST endpoints that cost money (Anthropic tokens, Browserbase minutes, or external scrape).
GUARDED_PATHS = {
    "/tailor", "/cover-letter", "/search", "/search/stream",
    "/jobs/enrich/stream", "/job/description", "/extract-jd",
}

_DAY = 86_400
_MINUTE = 60


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, *, per_min: int, per_day: int):
        super().__init__(app)
        self.per_min = per_min
        self.per_day = per_day
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._since_sweep = 0

    @staticmethod
    def _client_ip(request) -> str:
        # Behind Fly/most proxies the real client IP is in these headers.
        fly = request.headers.get("fly-client-ip")
        if fly:
            return fly
        xff = request.headers.get("x-forwarded-for", "")
        if xff:
            return xff.split(",")[0].strip()
        return request.client.host if request.client else "unknown"

    def _sweep(self, now: float) -> None:
        # Drop IPs with no requests in the last day so the map can't grow forever.
        cutoff = now - _DAY
        for ip in [ip for ip, dq in self._hits.items() if not dq or dq[-1] < cutoff]:
            del self._hits[ip]

    async def dispatch(self, request, call_next):
        if (self.per_min <= 0 and self.per_day <= 0) or request.method != "POST" \
                or request.url.path not in GUARDED_PATHS:
            return await call_next(request)

        now = time.time()
        self._since_sweep += 1
        if self._since_sweep >= 1000:
            self._since_sweep = 0
            self._sweep(now)

        dq = self._hits[self._client_ip(request)]
        while dq and dq[0] < now - _DAY:
            dq.popleft()

        if self.per_day and len(dq) >= self.per_day:
            return self._limited("Daily limit reached — please try again tomorrow.")
        if self.per_min and sum(1 for t in dq if t >= now - _MINUTE) >= self.per_min:
            return self._limited("You're going a bit fast — wait a minute and try again.")

        dq.append(now)
        return await call_next(request)

    @staticmethod
    def _limited(msg: str) -> JSONResponse:
        return JSONResponse(status_code=429, content={"detail": msg})
