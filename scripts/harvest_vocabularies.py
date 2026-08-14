"""Regenerate src/scrapers/vocabularies.py from the live boards.

Run: .venv/Scripts/python.exe -m scripts.harvest_vocabularies

MCF categories and Careers@Gov agencies/departments change as boards add them, so
these are SNAPSHOTS with a refresh path, never authorities. Validation in
src/scrapers/filters.py lets an unrecognised value through with a warning.

JobStreet's ids and MCF's position levels are constants here rather than harvested:
they are board-assigned ids established by probing each value and reading the
canonical redirect, not values readable from a listing response.
"""

from __future__ import annotations

import asyncio
import collections
from pathlib import Path

import httpx

from src.scrapers.careersgov import _UA, extract_jobs

OUT = Path(__file__).resolve().parents[1] / "src" / "scrapers" / "vocabularies.py"
MCF_API = "https://api.mycareersfuture.gov.sg/v2/jobs/"
CG_LISTING = "https://jobs.careers.gov.sg/"

# Measured 2026-08-14 by probing each id and reading the canonical redirect
# (?worktype=242 -> /full-time). worktype 246/247 and workarrangement=4 are invalid.
JOBSTREET_WORK_TYPES = {
    "full_time": "242", "part_time": "243", "contract_temp": "244", "casual_vacation": "245",
}
JOBSTREET_WORK_ARRANGEMENTS = {"on_site": "1", "hybrid": "2", "remote": "3"}
JOBSTREET_SALARY_TYPES = ("monthly", "annual", "hourly")
MCF_POSITION_LEVELS = (
    "Fresh/entry level", "Non-executive", "Junior Executive", "Executive",
    "Senior Executive", "Professional", "Manager", "Middle Management", "Senior Management",
)
# Acronyms candidates type; the board lists only full legal names. Lives here rather
# than in careersgov.py so filters.py can use it without an import cycle.
AGENCY_ALIASES = {
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


async def harvest_mcf() -> tuple[list[str], list[str]]:
    cats: collections.Counter = collections.Counter()
    emps: collections.Counter = collections.Counter()
    async with httpx.AsyncClient(timeout=60.0) as c:
        for off in range(0, 600, 100):
            r = await c.get(MCF_API, params={
                "search": "", "limit": 100, "offset": off, "sortBy": "new_posting_date",
            })
            r.raise_for_status()
            for j in r.json().get("results", []):
                for x in j.get("categories") or []:
                    if x.get("category"):
                        cats[x["category"]] += 1
                for x in j.get("employmentTypes") or []:
                    if x.get("employmentType"):
                        emps[x["employmentType"]] += 1
            await asyncio.sleep(0.6)
    return sorted(cats), sorted(emps)


async def harvest_careersgov() -> tuple[list[str], list[str], list[str], list[str]]:
    async with httpx.AsyncClient(
        timeout=60.0, headers={"User-Agent": _UA}, follow_redirects=True
    ) as c:
        r = await c.get(CG_LISTING)
        r.raise_for_status()
    jobs = extract_jobs(r.text)
    agencies: collections.Counter = collections.Counter()
    depts: collections.Counter = collections.Counter()
    emps: collections.Counter = collections.Counter()
    bands: collections.Counter = collections.Counter()
    for j in jobs:
        for key, ctr in (("agency", agencies), ("department", depts), ("employmentType", emps)):
            v = j.get(key)
            if isinstance(v, str) and v and v != "$undefined":
                ctr[v] += 1
        raw = j.get("experienceLevels")
        if isinstance(raw, list):  # guard: some records carry the sentinel STRING
            for lv in raw:
                if isinstance(lv, str) and lv != "$undefined":
                    bands[lv] += 1
    print(f"  Careers@Gov catalogue: {len(jobs)} postings")
    return sorted(agencies), sorted(depts), sorted(emps), sorted(bands)


def _tup(name: str, values) -> str:
    body = "\n".join(f"    {v!r}," for v in values)
    return f"{name}: tuple[str, ...] = (\n{body}\n)\n\n"


def _dct(name: str, mapping: dict) -> str:
    body = "\n".join(f"    {k!r}: {v!r}," for k, v in mapping.items())
    return f"{name}: dict[str, str] = {{\n{body}\n}}\n\n"


def render(**kw) -> str:
    parts = [
        '"""Filter vocabularies harvested from the live boards.\n\n'
        "GENERATED by scripts/harvest_vocabularies.py — do not edit by hand.\n\n"
        "SNAPSHOTS, not authorities. Boards add agencies and categories, so\n"
        "src/scrapers/filters.py passes an unrecognised value through with a warning\n"
        "rather than rejecting it: a frozen enum would reject a genuinely new agency.\n"
        '"""\n\n',
    ]
    parts.append(_tup("MCF_CATEGORIES", kw["mcf_categories"]))
    parts.append(_tup("MCF_EMPLOYMENT_TYPES", kw["mcf_employment_types"]))
    parts.append(_tup("MCF_POSITION_LEVELS", MCF_POSITION_LEVELS))
    parts.append(_dct("JOBSTREET_WORK_TYPES", JOBSTREET_WORK_TYPES))
    parts.append(_dct("JOBSTREET_WORK_ARRANGEMENTS", JOBSTREET_WORK_ARRANGEMENTS))
    parts.append(_tup("JOBSTREET_SALARY_TYPES", JOBSTREET_SALARY_TYPES))
    parts.append(_tup("CAREERSGOV_AGENCIES", kw["cg_agencies"]))
    parts.append(_tup("CAREERSGOV_DEPARTMENTS", kw["cg_departments"]))
    parts.append(_tup("CAREERSGOV_EMPLOYMENT_TYPES", kw["cg_employment_types"]))
    parts.append(_tup("CAREERSGOV_EXPERIENCE_BANDS", kw["cg_bands"]))
    parts.append(_dct("CAREERSGOV_AGENCY_ALIASES", AGENCY_ALIASES))
    return "".join(parts)


async def main() -> None:
    print("Harvesting MyCareersFuture...")
    mcf_categories, mcf_employment_types = await harvest_mcf()
    print(f"  {len(mcf_categories)} categories, {len(mcf_employment_types)} employment types")
    print("Harvesting Careers@Gov...")
    cg_agencies, cg_departments, cg_employment_types, cg_bands = await harvest_careersgov()
    print(f"  {len(cg_agencies)} agencies, {len(cg_departments)} departments")
    OUT.write_text(render(
        mcf_categories=mcf_categories, mcf_employment_types=mcf_employment_types,
        cg_agencies=cg_agencies, cg_departments=cg_departments,
        cg_employment_types=cg_employment_types, cg_bands=cg_bands,
    ), encoding="utf-8")
    print(f"Wrote {OUT}")


if __name__ == "__main__":
    asyncio.run(main())
