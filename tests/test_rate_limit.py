"""Per-IP rate limiting for the expensive endpoints."""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.rate_limit import RateLimitMiddleware


def _client(per_min: int, per_day: int = 1000) -> TestClient:
    app = FastAPI()
    app.add_middleware(RateLimitMiddleware, per_min=per_min, per_day=per_day)

    @app.post("/search")
    def _search():
        return {"ok": True}

    @app.post("/unlisted")
    def _unlisted():
        return {"ok": True}

    @app.get("/health")
    def _health():
        return {"ok": True}

    return TestClient(app)


def test_blocks_after_per_minute_cap():
    c = _client(per_min=2)
    assert c.post("/search").status_code == 200
    assert c.post("/search").status_code == 200
    r = c.post("/search")
    assert r.status_code == 429 and "detail" in r.json()


def test_blocks_after_per_day_cap():
    c = _client(per_min=1000, per_day=2)
    assert c.post("/search").status_code == 200
    assert c.post("/search").status_code == 200
    assert c.post("/search").status_code == 429


def test_only_guarded_post_paths_are_limited():
    c = _client(per_min=1)
    for _ in range(4):
        assert c.post("/unlisted").status_code == 200   # not in GUARDED_PATHS
        assert c.get("/health").status_code == 200        # GET never limited


def test_zero_disables_limiting():
    c = _client(per_min=0, per_day=0)
    for _ in range(5):
        assert c.post("/search").status_code == 200
