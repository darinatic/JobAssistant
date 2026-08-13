"""ATS-native job boards (Greenhouse / Lever / Ashby) — company career pages.

Why this source is worth having: roles appear on a company's own ATS **before** the
aggregators index them, the payloads are first-party JSON rather than scraped HTML,
and none of these APIs bot-wall. It is the highest-quality feed in the pool.

The cost is a **registry**: these APIs are per-company, so somebody has to know which
companies to ask and under what slug. :data:`BOARDS` is that list, verified live —
adding a company is a one-line data change, not code.

Per-ATS quirks that shape the code:

* **Greenhouse** only returns bodies with ``?content=true``, which is enormous (9 MB
  vs 0.7 MB for one large board), so listings are fetched lean and bodies are pulled
  per job from ``/jobs/{id}`` only when asked for. Its ``content`` is also
  HTML-entity-escaped, so it needs unescaping *before* tag-stripping.
* **Lever** and **Ashby** return bodies inline, so there is nothing extra to fetch.
* Only Lever and Ashby state remote/onsite. None of the three states seniority or
  salary reliably, so those stay ``None`` rather than being guessed from the title.
"""

from __future__ import annotations

import asyncio
import contextlib
import datetime
import html as html_lib
import logging
import re
from collections.abc import AsyncIterator
from dataclasses import dataclass

import httpx
from bs4 import BeautifulSoup

from src.scrapers.base import DiscoveredJob, JobScraper, SearchParams
from src.scrapers.careersgov import term_matches

log = logging.getLogger(__name__)

_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")
_WS_RE = re.compile(r"\s+")

GREENHOUSE, LEVER, ASHBY = "greenhouse", "lever", "ashby"


@dataclass(frozen=True)
class Board:
    """One company's public board on one ATS."""

    ats: str
    slug: str
    company: str


# Verified live 2026-08-13 by querying each API and counting Singapore postings.
# Ordered by SG volume. Growing this list is the main way to widen coverage.
BOARDS: tuple[Board, ...] = (
    Board(ASHBY, "airwallex", "Airwallex"),
    Board(GREENHOUSE, "stripe", "Stripe"),
    Board(GREENHOUSE, "databricks", "Databricks"),
    Board(ASHBY, "openai", "OpenAI"),
    Board(GREENHOUSE, "temus", "Temus"),
    Board(GREENHOUSE, "datadog", "Datadog"),
    Board(LEVER, "patsnap", "PatSnap"),
    Board(LEVER, "ninjavan", "Ninja Van"),
    Board(GREENHOUSE, "mongodb", "MongoDB"),
    Board(GREENHOUSE, "thunes", "Thunes"),
    Board(GREENHOUSE, "xendit", "Xendit"),
    Board(GREENHOUSE, "trustbank", "Trust Bank"),
    Board(ASHBY, "snowflake", "Snowflake"),
    Board(GREENHOUSE, "figma", "Figma"),
    Board(LEVER, "nium", "Nium"),
    Board(GREENHOUSE, "anthropic", "Anthropic"),
    Board(GREENHOUSE, "gitlab", "GitLab"),
    Board(GREENHOUSE, "elastic", "Elastic"),
    Board(GREENHOUSE, "airbnb", "Airbnb"),
    Board(GREENHOUSE, "robinhood", "Robinhood"),
)

_LIST_URL = {
    GREENHOUSE: "https://boards-api.greenhouse.io/v1/boards/{slug}/jobs",
    LEVER: "https://api.lever.co/v0/postings/{slug}?mode=json",
    ASHBY: "https://api.ashbyhq.com/posting-api/job-board/{slug}",
}
_GH_JOB_URL = "https://boards-api.greenhouse.io/v1/boards/{slug}/jobs/{job_id}"

_DATE_DAYS = {"past_24_hours": 1, "past_week": 7, "past_month": 30}
# Lever/Ashby workplace vocabularies -> our remote_options values.
_WORKPLACE = {"onsite": "on_site", "on_site": "on_site", "remote": "remote", "hybrid": "hybrid"}


def html_to_text(raw: str) -> str:
    """HTML (possibly entity-escaped) → plain text.

    Greenhouse double-encodes: its ``content`` arrives as ``&lt;p&gt;``, so stripping
    tags before unescaping would leave the markup as literal visible text.
    """
    if not raw:
        return ""
    unescaped = html_lib.unescape(raw)
    text = BeautifulSoup(unescaped, "html.parser").get_text(" ", strip=True)
    return _WS_RE.sub(" ", text).strip()


