"""Stateless job search — run scrapers, optionally rank by CV relevance.

No persistence, no auth: the client holds the results. Offers a collect-all
(`search_jobs`) and a progressive (`search_jobs_stream`) variant.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import asdict
from typing import AsyncIterator

from src.matching import extract_skills
from src.scrapers import SearchParams, build_scraper
from src.scrapers.base import DiscoveredJob

log = logging.getLogger(__name__)

DEFAULT_PLATFORMS = ["mycareersfuture", "linkedin", "jobstreet"]
# Reliability-tuned per-platform ceilings (LinkedIn guest soft-walls fast; MCF's
# JSON API is reliable so it can go higher).
_CAPS = {"mycareersfuture": 80, "linkedin": 20, "jobstreet": 25}
# Relative share of a large search budget. The higher-volume boards (JobStreet,
# LinkedIn, Careers@Gov) get more than MCF, per how many listings each carries.
_WEIGHTS = {"jobstreet": 3, "linkedin": 3, "careersgov": 3, "mycareersfuture": 1}

_SENTINEL = object()  # one per platform task signals "this platform is done"


def _platform_budgets(targets: list[str], max_jobs: int) -> dict[str, int]:
    """Split ``max_jobs`` across platforms proportional to ``_WEIGHTS``, each
    clamped to its ``_CAPS`` reliability ceiling and at least 1. Replaces the old
    first-arrived race so a fast platform (MCF) can't starve the slow browser ones.
    The realized total is the sum of budgets (≤ max_jobs, less when caps bind)."""
    weights = {p: _WEIGHTS.get(p, 1) for p in targets}
    total_w = sum(weights.values()) or 1
    return {
        p: max(1, min(round(max_jobs * weights[p] / total_w), _CAPS.get(p, max_jobs)))
        for p in targets
    }


def _skill_split(title: str, description: str, cv_skills: set[str] | None) -> dict:
    """Split a job's skills (from title + description) into have/missing + relevance."""
    if cv_skills is None:
        return {}
    jd_skills = extract_skills(f"{title} {description or ''}")
    have = jd_skills & cv_skills
    return {
        "matched_skills": sorted(have),
        "missing_skills": sorted(jd_skills - cv_skills),
        "relevance": round(100 * len(have) / len(jd_skills)) if jd_skills else 0,
    }


async def _fit_pct(cv: str | None, title: str, description: str) -> int | None:
    """Learned resume↔JD fit as 0-100, or None when the predictor is off / inputs
    are missing. OFF by default (``MATCH_PREDICTOR_MODEL``), so this is a no-op that
    returns instantly unless a model is configured — see ``src/match_predictor.py``.
    Adds a semantic ranking signal on top of the lexical gazetteer relevance."""
    if not cv or not (description or "").strip():
        return None
    from src import match_predictor
    if not match_predictor.is_enabled():
        return None
    prob = await asyncio.to_thread(match_predictor.predict_fit, cv, f"{title}\n{description}")
    return round(prob * 100) if prob is not None else None


def _enrich(job: DiscoveredJob, cv_skills: set[str] | None) -> dict:
    """Job dict + (when a CV is given) the JD's skills split into have/missing + relevance."""
    item = asdict(job)
    # A description isn't always available (e.g. LinkedIn soft-walls the per-job
    # detail fetch), so extract from title + description together.
    item["has_description"] = bool((job.description or "").strip())
    item.update(_skill_split(job.title, job.description or "", cv_skills))
    return item


