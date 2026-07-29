"""Response-parsing tests for the scrapers — the code most likely to break silently
when a site changes markup. Fixtures mirror the real response shapes; no network."""

import asyncio

from bs4 import BeautifulSoup

from src.scrapers.jobstreet import JobStreetScraper
from src.scrapers.linkedin import LinkedInGuestScraper
from src.scrapers.mycareersfuture import MyCareersFutureScraper

# ---------- MyCareersFuture (JSON -> DiscoveredJob) --------------------------

_MCF_JOB = {
    "uuid": "abc-123",
    "title": "AI Engineer",
    "status": {"jobStatus": "Open"},
    "postedCompany": {"name": "Acme Pte Ltd"},
    "address": {"districts": [{"region": "Central"}]},
    "salary": {"minimum": 5000, "maximum": 7000},
    "description": "<p>Build <b>RAG</b> pipelines</p>",
    "metadata": {
        "jobDetailsUrl": "https://www.mycareersfuture.gov.sg/job/abc-123",
        "createdAt": "2026-07-20T00:00:00Z",
        "newPostingDate": "2026-07-20",
    },
}


def test_mcf_parses_open_job():
    job = MyCareersFutureScraper()._from_mcf_job(_MCF_JOB)
    assert job is not None
    assert job.platform == "mycareersfuture"
    assert job.external_id == "abc-123"
    assert job.title == "AI Engineer"
    assert job.company == "Acme Pte Ltd"
    assert job.location == "Central"
    assert job.salary_min == 5000 and job.salary_max == 7000
    assert job.description == "Build RAG pipelines"   # HTML stripped
    assert job.url.endswith("/job/abc-123")


def test_mcf_skips_closed_job():
    closed = {**_MCF_JOB, "status": {"jobStatus": "Closed"}}
    assert MyCareersFutureScraper()._from_mcf_job(closed) is None


def test_mcf_skips_missing_uuid():
    assert MyCareersFutureScraper()._from_mcf_job({**_MCF_JOB, "uuid": None}) is None


def test_mcf_defaults_company_and_location():
    bare = {"uuid": "x", "title": "Dev", "status": {}, "metadata": {}}
    job = MyCareersFutureScraper()._from_mcf_job(bare)
    assert job is not None
    assert job.company == "Unknown" and job.location == "Singapore"


# ---------- LinkedIn (guest HTML card -> DiscoveredJob) ----------------------

_LI_CARD = """
<li>
  <a class="base-card__full-link" href="https://www.linkedin.com/jobs/view/ml-engineer-at-acme-3812345678?refId=x">link</a>
  <h3 class="base-search-card__title">ML Engineer</h3>
  <h4 class="base-search-card__subtitle"><a href="/company/acme">Acme Corp</a></h4>
  <span class="job-search-card__location">Singapore</span>
  <time datetime="2026-07-20">3 days ago</time>
</li>
"""


def _li(html: str):
    return BeautifulSoup(html, "html.parser").find("li")


def test_linkedin_parses_card():
    job = LinkedInGuestScraper()._parse_card(_li(_LI_CARD))
    assert job is not None
    assert job.platform == "linkedin"
    assert job.external_id == "3812345678"     # from the href slug
    assert job.title == "ML Engineer"
    assert job.company == "Acme Corp"
    assert job.location == "Singapore"
    assert "3812345678" in job.url


def test_linkedin_prefers_urn_id():
    card = """<li data-entity-urn="urn:li:jobPosting:9998887776">
      <a class="base-card__full-link" href="https://www.linkedin.com/jobs/view/x-123">t</a>
      <h3 class="base-search-card__title">T</h3></li>"""
    job = LinkedInGuestScraper()._parse_card(_li(card))
    assert job is not None
    assert job.external_id == "9998887776"     # URN wins over the href slug


def test_linkedin_none_without_link():
    assert LinkedInGuestScraper()._parse_card(_li("<li><span>no link</span></li>")) is None


# ---------- JobStreet (async Playwright card -> DiscoveredJob) ---------------


class _FakeEl:
    def __init__(self, text: str = "", href: str | None = None):
        self._text, self._href = text, href

    async def inner_text(self) -> str:
        return self._text

    async def get_attribute(self, name: str):
        return self._href if name == "href" else None


class _FakeCard:
    def __init__(self, mapping: dict):
        self._m = mapping

    async def query_selector(self, selector: str):
        return self._m.get(selector)


def test_jobstreet_parses_card():
    card = _FakeCard({
        'a[data-automation="jobTitle"]': _FakeEl("Data Scientist", href="/job/78901234"),
        '[data-automation="jobCompany"]': _FakeEl("Beta Ltd"),
        '[data-automation="jobLocation"], [data-automation="jobCardLocation"]': _FakeEl("Central Region"),
        'span[data-automation="jobListingDate"]': _FakeEl("2d ago"),
    })
    job = asyncio.run(JobStreetScraper()._parse_card(card))
    assert job is not None
    assert job.platform == "jobstreet"
    assert job.external_id == "78901234"
    assert job.title == "Data Scientist"
    assert job.company == "Beta Ltd"
    assert job.location == "Central Region"
    assert job.url.endswith("/job/78901234")


def test_jobstreet_none_without_title():
    assert asyncio.run(JobStreetScraper()._parse_card(_FakeCard({}))) is None
