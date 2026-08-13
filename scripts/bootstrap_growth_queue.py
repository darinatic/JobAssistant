"""Seed the gazetteer growth queue from a corpus of real job descriptions.

The queue only becomes a *ranked* review list once terms repeat across postings —
with two JDs in it every candidate sits at ``occurrences = 1`` and there is nothing
to prioritise. This fills it in one pass so curation can work on evidence.

It reuses the live pipeline rather than reimplementing it: ``JDParserAgent.parse``
already reconciles skills onto the gazetteer and records the leftovers, so parsing a
JD *is* the recording step. That means the queue this produces is exactly what normal
traffic would have produced, just faster.

Defaults to **MyCareersFuture only**: public JSON, inline descriptions, no browser,
and ToS-friendly. LinkedIn and JobStreet need Browserbase and carry ban risk, so they
are opt-in.

    .venv/Scripts/python.exe -m scripts.bootstrap_growth_queue --max-jobs 100
    .venv/Scripts/python.exe -m scripts.bootstrap_growth_queue --dry-run
"""

from __future__ import annotations

import argparse
import asyncio

from src.agents.jd_parser import JDParserAgent
from src.growth import fetch_candidates
from src.matching.gazetteer import canonicalize
from src.search import search_jobs
from src.utils.config import settings

# Broad enough to cover the roles the product targets without drifting off-domain.
_DEFAULT_KEYWORDS = [
    "AI Engineer",
    "Machine Learning Engineer",
    "Data Engineer",
    "Software Engineer",
]

_MIN_JD_CHARS = 200  # below this a "description" is a stub, not a posting


async def _collect_jds(keywords: list[str], per_keyword: int, platforms: list[str]) -> list[dict]:
    """Scrape postings and keep the ones with a real description, deduped by text."""
    seen: set[str] = set()
    out: list[dict] = []
    for kw in keywords:
        jobs = await search_jobs(
            keyword=kw, platforms=platforms, max_jobs=per_keyword, fetch_descriptions=True,
        )
        kept = 0
        for job in jobs:
            desc = (job.get("description") or "").strip()
            if len(desc) < _MIN_JD_CHARS:
                continue
            fingerprint = desc[:400]
            if fingerprint in seen:
                continue
            seen.add(fingerprint)
            out.append({"title": job.get("title", ""), "description": desc})
            kept += 1
        print(f"  {kw:32s} {len(jobs):3d} scraped -> {kept:3d} usable")
    return out


async def _parse_all(jds: list[dict], concurrency: int) -> int:
    """Parse each JD (which records its growth candidates). Returns the success count."""
    parser = JDParserAgent()
    sem = asyncio.Semaphore(concurrency)
    done = 0

    async def one(jd: dict) -> bool:
        nonlocal done
        async with sem:
            try:
                await parser.parse(jd["description"])
            except Exception as e:  # noqa: BLE001 — one bad posting must not stop the run
                print(f"  ! failed: {jd['title'][:50]} ({type(e).__name__}: {e})")
                return False
            done += 1
            if done % 10 == 0:
                print(f"  parsed {done}/{len(jds)}")
            return True

    results = await asyncio.gather(*(one(jd) for jd in jds))
    return sum(results)


async def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--keywords", nargs="*", default=_DEFAULT_KEYWORDS)
    ap.add_argument("--max-jobs", type=int, default=100, help="total postings to parse")
    ap.add_argument("--platforms", nargs="*", default=["mycareersfuture"])
    ap.add_argument("--concurrency", type=int, default=4)
    ap.add_argument("--dry-run", action="store_true",
                    help="scrape and report, but make no LLM calls and record nothing")
    args = ap.parse_args()

    if not settings.growth_persist_enabled:
        raise SystemExit(
            "SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY are not set — parsing would "
            "discard every candidate. Configure them first."
        )

    before = len(await fetch_candidates(limit=1000))
    per_keyword = max(1, args.max_jobs // max(1, len(args.keywords)))

    print(f"scraping up to {args.max_jobs} postings from {args.platforms}...")
    jds = await _collect_jds(args.keywords, per_keyword, args.platforms)
    print(f"\n{len(jds)} usable postings, queue currently holds {before} candidates")

    if args.dry_run:
        # Show what the gazetteer already covers, without spending a single token.
        unknown = {
            w for jd in jds for w in jd["title"].split()
            if len(w) > 3 and canonicalize(w) is None
        }
        print(f"dry run — no LLM calls made. {len(unknown)} unrecognised title words seen.")
        return

    print(f"\nparsing (concurrency {args.concurrency}); each JD is one Haiku call...")
    ok = await _parse_all(jds, args.concurrency)

    after = await fetch_candidates(limit=1000)
    print(f"\nparsed {ok}/{len(jds)} postings")
    print(f"queue: {before} -> {len(after)} candidates (+{len(after) - before})")
    repeated = [c for c in after if c["occurrences"] > 1]
    print(f"seen more than once: {len(repeated)}")
    for c in after[:15]:
        print(f"  {c['occurrences']:3d}x  {c['skill']}")
    print("\nnext: .venv/Scripts/python.exe -m scripts.curate_gazetteer propose")


if __name__ == "__main__":
    asyncio.run(main())