async def _scrape(
    keyword: str,
    location: str,
    platforms: list[str] | None,
    max_jobs: int,
    date_posted: str,
    experience_levels: list[str] | None,
    remote_options: list[str] | None,
    cv_skills: set[str] | None,
    fetch_descriptions: bool,
    master_cv: str | None = None,
) -> AsyncIterator[dict]:
    """Yield enriched job dicts, scraping all platforms **concurrently**.

    Each platform runs in its own task feeding a shared queue; results are
    yielded as they arrive (fast MCF jobs no longer wait behind the slow
    browser-based scrapers). Wall-clock ≈ the slowest platform, not the sum.
    """
    targets = platforms or DEFAULT_PLATFORMS
    budgets = _platform_budgets(targets, max_jobs)
    queue: asyncio.Queue = asyncio.Queue()

    async def run(platform: str) -> None:
        try:
            scraper = build_scraper(platform)
        except ValueError as e:
            log.warning("Skipping unknown platform: %s", e)
            await queue.put(_SENTINEL)
            return

        params = SearchParams(
            keyword=keyword,
            location=location,
            max_jobs=budgets.get(platform, max_jobs),
            date_posted=date_posted,
            experience_levels=experience_levels or [],
            remote_options=remote_options or [],
            fetch_descriptions=fetch_descriptions,
        )
        try:
            async for job in scraper.search(params):
                item = _enrich(job, cv_skills)
                fit = await _fit_pct(master_cv, job.title, job.description or "")
                if fit is not None:
                    item["fit"] = fit
                await queue.put(item)
        except Exception as e:
            log.warning("Scraper %s failed: %s", platform, e)
        finally:
            await queue.put(_SENTINEL)

    tasks = [asyncio.create_task(run(p)) for p in targets]
    remaining = len(tasks)
    yielded = 0
    # Each platform now self-limits to its own budget, so the total is bounded by
    # the sum of budgets — drain until every platform signals done (with that sum
    # as a safety ceiling in case a scraper over-delivers).
    total_budget = sum(budgets.values())
    try:
        while remaining and yielded < total_budget:
            item = await queue.get()
            if item is _SENTINEL:
                remaining -= 1
                continue
            yield item
            yielded += 1
    finally:
        for t in tasks:
            t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


async def search_jobs(
    keyword: str,
    location: str = "Singapore",
    platforms: list[str] | None = None,
    max_jobs: int = 25,
    date_posted: str = "any",
    experience_levels: list[str] | None = None,
    remote_options: list[str] | None = None,
    master_cv: str | None = None,
    fetch_descriptions: bool = False,
) -> list[dict]:
    """Collect all jobs, then (with a CV) sort by relevance. Deterministic — no LLM."""
    cv_skills = extract_skills(master_cv) if master_cv else None
    jobs = [
        job async for job in _scrape(
            keyword, location, platforms, max_jobs, date_posted,
            experience_levels, remote_options, cv_skills, fetch_descriptions, master_cv,
        )
    ]
    if cv_skills is not None:
        # Rank by learned fit when the predictor is on, else lexical relevance.
        jobs.sort(key=lambda j: j.get("fit", j.get("relevance", 0)), reverse=True)
    return jobs


async def search_jobs_stream(
    keyword: str,
    location: str = "Singapore",
    platforms: list[str] | None = None,
    max_jobs: int = 25,
    date_posted: str = "any",
    experience_levels: list[str] | None = None,
    remote_options: list[str] | None = None,
    master_cv: str | None = None,
    fetch_descriptions: bool = False,
) -> AsyncIterator[dict]:
    """Progressive variant — yields each job as it's scraped across all platforms."""
    cv_skills = extract_skills(master_cv) if master_cv else None
    async for job in _scrape(
        keyword, location, platforms, max_jobs, date_posted,
        experience_levels, remote_options, cv_skills, fetch_descriptions, master_cv,
    ):
        yield job


async def fetch_job_description(platform: str, external_id: str, url: str) -> str:
    """On-demand single-job description fetch — called when a job is opened.

    Search returns LinkedIn/JobStreet cards without descriptions (to stay fast and
    dodge LinkedIn's burst wall); this fills one in on request. MCF descriptions are
    already inline, so this is only a fallback there.
    """
    platform = (platform or "").lower()
    try:
        if platform == "linkedin":
            from src.browser import browserbase as bb
            if bb.enabled():
                return await bb.fetch_one_linkedin(external_id)
            from src.scrapers.linkedin import LinkedInGuestScraper
            return await LinkedInGuestScraper.fetch_one(external_id)
        if platform == "jobstreet":
            from src.scrapers.jobstreet import JobStreetScraper
            return await JobStreetScraper.fetch_one(url)
        if platform == "mycareersfuture":
            from src.jd_extract import extract_jd_from_url
            return await extract_jd_from_url(url)
    except Exception as e:
        log.warning("On-demand description fetch failed (%s): %s", platform, e)
    return ""


