"""Extract a job description from an arbitrary URL (best-effort).

Fetch the page, strip boilerplate, then use one cheap Haiku call to isolate just
the job posting. Works on most company/ATS pages; JS-heavy or bot-walled sites
(some LinkedIn/Indeed pages) may return too little text — handled as a clear error.
"""

import logging
import re

import httpx
from bs4 import BeautifulSoup
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage

from src.utils.config import settings

log = logging.getLogger(__name__)

_MCF_UUID = re.compile(r"([0-9a-f]{32})", re.IGNORECASE)
_HTML_TAG = re.compile(r"<[^>]+>")


async def _mcf_jd_from_api(url: str) -> str | None:
    """MyCareersFuture is a JS SPA — scraping the page yields nothing. Its job
    URL ends in the UUID, so pull the full description from the public JSON API."""
    m = _MCF_UUID.search(url)
    if not m:
        return None
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.get(f"https://api.mycareersfuture.gov.sg/v2/jobs/{m.group(1)}")
            if resp.status_code != 200:
                return None
            job = resp.json()
    except Exception:
        return None
    desc = " ".join(_HTML_TAG.sub(" ", job.get("description") or "").split())
    if len(desc) < 40:
        return None
    title = job.get("title") or ""
    company = ((job.get("postedCompany") or {}).get("name")) or ""
    header = f"{title} at {company}".strip(" at")
    return f"{header}\n\n{desc}" if header else desc

_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/125.0 Safari/537.36")

_SYSTEM = (
    "You are given the raw text of a web page. Extract ONLY the job posting: the role "
    "title, responsibilities, requirements, and required/preferred skills. Drop navigation, "
    "ads, cookie/consent notices, related-jobs, and any unrelated content. Return the cleaned "
    "job description as plain text. If the page contains no job posting, return exactly NO_JD."
)


async def extract_jd_from_url(url: str) -> str:
    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    # MyCareersFuture (and other JS SPAs) can't be scraped as HTML — use its API.
    if "mycareersfuture" in url.lower():
        jd = await _mcf_jd_from_api(url)
        if jd:
            return jd

    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=20,
                                     headers={"User-Agent": _UA}) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            html = resp.text
    except Exception as e:
        raise ValueError(f"Couldn't fetch the URL ({type(e).__name__}).") from e

    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "header", "noscript", "svg", "form"]):
        tag.decompose()
    text = " ".join(soup.get_text(" ").split())
    if len(text) < 200:
        raise ValueError("That page had too little readable text — it may require JavaScript or block scraping. Paste the JD instead.")

    llm = ChatAnthropic(
        model=settings.anthropic_haiku_model,
        api_key=settings.anthropic_api_key.get_secret_value(),
        max_tokens=2000,
        temperature=0,
    )
    resp = await llm.ainvoke([SystemMessage(content=_SYSTEM), HumanMessage(content=text[:16000])])
    jd = (resp.content if hasattr(resp, "content") else str(resp)).strip()
    if not jd or jd.strip() == "NO_JD" or len(jd) < 40:
        raise ValueError("Couldn't find a job description on that page. Paste the JD instead.")
    return jd
