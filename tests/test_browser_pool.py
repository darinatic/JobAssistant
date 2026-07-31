import asyncio

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


def test_session_slot_bounds_concurrency(monkeypatch):
    # The slot is the global cap every session path (gated/enrich/on-demand/JobStreet)
    # acquires; never more than BROWSERBASE_MAX_SESSIONS held at once.
    monkeypatch.setattr(pool.settings, "browserbase_max_sessions", 2)
    pool.reset_pool()
    live = 0
    peak = 0

    async def hold():
        nonlocal live, peak
        async with pool.session_slot():
            live += 1
            peak = max(peak, live)
            await asyncio.sleep(0.02)
            live -= 1

    async def run():
        await asyncio.gather(*(hold() for _ in range(8)))

    asyncio.run(run())
    assert peak <= 2


def test_acquire_release_slot_balance(monkeypatch):
    # acquire_slot/release_slot (used by StealthBrowser across start/close) balance.
    monkeypatch.setattr(pool.settings, "browserbase_max_sessions", 1)
    pool.reset_pool()

    async def run():
        await pool.acquire_slot()
        pool.release_slot()
        # after releasing, the single slot is free again → next acquire doesn't block
        await asyncio.wait_for(pool.acquire_slot(), timeout=0.5)
        pool.release_slot()

    asyncio.run(run())