def _skill_update(job: dict, description: str, cv_skills: set[str] | None) -> dict:
    """Build a per-job enrichment update the client patches onto its listing card."""
    out = {
        "platform": job.get("platform"),
        "external_id": job.get("external_id"),
        "description": description,
        "has_description": bool((description or "").strip()),
    }
    if description.strip():
        out.update(_skill_split(job.get("title", ""), description, cv_skills))
    return out


async def enrich_descriptions_stream(
    jobs: list[dict], master_cv: str | None = None,
) -> AsyncIterator[dict]:
    """Fetch full descriptions for cards that lack them, streaming skill updates.

    Groups by platform and reuses a SINGLE session per platform (one browser for all
    JobStreet jobs, one HTTP client for all LinkedIn jobs) rather than one per job.
    Platform groups run concurrently. This backfills every listing's keywords after
    the fast card render — slower, but complete. LinkedIn still soft-walls a long
    burst, so its tail may come back description-less; that's an inherent guest-scrape
    limit (a proxy pool / Browserbase would raise it).
    """
    cv_skills = extract_skills(master_cv) if master_cv else None
    groups: dict[str, list[dict]] = {}
    for j in jobs:
        if (j.get("description") or "").strip():
            continue  # already has keywords
        groups.setdefault((j.get("platform") or "").lower(), []).append(j)
    if not groups:
        return

    queue: asyncio.Queue = asyncio.Queue()

    async def _update(job: dict, desc: str) -> dict:
        upd = _skill_update(job, desc, cv_skills)
        fit = await _fit_pct(master_cv, job.get("title", ""), desc)
        if fit is not None:
            upd["fit"] = fit
        return upd

    async def run_linkedin(items: list[dict]) -> None:
        from src.browser import browserbase as bb
        try:
            # Preferred: proxied cloud browser gets past LinkedIn's guest IP wall.
            if bb.enabled():
                async for job, desc in bb.fetch_linkedin_descriptions(items):
                    await queue.put(await _update(job, desc))
                return
            # Free fallback: guest httpx loop — walls after ~5-10 jobs.
            import random
            import httpx
            from src.scrapers.linkedin import LinkedInGuestScraper, _DEFAULT_HEADERS
            s = LinkedInGuestScraper()
            async with httpx.AsyncClient(timeout=30.0, headers=_DEFAULT_HEADERS, follow_redirects=True) as client:
                for job in items:
                    try:
                        desc = await s._fetch_description(client, job.get("external_id", ""))
                    except Exception:
                        desc = ""
                    await queue.put(await _update(job, desc))
                    await asyncio.sleep(random.uniform(2.0, 5.0))  # ease off LinkedIn's rate wall
        finally:
            await queue.put(_SENTINEL)

    async def run_jobstreet(items: list[dict]) -> None:
        from src.browser.stealth import HumanBehavior, StealthBrowser
        from src.scrapers.jobstreet import JobStreetScraper
        s = JobStreetScraper()
        try:
            async with StealthBrowser(headless=True) as browser:
                for job in items:
                    try:
                        desc = await s._fetch_description(browser, job.get("url", ""))
                    except Exception:
                        desc = ""
                    await queue.put(await _update(job, desc))
                    await HumanBehavior.random_delay(1200, 2500)
        finally:
            await queue.put(_SENTINEL)

    async def run_other(platform: str, items: list[dict]) -> None:
        try:
            for job in items:
                desc = await fetch_job_description(platform, job.get("external_id", ""), job.get("url", ""))
                await queue.put(await _update(job, desc))
        finally:
            await queue.put(_SENTINEL)

    tasks: list = []
    for platform, items in groups.items():
        if platform == "linkedin":
            tasks.append(asyncio.create_task(run_linkedin(items)))
        elif platform == "jobstreet":
            tasks.append(asyncio.create_task(run_jobstreet(items)))
        else:
            tasks.append(asyncio.create_task(run_other(platform, items)))

    remaining = len(tasks)
    try:
        while remaining:
            item = await queue.get()
            if item is _SENTINEL:
                remaining -= 1
                continue
            yield item
    finally:
        for t in tasks:
            t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
