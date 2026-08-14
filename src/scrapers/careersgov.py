"""Careers@Gov scraper (jobs.careers.gov.sg) — the Singapore public service board.

High-value because its coverage is genuinely unique: GovTech, HTX, DSTA, CSIT, IMDA,
A*STAR and the ministries barely surface on the commercial aggregators.

**The whole catalogue arrives in one request.** The site is a Next.js App Router app
that server-renders every open posting into its RSC flight payload and then filters
client-side, so a single GET of the landing page yields ~2,200 jobs. That makes this
the cheapest adapter in the pool: no pagination, no per-keyword request, no browser,
and nothing to rate-limit. Filtering therefore happens locally, here.

Cards carry no description, so ``fetch_descriptions`` triggers a per-job detail fetch
of ``/jobs/{source}/{id}`` (the URL shape published in the site's own sitemap.xml).
Descriptions are server-rendered HTML, so plain httpx + BeautifulSoup is enough.

``robots.txt`` allows ``/`` and disallows only ``/api/`` — this adapter deliberately
uses the public pages and never the API.
"""

from __future__ import annotations

import asyncio
import contextlib
import datetime
import json
import logging
import re
from collections.abc import AsyncIterator

import httpx
from bs4 import BeautifulSoup

from src.scrapers.base import DiscoveredJob, JobScraper, SearchParams
from src.scrapers.parsing import lowest_careersgov_band, normalize_experience

log = logging.getLogger(__name__)

_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")

# Next.js streams the RSC payload as a series of JS string literals. Parsing each
# literal with json.loads is the only correct way to unescape it — a blanket
# `unicode_escape` decode corrupts every non-ASCII character in a job title.
_FLIGHT_RE = re.compile(r'self\.__next_f\.push\(\[1,("(?:[^"\\]|\\.)*")\]\)', re.S)
# Deliberately shape-agnostic on the id. Postings sourced from the board's own HR
# system use a composite "17659145/005056a3-..." id, but the ~15% that are hosted on
# Greenhouse or Workable use a plain numeric one. Pinning the composite shape
# silently dropped every one of those; validation happens on the decoded object.
_JOB_START_RE = re.compile(r'\{"id":"[^"]+","name":"')

# Next.js encodes a missing value as the literal string "$undefined".
_UNDEFINED = "$undefined"

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")

# Our normalized buckets → the site's own experience vocabulary.
_EXPERIENCE = {
    "entry_level": {"0 - 1 year"},
    "associate": {"1 - 3 years"},
    "mid_senior": {"4 - 6 years", "7 - 9 years"},
    "director": {"> 10 years"},
    "executive": {"> 10 years"},
}
_DATE_DAYS = {"past_24_hours": 1, "past_week": 7, "past_month": 30}


def _clean(value: str | None) -> str:
    """Site value → display string, mapping Next.js's `$undefined` sentinel to ''."""
    if not value or value == _UNDEFINED:
        return ""
    return _WS_RE.sub(" ", value).strip()


def extract_jobs(html: str) -> list[dict]:
    """Pull the embedded job records out of a Careers@Gov page's RSC payload.

    Scans each flight chunk for objects starting with the composite id and decodes
    them with ``raw_decode``, so a change to the record's other fields (or their
    order) does not break extraction.
    """
    jobs: dict[str, dict] = {}
    decoder = json.JSONDecoder()
    for match in _FLIGHT_RE.finditer(html):
        try:
            chunk = json.loads(match.group(1))
        except json.JSONDecodeError:
            continue
        for start in (m.start() for m in _JOB_START_RE.finditer(chunk)):
            try:
                obj, _ = decoder.raw_decode(chunk, start)
            except json.JSONDecodeError:
                continue
            # `agency` is required too: it is what distinguishes a job record from
            # any other {"id","name"} object the payload happens to carry.
            if isinstance(obj, dict) and obj.get("name") and obj.get("id") and obj.get("agency"):
                jobs.setdefault(obj["id"], obj)  # dedupe: chunks can repeat records
    return list(jobs.values())


