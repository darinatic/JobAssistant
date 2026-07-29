import asyncio
from unittest.mock import patch

from src.browser import pool


def setup_function():
    pool.reset_pool()


def test_retries_once_on_empty(monkeypatch):
    calls = []

    async def fake_fetch(platform, external_id, url):
        calls.append(external_id)
        return "" if len(calls) == 1 else "Real JD text"

    monkeypatch.setattr(pool, "_fetch_once", fake_fetch)
    out = asyncio.run(pool.fetch_jd({"platform": "linkedin", "external_id": "1", "url": "u"}))
    assert out == "Real JD text"
    assert len(calls) == 2  # first empty -> retried once


def test_gives_up_after_retries(monkeypatch):
    async def always_empty(platform, external_id, url):
        return ""

    monkeypatch.setattr(pool, "_fetch_once", always_empty)
    out = asyncio.run(pool.fetch_jd({"platform": "linkedin", "external_id": "1", "url": "u"}))
    assert out == ""


def test_semaphore_bounds_concurrency(monkeypatch):
    monkeypatch.setattr(pool.settings, "browserbase_max_sessions", 2)
    pool.reset_pool()
    live = 0
    peak = 0

    async def slow(platform, external_id, url):
        nonlocal live, peak
        live += 1
        peak = max(peak, live)
        await asyncio.sleep(0.02)
        live -= 1
        return "JD"

    monkeypatch.setattr(pool, "_fetch_once", slow)

    async def run():
        jobs = [{"platform": "linkedin", "external_id": str(i), "url": "u"} for i in range(8)]
        await asyncio.gather(*(pool.fetch_jd(j) for j in jobs))

    asyncio.run(run())
    assert peak <= 2  # never more than the session cap in flight
