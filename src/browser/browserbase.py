"""Browserbase-backed LinkedIn description fetching (optional).

LinkedIn's guest detail endpoint soft-walls by IP after a short burst, so a plain
httpx loop can only enrich the first handful of jobs. When Browserbase is configured
(``BROWSERBASE_API_KEY`` + ``BROWSERBASE_PROJECT_ID``), we instead drive a cloud
browser with residential proxies and navigate the public job page for each posting —
a trusted residential IP + real browser gets past the wall.

One session is reused for a whole batch (cheaper, and a single residential IP browsing
several job pages looks like a normal user). Off by default; billed per browser-minute.
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator

from src.utils.config import settings

log = logging.getLogger(__name__)

_LINKEDIN_VIEW = "https://www.linkedin.com/jobs/view/{job_id}/"
_DESC_SELECTORS = ["div.show-more-less-html__markup", "div.description__text"]


def enabled() -> bool:
    return settings.browserbase_enabled


async def create_session():
    """Create a Browserbase cloud-browser session. Returns ``(client, session)``;
    ``session.connect_url`` is a CDP endpoint for Playwright/patchright."""
    from browserbase import Browserbase

    bb = Browserbase(api_key=settings.browserbase_api_key.get_secret_value())
    create_kwargs: dict = {
        "project_id": settings.browserbase_project_id,
        "region": settings.browserbase_region,
    }
    if settings.browserbase_proxies:
        create_kwargs["proxies"] = True  # residential rotation — paid plans only
    # The SDK is synchronous; keep the event loop free while the session spins up.
    session = await asyncio.to_thread(bb.sessions.create, **create_kwargs)
    return bb, session


async def release_session(bb, session) -> None:
    """Explicitly release a session — don't rely on the disconnect, so a lingering
    session can't hold a concurrency slot. Best-effort; failures are logged only."""
    try:
        await asyncio.to_thread(
            bb.sessions.update, session.id,
            status="REQUEST_RELEASE", project_id=settings.browserbase_project_id,
        )
    except Exception as e:
        log.warning("Browserbase session release failed: %s", e)


@asynccontextmanager
async def _connected_page() -> AsyncIterator[object]:
    """Create a Browserbase session and yield a Playwright page bound to it."""
    from patchright.async_api import async_playwright

    bb, session = await create_session()
    async with async_playwright() as pw:
        browser = await pw.chromium.connect_over_cdp(session.connect_url)
        try:
            context = browser.contexts[0]
            page = context.pages[0] if context.pages else await context.new_page()
            yield page
        finally:
            await browser.close()
            await release_session(bb, session)


async def fetch_linkedin_descriptions(jobs: list[dict]) -> AsyncIterator[tuple[dict, str]]:
    """Yield ``(job, description)`` for each LinkedIn job, via one proxied cloud browser.

    Never raises — on a session/page failure it yields empty descriptions so the
    caller's enrichment still completes (and falls back gracefully).
    """
    try:
        async with _connected_page() as page:
            for job in jobs:
                desc = ""
                try:
                    job_id = job.get("external_id", "")
                    await page.goto(
                        _LINKEDIN_VIEW.format(job_id=job_id),
                        wait_until="domcontentloaded", timeout=30000,
                    )
                    for sel in _DESC_SELECTORS:
                        el = await page.query_selector(sel)
                        if el:
                            desc = (await el.inner_text()).strip()
                            break
                except Exception as e:
                    log.warning("Browserbase LinkedIn fetch failed (%s): %s", job.get("external_id"), e)
                yield job, desc
    except Exception as e:
        log.warning("Browserbase session unavailable, skipping: %s", e)
        for job in jobs:
            yield job, ""


async def fetch_one_linkedin(job_id: str) -> str:
    """Single-job convenience wrapper (used by the on-demand drawer fetch).

    Consume the generator FULLY (don't early-return after the first yield): an early
    return aclose()s it mid-flight, which runs the Playwright/session teardown during
    generator finalization and hangs on the Windows Proactor loop.
    """
    out = [desc async for _job, desc in fetch_linkedin_descriptions([{"external_id": job_id}])]
    return out[0] if out else ""