# Agencies are listed under their full legal names, but candidates search for the
# short ones. Without this, "govtech" matches nothing at all — the agency is
# "Government Technology Agency". Only aliases that are genuinely unambiguous.
_AGENCY_ALIASES = {
    "govtech": "Government Technology Agency",
    "htx": "Home Team Science and Technology Agency",
    "dsta": "Defence Science and Technology Agency",
    "csit": "Centre for Strategic Infocomm Technologies",
    "imda": "Info-communications Media Development Authority",
    "astar": "Agency for Science, Technology and Research",
    "a*star": "Agency for Science, Technology and Research",
    "csa": "Cyber Security Agency of Singapore",
    "mas": "Monetary Authority of Singapore",
    "hdb": "Housing and Development Board",
    "lta": "Land Transport Authority",
    "iras": "Inland Revenue Authority of Singapore",
    "cpf": "Central Provident Fund Board",
    "moe": "Ministry of Education",
    "mom": "Ministry of Manpower",
    "mindef": "MINDEF",
    "scdf": "Singapore Civil Defence Force",
    "spf": "Singapore Police Force",
    "hsa": "Health Sciences Authority",
    "nrf": "National Research Foundation",
    "pub": "PUB, The National Water Agency",
}


def term_matches(haystack: str, term: str) -> bool:
    """Whole-word match, so a short term can't fire inside a longer word.

    Plain substring matching made "AI" match "M**ai**ntenance" and
    "Sust**ai**nability", which quietly filled an "AI engineer" search with
    technicians. Word boundaries keep "AI-Augmented" and "AI/ML" matching, because a
    hyphen or slash is a boundary.
    """
    return re.search(rf"(?<![a-z0-9]){re.escape(term)}(?![a-z0-9])", haystack) is not None


def _matches_keyword(job: dict, keyword: str) -> bool:
    """Every whitespace-separated term must appear somewhere in the card.

    Searching title + agency + department (rather than title alone) is what makes a
    query like "data govtech" work, and department carries the site's own taxonomy
    (e.g. "InfoComm, Technology, New Media Communications"). Common agency acronyms
    are expanded first, since the board only ever lists full legal names.
    """
    if not keyword.strip():
        return True
    haystack = " ".join(
        _clean(job.get(k)) for k in ("name", "agency", "department", "employmentType")
    ).lower()
    for term in keyword.lower().split():
        expanded = _AGENCY_ALIASES.get(term)
        if expanded and expanded.lower() in haystack:
            continue
        if not term_matches(haystack, term):
            return False
    return True


def _coerce_levels(job: dict) -> list[str]:
    """The posting's stated experience bands, or [] when it states none.

    Next.js encodes a missing value as the literal string "$undefined", and it does
    so for the WHOLE field, not just its elements. Iterating that string yields
    characters, which used to make a posting look like it stated the bands
    {'$','u','n','d','e','f','i'} — never matching a real band, so an experience
    filter silently excluded it (33 live postings, mostly GovTech).
    """
    raw = job.get("experienceLevels")
    if not isinstance(raw, list):
        return []
    return [lv for lv in raw if isinstance(lv, str) and lv != _UNDEFINED]


def _matches_experience(job: dict, wanted: list[str]) -> bool:
    if not wanted:
        return True
    levels = set(_coerce_levels(job))
    if not levels:
        return True  # unstated — don't exclude on a field the posting never filled in
    allowed: set[str] = set()
    for bucket in wanted:
        allowed |= _EXPERIENCE.get(bucket, set())
    return bool(levels & allowed) if allowed else True


def _posted_date(job: dict) -> str:
    ts = job.get("activityTimestamp")
    if not isinstance(ts, (int, float)):
        return ""
    with contextlib.suppress(ValueError, OSError, OverflowError):
        return datetime.datetime.fromtimestamp(ts / 1000, datetime.UTC).date().isoformat()
    return ""


def _experience_raw(job: dict) -> str:
    return ", ".join(_coerce_levels(job))


