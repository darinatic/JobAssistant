"""Common scraper interface."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import AsyncIterator, Protocol


@dataclass
class SearchParams:
    keyword: str
    location: str = "Singapore"
    # past_24_hours | past_week | past_month | any
    date_posted: str = "past_week"
    # entry_level | associate | mid_senior | director | executive
    experience_levels: list[str] = field(default_factory=list)
    # on_site | remote | hybrid
    remote_options: list[str] = field(default_factory=list)
    max_jobs: int = 25
    # When False, scrapers that need a separate detail fetch (LinkedIn, JobStreet)
    # return cards WITHOUT descriptions — the client fetches them on demand when a
    # job is opened. Keeps search fast and avoids tripping LinkedIn's burst wall.
    # MCF ignores this (descriptions are inline in its search response).
    fetch_descriptions: bool = True


@dataclass
class DiscoveredJob:
    platform: str          # 'linkedin' | 'jobstreet' | 'mycareersfuture' | ...
    external_id: str       # platform-native id (LinkedIn job_id, MCF uuid, JobStreet slug-id)
    url: str
    title: str
    company: str
    location: str
    description: str = ""
    posted_date: str = ""  # ISO-ish or human-readable, scraper-specific
    salary_min: int | None = None
    salary_max: int | None = None


class JobScraper(Protocol):
    PLATFORM: str

    def search(self, params: SearchParams) -> AsyncIterator[DiscoveredJob]:
        """Yield DiscoveredJob instances up to params.max_jobs."""
        ...
