"""Bounded Browserbase session pool for eager JD fetching.

A process-global semaphore caps total concurrent cloud-browser sessions across
ALL requests so a burst of users can't exceed the plan. ``fetch_jd`` acquires a
slot, fetches one job's description via the platform fetcher, and retries once on
an empty result (a transient wall) before giving up ('' -> caller skips the job).
"""

from __future__ import annotations

import asyncio
import logging

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


async def _fetch_once(platform: str, external_id: str, url: str) -> str:
    # Indirection so tests can stub the actual network fetch.
    from src.search import fetch_job_description
    return await fetch_job_description(platform, external_id, url)


async def fetch_jd(job: dict, *, retries: int = 1) -> str:
    """Fetch one job's JD under the global session cap, retrying once on empty."""
    platform = (job.get("platform") or "").lower()
    external_id = job.get("external_id", "")
    url = job.get("url", "")
    async with _semaphore():
        for _ in range(retries + 1):
            try:
                desc = await _fetch_once(platform, external_id, url)
            except Exception as e:
                log.warning("pool JD fetch error (%s): %s", external_id, e)
                desc = ""
            if desc and desc.strip():
                return desc
        return ""