def _iso_date(value) -> str:
    """ISO-8601 string or epoch-millis → YYYY-MM-DD ('' when absent/unparseable)."""
    if not value:
        return ""
    if isinstance(value, (int, float)):
        with contextlib.suppress(ValueError, OSError, OverflowError):
            return datetime.datetime.fromtimestamp(
                value / 1000, datetime.UTC
            ).date().isoformat()
        return ""
    with contextlib.suppress(ValueError, TypeError):
        return datetime.datetime.fromisoformat(str(value).replace("Z", "+00:00")).date().isoformat()
    return ""


@dataclass
class _Posting:
    """One ATS posting, normalized across the three vendors before filtering."""

    external_id: str
    title: str
    company: str
    location: str
    url: str
    posted_date: str = ""
    description: str = ""
    workplace: str | None = None   # our remote_options vocabulary, when stated
    context: str = ""              # department/team, searched alongside the title
    gh_slug: str | None = None     # set when a Greenhouse body must be fetched later


def _from_greenhouse(raw: dict, board: Board) -> _Posting:
    location = (raw.get("location") or {}).get("name", "")
    departments = ", ".join(d.get("name", "") for d in (raw.get("departments") or []))
    return _Posting(
        external_id=str(raw.get("id", "")),
        title=raw.get("title", ""),
        company=raw.get("company_name") or board.company,
        location=location,
        url=raw.get("absolute_url", ""),
        posted_date=_iso_date(raw.get("first_published") or raw.get("updated_at")),
        description=html_to_text(raw.get("content", "")),
        context=departments,
        gh_slug=board.slug,
    )


def _from_lever(raw: dict, board: Board) -> _Posting:
    cats = raw.get("categories") or {}
    body = " ".join(filter(None, [
        raw.get("descriptionPlain") or html_to_text(raw.get("description", "")),
        # Lever keeps responsibilities/requirements in `lists`, outside `description`.
        " ".join(html_to_text(item.get("content", "")) for item in (raw.get("lists") or [])),
    ]))
    return _Posting(
        external_id=str(raw.get("id", "")),
        title=raw.get("text", ""),
        company=board.company,
        location=cats.get("location", ""),
        url=raw.get("hostedUrl", ""),
        posted_date=_iso_date(raw.get("createdAt")),
        description=_WS_RE.sub(" ", body).strip(),
        workplace=_WORKPLACE.get(str(raw.get("workplaceType", "")).lower()),
        context=" ".join(filter(None, [cats.get("department", ""), cats.get("team", "")])),
    )


def _from_ashby(raw: dict, board: Board) -> _Posting:
    workplace = _WORKPLACE.get(str(raw.get("workplaceType", "")).lower())
    if raw.get("isRemote"):
        workplace = "remote"
    return _Posting(
        external_id=str(raw.get("id", "")),
        title=raw.get("title", ""),
        company=board.company,
        location=raw.get("location", ""),
        url=raw.get("jobUrl", ""),
        posted_date=_iso_date(raw.get("publishedAt")),
        description=html_to_text(raw.get("descriptionHtml", "")),
        workplace=workplace,
        context=" ".join(filter(None, [raw.get("department", ""), raw.get("team", "")])),
    )


_NORMALIZE = {GREENHOUSE: _from_greenhouse, LEVER: _from_lever, ASHBY: _from_ashby}


def normalize(raw: dict, board: Board) -> _Posting:
    return _NORMALIZE[board.ats](raw, board)


def _matches(posting: _Posting, params: SearchParams) -> bool:
    if params.location and params.location.lower() not in posting.location.lower():
        return False
    if params.keyword.strip():
        haystack = f"{posting.title} {posting.company} {posting.context}".lower()
        # Whole-word, not substring: "AI" must not fire inside "M-ai-ntenance".
        if not all(term_matches(haystack, t) for t in params.keyword.lower().split()):
            return False
    if params.remote_options and posting.workplace:
        # Unstated workplace is never excluded — Greenhouse simply doesn't say.
        if posting.workplace not in params.remote_options:
            return False
    days = _DATE_DAYS.get(params.date_posted)
    if days and posting.posted_date:
        cutoff = datetime.date.today() - datetime.timedelta(days=days)
        with contextlib.suppress(ValueError):
            if datetime.date.fromisoformat(posting.posted_date) < cutoff:
                return False
    return True


