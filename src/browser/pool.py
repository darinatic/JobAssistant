"""Global Browserbase session cap.

A process-global semaphore caps total concurrent cloud-browser sessions across
ALL requests + paths so a burst of users can't exceed the plan. The slot is held
for a session's whole lifetime — acquired where a session is created
(``browserbase._connected_page`` and ``StealthBrowser``) and released when it's
torn down — so gated search, enrichment, on-demand fetches, and JobStreet are all
bounded by the SAME ``BROWSERBASE_MAX_SESSIONS`` limit.

``fetch_jd`` is the gated-search helper: fetch one job's JD (its underlying
session takes a slot), retrying once on an empty result (a transient wall) before
giving up ('' -> caller skips the job).
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from src.utils.config import settings

log = logging.getLogger(__name__)

_sem: asyncio.Semaphore | None = None


def _semaphore() -> asyncio.Semaphore:
    global _sem
    if _sem is None:
        _sem = asyncio.Semaphore(max(1, int(settings.browserbase_max_sessions)))
    return _sem


def reset_pool() -> None:
    """Test helper — drop the cached semaphore so a new cap takes effect."""
    global _sem
    _sem = None


async def acquire_slot() -> None:
    """Take one global session slot (blocks past the cap). Pair with ``release_slot``."""
    await _semaphore().acquire()


def release_slot() -> None:
    _semaphore().release()


@asynccontextmanager
async def session_slot():
    """Hold one session slot for the duration of the block (single-session paths)."""
    await acquire_slot()
    try:
        yield
    finally:
        release_slot()


async def _fetch_once(platform: str, external_id: str, url: str) -> str:
    # Indirection so tests can stub the actual network fetch.
    from src.search import fetch_job_description
    return await fetch_job_description(platform, external_id, url)


async def fetch_jd(job: dict, *, retries: int = 1) -> str:
    """Fetch one job's JD (the session it opens takes a global slot), retrying once
    on empty. No semaphore here — the slot lives at the session boundary, so gating
    it here too would double-acquire and deadlock the gated workers."""
    platform = (job.get("platform") or "").lower()
    external_id = job.get("external_id", "")
    url = job.get("url", "")
    for _ in range(retries + 1):
        try:
            desc = await _fetch_once(platform, external_id, url)
        except Exception as e:
            log.warning("pool JD fetch error (%s): %s", external_id, e)
            desc = ""
        if desc and desc.strip():
            return desc
    return ""
