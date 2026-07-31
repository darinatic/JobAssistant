"""Guards on the Browserbase helpers' shapes — a misplaced @asynccontextmanager
decorator once silently broke ALL cloud-browser description fetching (empty results,
no error). These catch that class of regression without hitting the network."""

import inspect
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.browser import browserbase as bb
from src.scrapers.base import JobDetail


def test_create_session_is_a_plain_coroutine():
    # Must be awaitable (`bb, session = await create_session()`), NOT a context
    # manager. If @asynccontextmanager lands here, this flips to False.
    assert inspect.iscoroutinefunction(bb.create_session)


def test_connected_page_is_an_async_context_manager():
    # Must support `async with _connected_page() as page`. Calling it does NOT run
    # the body (that happens on __aenter__), so this touches no network.
    cm = bb._connected_page()
    assert hasattr(cm, "__aenter__") and hasattr(cm, "__aexit__")


def test_proxies_config_geo_targets_configured_location(monkeypatch):
    monkeypatch.setattr(bb.settings, "browserbase_proxies", True)
    monkeypatch.setattr(bb.settings, "browserbase_proxy_country", "SG")
    monkeypatch.setattr(bb.settings, "browserbase_proxy_city", "SINGAPORE")
    assert bb._proxies_config() == [
        {"type": "browserbase", "geolocation": {"country": "SG", "city": "SINGAPORE"}}
    ]


def test_proxies_config_off_and_default_geo(monkeypatch):
    monkeypatch.setattr(bb.settings, "browserbase_proxies", False)
    assert bb._proxies_config() is None  # proxies disabled → no proxy kwarg
    monkeypatch.setattr(bb.settings, "browserbase_proxies", True)
    monkeypatch.setattr(bb.settings, "browserbase_proxy_country", "")
    assert bb._proxies_config() is True  # blank country → Browserbase default geo


class _FakePlaywrightCM:
    """Stands in for `async_playwright()` — an async context manager yielding `pw`."""
    def __init__(self, pw):
        self._pw = pw

    async def __aenter__(self):
        return self._pw

    async def __aexit__(self, *exc):
        return False


def _stub_session(monkeypatch, session_id: str):
    """Stub create_session/release_session; return the list release ids land in."""
    released: list[str] = []
    session = MagicMock(id=session_id, connect_url="ws://fake")

    async def _create():
        return MagicMock(), session

    async def _release(_bb, s):
        released.append(s.id)

    monkeypatch.setattr(bb, "create_session", _create)
    monkeypatch.setattr(bb, "release_session", _release)
    return released


@pytest.mark.asyncio
async def test_connected_page_releases_session_when_connect_fails(monkeypatch):
    # Leak path: create_session succeeds, connect_over_cdp throws. The session must
    # still be released (it lives outside the try, but the outer finally covers it).
    released = _stub_session(monkeypatch, "s-connect")
    pw = MagicMock()
    pw.chromium.connect_over_cdp = AsyncMock(side_effect=RuntimeError("connect boom"))
    monkeypatch.setattr("patchright.async_api.async_playwright", lambda: _FakePlaywrightCM(pw))

    with pytest.raises(RuntimeError, match="connect boom"):
        async with bb._connected_page():
            pass
    assert released == ["s-connect"]


@pytest.mark.asyncio
async def test_connected_page_releases_session_when_close_fails(monkeypatch):
    # Leak path: browser.close() throws during teardown — release must still run.
    released = _stub_session(monkeypatch, "s-close")
    browser = MagicMock()
    browser.close = AsyncMock(side_effect=RuntimeError("close boom"))
    ctx = MagicMock()
    ctx.pages = [MagicMock()]
    browser.contexts = [ctx]
    pw = MagicMock()
    pw.chromium.connect_over_cdp = AsyncMock(return_value=browser)
    monkeypatch.setattr("patchright.async_api.async_playwright", lambda: _FakePlaywrightCM(pw))

    async with bb._connected_page() as page:  # close boom is swallowed here
        assert page is ctx.pages[0]
    assert released == ["s-close"]


@pytest.mark.asyncio
async def test_stealth_browserbase_releases_session_on_start_failure(monkeypatch):
    # Leak path: StealthBrowser creates a session, then Playwright fails to start —
    # __aexit__ won't run, so start() must release the session itself before raising.
    from src.browser import stealth
    released = _stub_session(monkeypatch, "s-start")
    apw = MagicMock()
    apw.start = AsyncMock(side_effect=RuntimeError("pw boom"))
    monkeypatch.setattr(stealth, "async_playwright", lambda: apw)

    sb = stealth.StealthBrowser(via_browserbase=True)
    with pytest.raises(RuntimeError, match="pw boom"):
        await sb.start()
    assert released == ["s-start"]


@pytest.mark.asyncio
async def test_fetch_linkedin_details_rotates_sessions(monkeypatch):
    # Batch rotation: a fresh session every N jobs so a burst can't wall the tail.
    monkeypatch.setattr(bb.settings, "browserbase_jobs_per_session", 2)
    sessions = 0
    page = MagicMock()
    page.goto = AsyncMock()

    @asynccontextmanager
    async def fake_connected_page():
        nonlocal sessions
        sessions += 1
        yield page

    async def fake_read(_page):
        return JobDetail(description="jd")

    monkeypatch.setattr(bb, "_connected_page", fake_connected_page)
    monkeypatch.setattr(bb, "_read_detail", fake_read)

    jobs = [{"external_id": str(i)} for i in range(5)]
    out = [d async for _job, d in bb.fetch_linkedin_details(jobs)]

    assert len(out) == 5 and all(d.description == "jd" for d in out)
    assert sessions == 3  # ceil(5 / 2) chunks -> 3 rotated sessions