class AtsScraper(JobScraper):
    """Fan-out over every board in :data:`BOARDS`, concurrently."""

    PLATFORM = "ats"
    CONCURRENCY = 8

    def __init__(self, boards: tuple[Board, ...] = BOARDS) -> None:
        self.boards = boards

    async def search(self, params: SearchParams) -> AsyncIterator[DiscoveredJob]:
        async with httpx.AsyncClient(
            timeout=45.0, headers={"User-Agent": _UA}, follow_redirects=True
        ) as client:
            sem = asyncio.Semaphore(self.CONCURRENCY)

            async def load(board: Board) -> list[_Posting]:
                async with sem:
                    return await self._board_postings(client, board)

            results = await asyncio.gather(
                *(load(b) for b in self.boards), return_exceptions=True
            )

            selected: list[_Posting] = []
            for board, result in zip(self.boards, results, strict=True):
                if isinstance(result, BaseException):
                    log.warning("ATS board %s/%s failed: %s", board.ats, board.slug, result)
                    continue
                selected.extend(p for p in result if _matches(p, params))

            # Newest first, so a small max_jobs returns the freshest roles.
            selected.sort(key=lambda p: p.posted_date, reverse=True)
            selected = selected[: params.max_jobs]

            if params.fetch_descriptions:
                await self._fill_greenhouse_bodies(client, selected)

            for posting in selected:
                yield self._to_discovered(posting)

    async def _board_postings(self, client: httpx.AsyncClient, board: Board) -> list[_Posting]:
        resp = await client.get(_LIST_URL[board.ats].format(slug=board.slug))
        resp.raise_for_status()
        payload = resp.json()
        raw_jobs = payload.get("jobs", payload) if isinstance(payload, dict) else payload
        if not isinstance(raw_jobs, list):
            return []
        return [normalize(raw, board) for raw in raw_jobs if isinstance(raw, dict)]

    async def _fill_greenhouse_bodies(
        self, client: httpx.AsyncClient, postings: list[_Posting]
    ) -> None:
        """Greenhouse listings carry no body; fetch it per selected job.

        Deliberately not `?content=true` on the listing: that returns ~9 MB for a
        large board, most of which is discarded by the location filter.
        """
        need = [p for p in postings if p.gh_slug and not p.description]
        if not need:
            return
        sem = asyncio.Semaphore(self.CONCURRENCY)

        async def one(posting: _Posting) -> None:
            async with sem:
                try:
                    resp = await client.get(
                        _GH_JOB_URL.format(slug=posting.gh_slug, job_id=posting.external_id)
                    )
                    resp.raise_for_status()
                    posting.description = html_to_text(resp.json().get("content", ""))
                except Exception as e:  # noqa: BLE001 — a card without a body still ranks
                    log.debug("Greenhouse body fetch failed (%s): %s", posting.external_id, e)

        await asyncio.gather(*(one(p) for p in need))

    def _to_discovered(self, posting: _Posting) -> DiscoveredJob:
        return DiscoveredJob(
            platform=self.PLATFORM,
            external_id=posting.external_id,
            url=posting.url,
            title=posting.title,
            company=posting.company,
            location=posting.location,
            description=posting.description,
            posted_date=posting.posted_date,
            # None of the three boards states salary or seniority reliably, and the
            # matcher would rather have nothing than a guess from the job title.
        )

    @staticmethod
    async def fetch_one(url: str) -> str:
        """On-demand body for a single posting (the drawer's lazy fetch).

        Lever and Ashby bodies normally arrive inline with the card, but a posting
        with an empty body — or any card that reaches the drawer without one — still
        has to be recoverable, so all three vendors are handled here rather than
        Greenhouse alone.
        """
        async with httpx.AsyncClient(
            timeout=30.0, headers={"User-Agent": _UA}, follow_redirects=True
        ) as client:
            lever = re.search(r"jobs\.lever\.co/([^/]+)/([0-9a-f-]{16,})", url)
            if lever:
                slug, job_id = lever.groups()
                with contextlib.suppress(Exception):
                    resp = await client.get(
                        f"https://api.lever.co/v0/postings/{slug}/{job_id}?mode=json"
                    )
                    if resp.status_code == 200:
                        return _from_lever(resp.json(), Board(LEVER, slug, slug)).description
                return ""

            ashby = re.search(r"jobs\.ashbyhq\.com/([^/]+)/([0-9a-f-]{16,})", url)
            if ashby:
                slug, job_id = ashby.groups()
                # Ashby has no per-job endpoint; pull the board and pick the posting.
                with contextlib.suppress(Exception):
                    resp = await client.get(_LIST_URL[ASHBY].format(slug=slug))
                    if resp.status_code == 200:
                        payload = resp.json()
                        jobs = payload.get("jobs", payload) if isinstance(payload, dict) else payload
                        for raw in jobs or []:
                            if str(raw.get("id")) == job_id:
                                return _from_ashby(raw, Board(ASHBY, slug, slug)).description
                return ""

            match = re.search(r"gh_jid=(\d+)", url) or re.search(r"/jobs/(\d+)", url)
            if not match:
                return ""
            job_id = match.group(1)
            for board in (b for b in BOARDS if b.ats == GREENHOUSE):
                with contextlib.suppress(httpx.HTTPError):
                    resp = await client.get(
                        _GH_JOB_URL.format(slug=board.slug, job_id=job_id)
                    )
                    if resp.status_code == 200:
                        return html_to_text(resp.json().get("content", ""))
        return ""