class CareersGovScraper(JobScraper):
    PLATFORM = "careersgov"
    LISTING_URL = "https://jobs.careers.gov.sg/"
    JOB_URL = "https://jobs.careers.gov.sg/jobs/{source}/{job_id}"
    DETAIL_CONCURRENCY = 6

    @classmethod
    def job_url(cls, job: dict) -> str:
        source = _clean(job.get("jobSource")) or "hrp"
        return cls.JOB_URL.format(source=source, job_id=job.get("id", ""))

    async def search(self, params: SearchParams) -> AsyncIterator[DiscoveredJob]:
        async with httpx.AsyncClient(
            timeout=45.0, headers={"User-Agent": _UA}, follow_redirects=True
        ) as client:
            try:
                resp = await client.get(self.LISTING_URL)
                resp.raise_for_status()
            except httpx.HTTPError as e:
                log.warning("Careers@Gov listing fetch failed: %s", e)
                return

            catalogue = extract_jobs(resp.text)
            log.info("Careers@Gov: %d postings in the catalogue", len(catalogue))

            days = _DATE_DAYS.get(params.date_posted)
            cutoff_ms = None
            if days:
                cutoff = datetime.datetime.now(datetime.UTC) - datetime.timedelta(days=days)
                cutoff_ms = cutoff.timestamp() * 1000

            selected: list[dict] = []
            for job in catalogue:
                if job.get("isAvailable") is False:
                    continue
                if not _matches_keyword(job, params.keyword):
                    continue
                if not _matches_experience(job, params.experience_levels):
                    continue
                ts = job.get("activityTimestamp")
                if cutoff_ms and isinstance(ts, (int, float)) and ts < cutoff_ms:
                    continue
                selected.append(job)
                if len(selected) >= params.max_jobs:
                    break

            descriptions: dict[str, str] = {}
            if params.fetch_descriptions and selected:
                descriptions = await self._fetch_descriptions(client, selected)

            for job in selected:
                yield self._to_discovered(job, descriptions.get(job["id"], ""))

    def _to_discovered(self, job: dict, description: str) -> DiscoveredJob:
        raw_levels = _experience_raw(job)
        # A posting can list several bands; normalize on the lowest, which is the
        # least experience it will accept.
        lowest = lowest_careersgov_band(_coerce_levels(job))
        return DiscoveredJob(
            platform=self.PLATFORM,
            external_id=str(job.get("id", "")),
            url=self.job_url(job),
            title=_clean(job.get("name")),
            company=_clean(job.get("agency")),
            location="Singapore",  # the public service does not post overseas roles here
            description=description,
            posted_date=_posted_date(job),
            # Careers@Gov does not publish salary on the listing or the detail page.
            experience_raw=raw_levels or None,
            experience_level=normalize_experience(lowest, self.PLATFORM) if lowest else None,
        )

    async def _fetch_descriptions(
        self, client: httpx.AsyncClient, jobs: list[dict]
    ) -> dict[str, str]:
        """Fetch detail pages concurrently but politely. Failures degrade to a card."""
        sem = asyncio.Semaphore(self.DETAIL_CONCURRENCY)

        async def one(job: dict) -> tuple[str, str]:
            async with sem:
                try:
                    resp = await client.get(self.job_url(job))
                    resp.raise_for_status()
                    return job["id"], parse_description(resp.text)
                except Exception as e:  # noqa: BLE001 — a card without a body still ranks
                    log.debug("Careers@Gov detail fetch failed (%s): %s", job.get("id"), e)
                    return job["id"], ""

        return dict(await asyncio.gather(*(one(j) for j in jobs)))

    @staticmethod
    async def fetch_one(url: str) -> str:
        """On-demand description for a single posting (the drawer's lazy fetch)."""
        async with httpx.AsyncClient(
            timeout=30.0, headers={"User-Agent": _UA}, follow_redirects=True
        ) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            return parse_description(resp.text)


def parse_description(html: str) -> str:
    """Extract the posting body from a Careers@Gov detail page.

    The body is a series of ``<article>`` blocks labelled by the preceding ``<h2>``
    ("What the role is", "What you will be working on", "What we are looking for").
    Keeping those headings makes the text read like a normal JD, which helps both
    skill extraction and the tailor.

    Do NOT fall back to ``<main>``: it opens with the standard Singapore government
    masthead ("Expand masthead to find out how to identify an official government
    website..."), which would prepend ~250 characters of boilerplate to every single
    posting and pollute the JD given to the model.
    """
    soup = BeautifulSoup(html, "html.parser")
    parts: list[str] = []
    for article in soup.find_all("article"):
        body = article.get_text(" ", strip=True)
        if not body:
            continue
        heading = article.find_previous("h2")
        label = heading.get_text(" ", strip=True) if heading else ""
        parts.append(f"{label}: {body}" if label else body)

    if not parts:  # markup changed — take labelled sections rather than the page
        for heading in soup.find_all(["h2", "h3"]):
            sibling = heading.find_next_sibling()
            if sibling:
                body = sibling.get_text(" ", strip=True)
                if len(body) > 40:
                    parts.append(f"{heading.get_text(' ', strip=True)}: {body}")

    return _WS_RE.sub(" ", _TAG_RE.sub(" ", " ".join(parts))).strip()
