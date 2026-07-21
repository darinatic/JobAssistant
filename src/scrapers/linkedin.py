"""LinkedIn guest scraper.

Uses the public guest endpoints — no login required. The search endpoint
returns an HTML fragment of <li> job cards; the detail endpoint returns the
full job posting HTML. Both are issued by LinkedIn's own JS for logged-out
visitors, so requests with a normal browser UA work.

Rate behaviour: soft-limit kicks in around 5-10 quick requests from one IP.
We sleep 3-8s between page fetches. Beyond ~50-100 jobs in a burst, expect
empty responses or a login wall.
"""

from __future__ import annotations

import asyncio
import random
import re
import urllib.parse
from typing import AsyncIterator

import httpx
from bs4 import BeautifulSoup

from src.scrapers.base import DiscoveredJob, JobScraper, SearchParams


SEARCH_URL = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
DETAIL_URL = "https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{job_id}"

# Singapore geoId — LinkedIn's stable identifier for the country.
GEO_ID_SINGAPORE = "102454443"

# LinkedIn's f_TPR (Time Posted Range) values, seconds.
DATE_POSTED_MAP = {
    "past_24_hours": "r86400",
    "past_week": "r604800",
    "past_month": "r2592000",
    "any": "",
}

EXPERIENCE_MAP = {
    "internship": "1",
    "entry_level": "2",
    "associate": "3",
    "mid_senior": "4",
    "director": "5",
    "executive": "6",
}

REMOTE_MAP = {"on_site": "1", "remote": "2", "hybrid": "3"}

_DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-SG,en;q=0.9",
    "Cache-Control": "no-cache",
}

_JOB_ID_RE = re.compile(r"-(\d+)(?:\?|$)")


class LinkedInGuestScraper(JobScraper):
    PLATFORM = "linkedin"

    async def search(self, params: SearchParams) -> AsyncIterator[DiscoveredJob]:
        query = self._build_query(params)

        async with httpx.AsyncClient(
            timeout=30.0,
            headers=_DEFAULT_HEADERS,
            follow_redirects=True,
        ) as client:
            start = 0
            yielded = 0

            while yielded < params.max_jobs:
                resp = await client.get(SEARCH_URL, params={**query, "start": start})
                if resp.status_code in (429, 403):
                    # Hit the soft wall.
                    break
                resp.raise_for_status()

                soup = BeautifulSoup(resp.text, "html.parser")
                cards = soup.find_all("li")
                if not cards:
                    break

                for card in cards:
                    if yielded >= params.max_jobs:
                        break
                    parsed = self._parse_card(card)
                    if parsed is None:
                        continue
                    # Fetch full description from the detail endpoint only when asked.
                    # Bursting the detail endpoint is what trips LinkedIn's soft-wall,
                    # so search defers this to an on-demand fetch (see fetch_one).
                    if params.fetch_descriptions:
                        parsed.description = await self._fetch_description(
                            client, parsed.external_id
                        )
                    yield parsed
                    yielded += 1

                start += len(cards)
                # Polite delay — LinkedIn throttles fast loops aggressively.
                await asyncio.sleep(random.uniform(3.0, 8.0))

    def _build_query(self, params: SearchParams) -> dict[str, str]:
        q: dict[str, str] = {
            "keywords": params.keyword,
            "location": params.location,
            "geoId": GEO_ID_SINGAPORE,
        }
        tpr = DATE_POSTED_MAP.get(params.date_posted, "")
        if tpr:
            q["f_TPR"] = tpr
        if params.experience_levels:
            vals = [EXPERIENCE_MAP[e] for e in params.experience_levels if e in EXPERIENCE_MAP]
            if vals:
                q["f_E"] = ",".join(vals)
        if params.remote_options:
            vals = [REMOTE_MAP[r] for r in params.remote_options if r in REMOTE_MAP]
            if vals:
                q["f_WT"] = ",".join(vals)
        return q

    def _parse_card(self, card) -> DiscoveredJob | None:
        link = card.select_one("a.base-card__full-link") or card.select_one("a[href*='/jobs/view/']")
        if not link or not link.get("href"):
            return None

        href = link["href"].split("?")[0]
        job_id = self._extract_job_id(href, card)
        if not job_id:
            return None

        title_el = card.select_one("h3.base-search-card__title") or card.select_one("h3")
        company_el = card.select_one("h4.base-search-card__subtitle a") or card.select_one("h4 a") or card.select_one("h4")
        location_el = card.select_one("span.job-search-card__location") or card.select_one(".job-search-card__location")
        posted_el = card.select_one("time")

        return DiscoveredJob(
            platform=self.PLATFORM,
            external_id=job_id,
            url=f"https://www.linkedin.com/jobs/view/{job_id}/",
            title=(title_el.get_text(strip=True) if title_el else "Untitled"),
            company=(company_el.get_text(strip=True) if company_el else "Unknown"),
            location=(location_el.get_text(strip=True) if location_el else ""),
            posted_date=(posted_el.get("datetime") or posted_el.get_text(strip=True)) if posted_el else "",
        )

    def _extract_job_id(self, href: str, card) -> str | None:
        # Prefer URN attribute when present — survives URL slug changes.
        urn = card.get("data-entity-urn") if hasattr(card, "get") else None
        if urn and "jobPosting:" in urn:
            return urn.split(":")[-1]

        m = _JOB_ID_RE.search(href)
        if m:
            return m.group(1)

        m = re.search(r"/jobs/view/(\d+)", href)
        if m:
            return m.group(1)

        return None

    @classmethod
    async def fetch_one(cls, external_id: str) -> str:
        """On-demand single-job description fetch (used when a job is opened)."""
        self = cls()
        async with httpx.AsyncClient(
            timeout=30.0, headers=_DEFAULT_HEADERS, follow_redirects=True
        ) as client:
            return await self._fetch_description(client, external_id)

    async def _fetch_description(self, client: httpx.AsyncClient, job_id: str) -> str:
        try:
            resp = await client.get(DETAIL_URL.format(job_id=urllib.parse.quote(job_id)))
            if resp.status_code != 200:
                return ""
            soup = BeautifulSoup(resp.text, "html.parser")
            desc = soup.select_one("div.show-more-less-html__markup") or soup.select_one(
                "div.description__text"
            )
            return desc.get_text("\n", strip=True) if desc else ""
        except Exception:
            return ""
