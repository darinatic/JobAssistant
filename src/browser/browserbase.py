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
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from src.scrapers.base import JobDetail
from src.scrapers.parsing import normalize_experience, parse_salary
from src.utils.config import settings

log = logging.getLogger(__name__)

_LINKEDIN_VIEW = "https://www.linkedin.com/jobs/view/{job_id}/"
_DESC_SELECTORS = ["div.show-more-less-html__markup", "div.description__text"]
_SALARY_SELECTORS = ["div.salary", "div.compensation__salary", ".compensation__salary-range"]


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


async def _close_quietly(browser) -> None:
    """Best-effort browser disconnect — a close failure must NOT skip session release."""
    try:
        await browser.close()
    except Exception as e:
        log.warning("Browserbase browser close failed: %s", e)


@asynccontextmanager
async def _connected_page() -> AsyncIterator[object]:
    """Create a Browserbase session and yield a Playwright page bound to it.

    The session is ALWAYS released — even if connect_over_cdp or browser.close
    throws — so a failure can't leak a session (which would hold a concurrency slot
    and keep billing until Browserbase's idle timeout). ``create_session`` is
    outside the try on purpose: if it fails, no session exists to release.
    """
    from patchright.async_api import async_playwright

    bb, session = await create_session()
    try:
        async with async_playwright() as pw:
            browser = await pw.chromium.connect_over_cdp(session.connect_url)
            try:
                context = browser.contexts[0]
                page = context.pages[0] if context.pages else await context.new_page()
                yield page
            finally:
                await _close_quietly(browser)
    finally:
        await release_session(bb, session)


async def _read_detail(page) -> JobDetail:
    """Read description + salary + seniority off an already-navigated LinkedIn page."""
    description = ""
    for sel in _DESC_SELECTORS:
        el = await page.query_selector(sel)
        if el:
            description = (await el.inner_text()).strip()
            break

    salary_raw = None
    for sel in _SALARY_SELECTORS:
        el = await page.query_selector(sel)
        if el:
            text = (await el.inner_text()).strip()
            if text:
                salary_raw = text
                break
    salary_min, salary_max, salary_period = parse_salary(salary_raw)

    experience_raw = None
    for item in await page.query_selector_all("li.description__job-criteria-item"):
        head = await item.query_selector("h3.description__job-criteria-subheader")
        value = await item.query_selector("span.description__job-criteria-text")
        if head and value and "seniority level" in (await head.inner_text()).strip().lower():
            experience_raw = (await value.inner_text()).strip() or None
            break

    return JobDetail(
        description=description,
        salary_min=salary_min,
        salary_max=salary_max,
        salary_period=salary_period,
        salary_raw=salary_raw,
        experience_raw=experience_raw,
        experience_level=normalize_experience(experience_raw, "linkedin"),
    )


async def fetch_linkedin_details(jobs: list[dict]) -> AsyncIterator[tuple[dict, JobDetail]]:
    """Yield ``(job, JobDetail)`` for each LinkedIn job, via one proxied cloud browser.

    Never raises — on a session/page failure it yields empty details so the caller's
    enrichment still completes (and falls back gracefully).
    """
    try:
        async with _connected_page() as page:
            for job in jobs:
                detail = JobDetail()
                try:
                    await page.goto(
                        _LINKEDIN_VIEW.format(job_id=job.get("external_id", "")),
                        wait_until="domcontentloaded", timeout=30000,
                    )
                    detail = await _read_detail(page)
                except Exception as e:
                    log.warning("Browserbase LinkedIn fetch failed (%s): %s", job.get("external_id"), e)
                yield job, detail
    except Exception as e:
        log.warning("Browserbase session unavailable, skipping: %s", e)
        for job in jobs:
            yield job, JobDetail()


async def fetch_linkedin_descriptions(jobs: list[dict]) -> AsyncIterator[tuple[dict, str]]:
    """Backward-compatible description-only variant (scoring path needs text only)."""
    async for job, detail in fetch_linkedin_details(jobs):
        yield job, detail.description


async def fetch_one_linkedin(job_id: str) -> str:
    """Single-job convenience wrapper (used by the on-demand drawer fetch).

    Consume the generator FULLY (don't early-return after the first yield): an early
    return aclose()s it mid-flight, which runs the Playwright/session teardown during
    generator finalization and hangs on the Windows Proactor loop.
    """
    return (await fetch_one_linkedin_detail(job_id)).description


async def fetch_one_linkedin_detail(job_id: str) -> JobDetail:
    """Single-job DETAIL fetch (description + salary + seniority) via cloud browser."""
    out = [d async for _job, d in fetch_linkedin_details([{"external_id": job_id}])]
    return out[0] if out else JobDetail()
