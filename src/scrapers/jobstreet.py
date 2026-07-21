"""JobStreet Singapore scraper.

Cloudflare blocks plain HTTP scraping, so we use Patchright (stealth
Playwright fork) to render the search page and pull jobs from the React DOM.
JobStreet uses stable `data-automation` attributes for testable selectors.
"""

from __future__ import annotations

import asyncio
import re
import urllib.parse
from typing import AsyncIterator

from src.browser.stealth import HumanBehavior, StealthBrowser
from src.scrapers.base import DiscoveredJob, JobScraper, SearchParams


# JobStreet's URL slug convention: lowercase, hyphen-separated.
_SLUG_RE = re.compile(r"[^a-z0-9]+")
_JOB_ID_RE = re.compile(r"/job/(\d+)")


def _slugify(text: str) -> str:
    return _SLUG_RE.sub("-", text.lower()).strip("-")


# date_posted → JobStreet's `daterange` (days). No native seniority/remote URL param.
_JS_DATERANGE = {"past_24_hours": "1", "past_week": "7", "past_month": "31"}


class JobStreetScraper(JobScraper):
    PLATFORM = "jobstreet"
    BASE_URL = "https://sg.jobstreet.com"

    async def search(self, params: SearchParams) -> AsyncIterator[DiscoveredJob]:
        # Hold all jobs in memory then yield — Patchright context lifetime
        # is easier to manage if we exit before yielding to the caller.
        jobs = await self._collect(params)
        for job in jobs:
            yield job

    async def _collect(self, params: SearchParams) -> list[DiscoveredJob]:
        results: list[DiscoveredJob] = []
        seen_ids: set[str] = set()

        async with StealthBrowser(headless=True) as browser:
            page_num = 1
            while len(results) < params.max_jobs:
                url = self._build_search_url(params, page_num)
                await browser.goto(url, wait_until="domcontentloaded")
                await HumanBehavior.random_delay(2000, 4000)

                cards = await browser.page.query_selector_all(
                    'article[data-automation="normalJob"], [data-card-type="JobCard"]'
                )
                if not cards:
                    break

                page_yielded = 0
                for card in cards:
                    if len(results) >= params.max_jobs:
                        break
                    try:
                        job = await self._parse_card(card)
                    except Exception:
                        continue
                    if not job or job.external_id in seen_ids:
                        continue
                    seen_ids.add(job.external_id)
                    results.append(job)
                    page_yielded += 1

                if page_yielded == 0:
                    break

                page_num += 1
                await HumanBehavior.random_delay(3000, 6000)

            # Fetch full descriptions for collected jobs — only when asked. Each
            # description is a separate page navigation, so doing all of them up
            # front dominates search time; search defers this to fetch_one.
            if params.fetch_descriptions:
                for job in results:
                    try:
                        job.description = await self._fetch_description(browser, job.url)
                    except Exception:
                        job.description = ""
                    await HumanBehavior.random_delay(1500, 3500)

        return results

    @classmethod
    async def fetch_one(cls, url: str) -> str:
        """On-demand single-job description fetch (used when a job is opened)."""
        self = cls()
        async with StealthBrowser(headless=True) as browser:
            try:
                return await self._fetch_description(browser, url)
            except Exception:
                return ""

    def _build_search_url(self, params: SearchParams, page: int) -> str:
        kw_slug = _slugify(params.keyword) or "jobs"
        loc_slug = urllib.parse.quote(params.location)
        url = f"{self.BASE_URL}/{kw_slug}-jobs/in-{loc_slug}?page={page}"
        daterange = _JS_DATERANGE.get(params.date_posted)
        if daterange:
            url += f"&daterange={daterange}"
        return url

    async def _parse_card(self, card) -> DiscoveredJob | None:
        title_link = await card.query_selector('a[data-automation="jobTitle"]')
        if not title_link:
            return None
        href = await title_link.get_attribute("href") or ""
        title = (await title_link.inner_text()).strip()

        # JobStreet URLs are like /job/{id} — relative or absolute.
        absolute_url = href if href.startswith("http") else f"{self.BASE_URL}{href}"
        m = _JOB_ID_RE.search(absolute_url)
        external_id = m.group(1) if m else absolute_url

        company = await self._text(card, '[data-automation="jobCompany"]')
        # Location isn't an <a> — 'jobLocation'/'jobCardLocation' carry e.g. "Central
        # Region". The old anchor-only selector never matched, defaulting to Singapore.
        location = await self._text(card, '[data-automation="jobLocation"], [data-automation="jobCardLocation"]')
        posted = await self._text(card, 'span[data-automation="jobListingDate"]')
        salary = await self._text(card, 'span[data-automation="jobSalary"]')

        return DiscoveredJob(
            platform=self.PLATFORM,
            external_id=external_id,
            url=absolute_url,
            title=title or "Untitled",
            company=company or "Unknown",
            location=location or "Singapore",
            posted_date=posted,
            description="",  # filled in by _fetch_description
            salary_min=None,
            salary_max=None,
        ) if external_id else None

    async def _fetch_description(self, browser: StealthBrowser, job_url: str) -> str:
        await browser.goto(job_url, wait_until="domcontentloaded")
        await HumanBehavior.random_delay(1500, 3000)
        el = await browser.page.query_selector('div[data-automation="jobAdDetails"]')
        if not el:
            return ""
        text = await el.inner_text()
        return text.strip()

    @staticmethod
    async def _text(node, selector: str) -> str:
        el = await node.query_selector(selector)
        if not el:
            return ""
        try:
            return (await el.inner_text()).strip()
        except Exception:
            return ""
