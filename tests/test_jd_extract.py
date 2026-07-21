"""URL → JD extraction routing (MCF special-case)."""

import asyncio
from unittest.mock import AsyncMock, patch

from src.jd_extract import _MCF_UUID, extract_jd_from_url


def test_mcf_uuid_extracted_from_url():
    url = "https://www.mycareersfuture.gov.sg/job/it/senior-ai-engineer-005932e6496522f43f0c38df096ed428"
    m = _MCF_UUID.search(url)
    assert m and m.group(1) == "005932e6496522f43f0c38df096ed428"


def test_mcf_url_uses_api_not_scrape():
    with patch("src.jd_extract._mcf_jd_from_api",
               new=AsyncMock(return_value="Senior AI Engineer at Acme\n\nBuild RAG systems.")):
        jd = asyncio.run(extract_jd_from_url("https://www.mycareersfuture.gov.sg/job/x-abc"))
    assert "Senior AI Engineer" in jd and "RAG" in jd
