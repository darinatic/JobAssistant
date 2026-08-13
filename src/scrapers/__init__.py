"""Job scrapers — one module per platform, all conform to JobScraper."""

from src.scrapers.ats import AtsScraper
from src.scrapers.base import DiscoveredJob, JobScraper, SearchParams
from src.scrapers.careersgov import CareersGovScraper
from src.scrapers.jobstreet import JobStreetScraper
from src.scrapers.linkedin import LinkedInGuestScraper
from src.scrapers.mycareersfuture import MyCareersFutureScraper

__all__ = [
    "DiscoveredJob",
    "JobScraper",
    "SearchParams",
    "MyCareersFutureScraper",
    "CareersGovScraper",
    "AtsScraper",
    "LinkedInGuestScraper",
    "JobStreetScraper",
]


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
    if p in ("ats", "companyboards", "greenhouse", "lever", "ashby"):
        return AtsScraper()
    raise ValueError(f"Unknown platform: {platform}")
