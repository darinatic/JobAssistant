"""MyCareersFuture scraper.

MCF (Singapore Government job board) exposes an unauthenticated JSON API at
api.mycareersfuture.gov.sg/v2/jobs/. Full job descriptions live in the search
response — no detail fetch required.
"""

from __future__ import annotations

import asyncio
import datetime
import re
from collections.abc import AsyncIterator

import httpx

from src.scrapers.base import DiscoveredJob, JobScraper, SearchParams
from src.scrapers.filters import McfFilters
from src.scrapers.parsing import normalize_experience

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

    def _build_query(self, params: SearchParams, offset: int, page_limit: int) -> dict:
        """The MCF query for one page.

        `categories`, `employmentTypes` and `salary` are real server-side filters
        (measured 2026-08-14: salary=8000 cut a 12,838-result search to 3,253).
        Note MCF rejects a NUMERIC category id with HTTP 400 — it wants the name.
        """
        position_levels: list[str] = []
        for lvl in params.experience_levels:
            position_levels.extend(_POSITION_LEVELS.get(lvl, []))
        position_levels = list(dict.fromkeys(position_levels))  # dedupe, keep order

        query: dict = {
            "search": params.keyword,
            "limit": page_limit,
            "offset": offset,
            "sortBy": "new_posting_date",  # newest first (needed for the date cutoff)
        }
        if position_levels:
            query["positionLevels"] = position_levels  # httpx repeats list params
        if params.min_salary:
            query["salary"] = params.min_salary

        extras = McfFilters(**(params.platform_filters.get(self.PLATFORM) or {}))
        if extras.categories:
            query["categories"] = extras.categories
        if extras.employment_types:
            query["employmentTypes"] = extras.employment_types
        if extras.schemes:
            query["schemes"] = extras.schemes
        return query

    async def search(self, params: SearchParams) -> AsyncIterator[DiscoveredJob]:
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
                query = self._build_query(params, offset, page_limit)
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
        salary_min = salary.get("minimum")
        salary_max = salary.get("maximum")
        salary_period = self._salary_period(salary)
        salary_raw = self._salary_raw(salary_min, salary_max, salary_period)

        levels = self._position_levels(job)
        experience_raw = ", ".join(levels) or None
        # Normalize on the primary (first) level — the joined string won't match
        # the single-label table.
        experience_level = normalize_experience(levels[0], self.PLATFORM) if levels else None

        return DiscoveredJob(
            platform=self.PLATFORM,
            external_id=uuid,
            url=url,
            title=job.get("title") or "Untitled",
            company=company,
            location=location,
            description=_strip_html(job.get("description") or ""),
            posted_date=metadata.get("createdAt") or "",
            salary_min=salary_min,
            salary_max=salary_max,
            salary_period=salary_period,
            salary_raw=salary_raw,
            experience_raw=experience_raw,
            experience_level=experience_level,
        )

    @staticmethod
    def _salary_period(salary: dict) -> str | None:
        # salary.type.salaryType is "Monthly" / "Annually" (verified live).
        raw = ((salary.get("type") or {}).get("salaryType") or "").strip().lower()
        if raw.startswith("month"):
            return "monthly"
        if raw.startswith(("annual", "year")):
            return "annual"
        return None

    @staticmethod
    def _salary_raw(lo: int | None, hi: int | None, period: str | None) -> str | None:
        if lo is None and hi is None:
            return None
        suffix = {"monthly": "/mo", "annual": "/yr"}.get(period or "", "")
        if lo is not None and hi is not None:
            return f"${lo:,} - ${hi:,}{suffix}"
        val = lo if lo is not None else hi
        return f"${val:,}{suffix}"

    @staticmethod
    def _position_levels(job: dict) -> list[str]:
        levels = job.get("positionLevels") or []
        return [
            (lvl.get("position") or "").strip()
            for lvl in levels
            if isinstance(lvl, dict) and (lvl.get("position") or "").strip()
        ]
