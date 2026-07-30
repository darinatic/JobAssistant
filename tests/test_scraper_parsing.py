"""Response-parsing tests for the scrapers — the code most likely to break silently
when a site changes markup. Fixtures mirror the real response shapes; no network."""

import asyncio

import pytest
from bs4 import BeautifulSoup

from src.scrapers.jobstreet import JobStreetScraper
from src.scrapers.linkedin import LinkedInGuestScraper
from src.scrapers.mycareersfuture import MyCareersFutureScraper
from src.scrapers.parsing import monthly_value, normalize_experience, parse_salary

# ---------- salary + experience helpers (parsing.py) ------------------------

@pytest.mark.parametrize("text, expected", [
    ("$5,000 - $7,000 per month", (5000, 7000, "monthly")),
    ("$3,500 – $4,500 per month", (3500, 4500, "monthly")),          # en-dash
    ("SGD 60,000-90,000 annually", (60000, 90000, "annual")),
    ("SGD 11,000.00/mo - SGD 13,000.00/mo", (11000, 13000, "monthly")),  # LinkedIn
    ("$5k - $7k", (5000, 7000, None)),
    ("Up to $8,000/mo", (None, 8000, "monthly")),
    ("From $5,000 monthly", (5000, None, "monthly")),
    ("$6,500 per year", (6500, None, "annual")),
    ("Salary match", (None, None, None)),
    ("Competitive", (None, None, None)),
    ("", (None, None, None)),
    (None, (None, None, None)),
    ("2 years experience", (None, None, None)),   # 2 -> below plausible floor
])
def test_parse_salary(text, expected):
    assert parse_salary(text) == expected


def test_monthly_value_normalizes_annual():
    assert monthly_value(120000, "annual") == 10000
    assert monthly_value(6000, "monthly") == 6000
    assert monthly_value(6000, None) == 6000      # unknown treated as monthly
    assert monthly_value(None, "annual") is None


@pytest.mark.parametrize("raw, platform, expected", [
    ("Non-executive", "mycareersfuture", "entry_level"),
    ("Fresh/entry level", "mycareersfuture", "entry_level"),
    ("Junior Executive", "mycareersfuture", "associate"),
    ("Senior Executive", "mycareersfuture", "mid_senior"),
    ("Middle Management", "mycareersfuture", "director"),
    ("Mid-Senior level", "linkedin", "mid_senior"),
    ("Entry level", "linkedin", "entry_level"),
    ("Director", "linkedin", "director"),
    ("Not Applicable", "linkedin", None),
    ("Internship", "linkedin", None),
    ("Whatever", "jobstreet", None),       # no table for jobstreet
    ("", "linkedin", None),
    (None, "mycareersfuture", None),
])
def test_normalize_experience(raw, platform, expected):
    assert normalize_experience(raw, platform) == expected

# ---------- MyCareersFuture (JSON -> DiscoveredJob) --------------------------

