"""Job scrapers — one module per platform, all conform to JobScraper."""

from src.scrapers.base import DiscoveredJob, JobScraper, SearchParams
from src.scrapers.capabilities import (
    ALL_CAPABILITIES,
    BoardCapabilities,
    Support,
    _attach_filter_models,
    capabilities_for,
)
from src.scrapers.careersgov import CareersGovScraper
from src.scrapers.jobstreet import JobStreetScraper
from src.scrapers.linkedin import LinkedInGuestScraper
from src.scrapers.mycareersfuture import MyCareersFutureScraper

__all__ = [
    "DiscoveredJob",
    "JobScraper",
    "SearchParams",
    "ALL_CAPABILITIES",
    "BoardCapabilities",
    "Support",
    "capabilities_for",
    "MyCareersFutureScraper",
    "CareersGovScraper",
    "LinkedInGuestScraper",
    "JobStreetScraper",
]


# Bind the native-filter models now that every adapter module is imported.
_attach_filter_models()


def build_scraper(platform: str) -> JobScraper:
    """Factory: platform name → scraper instance."""
    p = platform.lower().replace(" ", "").replace("-", "")
    if p in ("mcf", "mycareersfuture"):
        return MyCareersFutureScraper()
    if p == "linkedin":
        return LinkedInGuestScraper()
    if p == "jobstreet":
        return JobStreetScraper()
    if p in ("careersgov", "careers@gov", "careersatgov", "gov"):
        return CareersGovScraper()
    raise ValueError(f"Unknown platform: {platform}")
