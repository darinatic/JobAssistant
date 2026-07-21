"""MyCareersFuture scraper.

MCF (Singapore Government job board) exposes an unauthenticated JSON API at
api.mycareersfuture.gov.sg/v2/jobs/. Full job descriptions live in the search
response — no detail fetch required.
"""

from __future__ import annotations

import asyncio
import datetime
import re
from typing import AsyncIterator

import httpx

from src.scrapers.base import DiscoveredJob, JobScraper, SearchParams


_TAG_RE = re.compile(r"<[^>]+>")
_WHITESPACE_RE = re.compile(r"\s+")

# Our experience buckets → MCF's positionLevels vocabulary (query-param filter).
_POSITION_LEVELS = {
    "entry_level": ["Fresh/entry level", "Non-executive"],
    "associate": ["Junior Executive"],
    "mid_senior": ["Senior Executive", "Manager", "Professional"],
    "director": ["Middle Management", "Senior Management"],
    "executive": ["Senior Management"],
}
# date_posted → recency window in days (MCF has no date param; filtered client-side
# over the new_posting_date-sorted results).
_DATE_DAYS = {"past_24_hours": 1, "past_week": 7, "past_month": 30}


def _strip_html(html: str) -> str:
    text = _TAG_RE.sub(" ", html or "")
    return _WHITESPACE_RE.sub(" ", text).strip()


class MyCareersFutureScraper(JobScraper):
    PLATFORM = "mycareersfuture"
    BASE_URL = "https://api.mycareersfuture.gov.sg/v2/jobs/"
    PAGE_SIZE = 100  # max recommended by the unofficial API client

    async def search(self, params: SearchParams) -> AsyncIterator[DiscoveredJob]:
        position_levels: list[str] = []
        for lvl in params.experience_levels:
            position_levels.extend(_POSITION_LEVELS.get(lvl, []))
        position_levels = list(dict.fromkeys(position_levels))  # dedupe, keep order

        days = _DATE_DAYS.get(params.date_posted)
        cutoff = datetime.date.today() - datetime.timedelta(days=days) if days else None

        async with httpx.AsyncClient(timeout=30.0) as client:
            offset = 0
            yielded = 0

            while yielded < params.max_jobs:
                # Fetch a full, FIXED-size page — do NOT shrink toward
                # `max_jobs - yielded`. When results get filtered out (closed jobs),
                # a shrinking limit crawls ~1 job/request (1s sleep each), which can
                # stall the whole search for minutes. The inner loop caps output.
                page_limit = min(self.PAGE_SIZE, max(params.max_jobs, 30))
                query: dict = {
                    "search": params.keyword,
                    "limit": page_limit,
                    "offset": offset,
                    "sortBy": "new_posting_date",  # newest first (needed for the date cutoff)
                }
                if position_levels:
                    query["positionLevels"] = position_levels  # httpx repeats list params
                resp = await client.get(self.BASE_URL, params=query)
                resp.raise_for_status()
                data = resp.json()
                results = data.get("results") or []
                if not results:
                    break

                stop = False
                for job in results:
                    if yielded >= params.max_jobs:
                        break
                    # Date filter: results are newest-first, so the first job older
                    # than the cutoff means everything after is too — stop entirely.
                    if cutoff:
                        posted = self._posting_date(job)
                        if posted and posted < cutoff:
                            stop = True
                            break
                    discovered = self._from_mcf_job(job)
                    if discovered is None:
                        continue
                    yield discovered
                    yielded += 1

                if stop:
                    break
                offset += len(results)
                # Polite — MCF is a government endpoint with no documented limit.
                await asyncio.sleep(1.0)

    @staticmethod
    def _posting_date(job: dict) -> datetime.date | None:
        raw = (job.get("metadata") or {}).get("newPostingDate")
        try:
            return datetime.date.fromisoformat(raw[:10]) if raw else None
        except (ValueError, TypeError):
            return None

    def _from_mcf_job(self, job: dict) -> DiscoveredJob | None:
        status = (job.get("status") or {}).get("jobStatus")
        if status and status.lower() != "open":
            return None

        uuid = job.get("uuid")
        if not uuid:
            return None

        metadata = job.get("metadata") or {}
        url = metadata.get("jobDetailsUrl") or f"https://www.mycareersfuture.gov.sg/job/{uuid}"

        company = ((job.get("postedCompany") or {}).get("name")) or "Unknown"

        address = job.get("address") or {}
        location_parts: list[str] = []
        districts = address.get("districts") or []
        if districts:
            location_parts.extend(
                d.get("region") or d.get("location") for d in districts if isinstance(d, dict)
            )
        location = ", ".join(filter(None, location_parts)) or "Singapore"

        salary = job.get("salary") or {}
        return DiscoveredJob(
            platform=self.PLATFORM,
            external_id=uuid,
            url=url,
            title=job.get("title") or "Untitled",
            company=company,
            location=location,
            description=_strip_html(job.get("description") or ""),
            posted_date=metadata.get("createdAt") or "",
            salary_min=salary.get("minimum"),
            salary_max=salary.get("maximum"),
        )