_MCF_JOB = {
    "uuid": "abc-123",
    "title": "AI Engineer",
    "status": {"jobStatus": "Open"},
    "postedCompany": {"name": "Acme Pte Ltd"},
    "address": {"districts": [{"region": "Central"}]},
    "salary": {"minimum": 5000, "maximum": 7000, "type": {"id": 4, "salaryType": "Monthly"}},
    "positionLevels": [{"id": 11, "position": "Senior Executive"}],
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


def test_mcf_parses_salary_and_experience():
    job = MyCareersFutureScraper()._from_mcf_job(_MCF_JOB)
    assert job is not None
    assert job.salary_period == "monthly"
    assert job.salary_raw == "$5,000 - $7,000/mo"
    assert job.experience_raw == "Senior Executive"
    assert job.experience_level == "mid_senior"


def test_mcf_annual_salary_period():
    annual = {**_MCF_JOB, "salary": {"minimum": 60000, "maximum": 90000,
                                     "type": {"salaryType": "Annually"}}}
    job = MyCareersFutureScraper()._from_mcf_job(annual)
    assert job is not None
    assert job.salary_period == "annual"
    assert job.salary_raw == "$60,000 - $90,000/yr"


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


_LI_DETAIL = """
<html><body>
  <div class="description__text">
    <div class="show-more-less-html__markup">Design and ship RAG systems.</div>
  </div>
  <div class="salary compensation__salary">SGD 11,000.00/mo - SGD 13,000.00/mo</div>
  <ul class="description__job-criteria-list">
    <li class="description__job-criteria-item">
      <h3 class="description__job-criteria-subheader">Seniority level</h3>
      <span class="description__job-criteria-text">Mid-Senior level</span>
    </li>
    <li class="description__job-criteria-item">
      <h3 class="description__job-criteria-subheader">Employment type</h3>
      <span class="description__job-criteria-text">Full-time</span>
    </li>
  </ul>
</body></html>
"""


def test_linkedin_parse_detail():
    detail = LinkedInGuestScraper()._parse_detail(_LI_DETAIL)
    assert "RAG systems" in detail.description
    assert detail.salary_min == 11000 and detail.salary_max == 13000
    assert detail.salary_period == "monthly"
    assert detail.experience_raw == "Mid-Senior level"
    assert detail.experience_level == "mid_senior"


def test_linkedin_parse_detail_missing_extras():
    detail = LinkedInGuestScraper()._parse_detail(
        '<div class="show-more-less-html__markup">Just a description.</div>'
    )
    assert detail.description == "Just a description."
    assert detail.salary_min is None and detail.salary_raw is None
    assert detail.experience_raw is None and detail.experience_level is None


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


def test_jobstreet_parses_salary_from_card():
    card = _FakeCard({
        'a[data-automation="jobTitle"]': _FakeEl("Data Scientist", href="/job/78901234"),
        '[data-automation="jobCompany"]': _FakeEl("Beta Ltd"),
        '[data-automation="jobLocation"], [data-automation="jobCardLocation"]': _FakeEl("Central Region"),
        'span[data-automation="jobListingDate"]': _FakeEl("2d ago"),
        '[data-automation="jobSalary"]': _FakeEl("$7,000 – $8,000 per month"),
    })
    job = asyncio.run(JobStreetScraper()._parse_card(card))
    assert job is not None
    assert job.salary_min == 7000 and job.salary_max == 8000
    assert job.salary_period == "monthly"
    assert job.salary_raw == "$7,000 – $8,000 per month"
    # JobStreet exposes no seniority field.
    assert job.experience_raw is None and job.experience_level is None


def test_jobstreet_no_salary_cell():
    card = _FakeCard({
        'a[data-automation="jobTitle"]': _FakeEl("Data Scientist", href="/job/78901234"),
    })
    job = asyncio.run(JobStreetScraper()._parse_card(card))
    assert job is not None
    assert job.salary_min is None and job.salary_raw is None


def test_jobstreet_none_without_title():
    assert asyncio.run(JobStreetScraper()._parse_card(_FakeCard({}))) is None


# ---------- Insights salary normalization -----------------------------------


def test_insights_salary_normalizes_annual_to_monthly():
    from src.insights import aggregate_jobs
    jobs = [
        {"title": "A", "description": "python", "salary_min": 5000, "salary_max": 6000,
         "salary_period": "monthly", "platform": "mycareersfuture"},
        {"title": "B", "description": "python", "salary_min": 84000, "salary_max": 120000,
         "salary_period": "annual", "platform": "linkedin"},
    ]
    out = aggregate_jobs(jobs)
    # Annual 120,000 -> 10,000/mo is the max; annual 84,000 -> 7,000/mo, so min is 5,000.
    assert out["salary"]["max"] == 10000
    assert out["salary"]["min"] == 5000
    assert out["salary"]["disclosed"] == 4
