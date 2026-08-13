"""Propose gazetteer additions from the growth queue, then apply what you approve.

Two phases, because the gazetteer's precision is what makes the deterministic matcher
worth trusting — nothing is ever written without a human in the loop:

    propose  ->  outputs/gazetteer_review.json   (you edit the verdicts)
    apply    ->  src/matching/gazetteer.py

`propose` runs a cheap deterministic pre-filter (soft skills, workplace phrases) and
sends only what survives to the model, which classifies each candidate as an **alias**
of an existing canonical, a **new canonical**, or a **reject**. This is a dev-time
workflow: the model never touches the request path, and its output is a suggestion,
not a decision.

    .venv/Scripts/python.exe -m scripts.curate_gazetteer propose --min-occurrences 2
    # review + edit outputs/gazetteer_review.json
    .venv/Scripts/python.exe -m scripts.curate_gazetteer apply
"""

from __future__ import annotations

import argparse
import asyncio
import json
from datetime import date
from pathlib import Path

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from src.growth import fetch_candidates
from src.llm import chat_model
from src.matching.curation import (
    add_alias,
    add_canonical,
    auto_reject,
    has_canonical,
    needs_disambiguation,
)
from src.matching.gazetteer import SKILLS

_GAZETTEER = Path("src/matching/gazetteer.py")
_REVIEW = Path("outputs/gazetteer_review.json")
_BATCH = 40


class _Verdict(BaseModel):
    candidate: str = Field(description="the candidate term, copied verbatim")
    verdict: str = Field(description="one of: alias, canonical, reject")
    canonical: str | None = Field(
        default=None,
        description="when verdict is 'alias', the EXACT existing canonical it maps to",
    )
    reason: str = Field(description="one short clause justifying the verdict")


class _Verdicts(BaseModel):
    verdicts: list[_Verdict]


_SYSTEM = """You curate a skills taxonomy used by a deterministic resume/job matcher.

Its value is PRECISION: an exact phrase match is trusted as evidence a candidate
genuinely has a skill, so a sloppy entry directly causes a false claim on someone's
resume. Prefer rejecting a borderline term over admitting it.

For each candidate term return exactly one verdict:

- "alias"     — it is another name, abbreviation, vendor variant, or spelling of an
                EXISTING canonical. Give that canonical verbatim from the provided
                list. Example: "Azure Kubernetes Service (AKS)" is an alias of
                "Kubernetes".
- "canonical" — a real, specific, nameable technology, tool, framework, platform or
                well-defined technical practice that is genuinely absent from the
                list. Example: "Informatica", "CrewAI".
- "reject"    — anything else: soft skills, attitudes, seniority, job-context phrases,
                market segments, or terms so generic they would match unrelated text
                ("APIs", "tools", "platforms", "best practices").

Rules:
- Never invent a canonical name that is not in the provided list for an "alias".
- A term that is merely a broader/vaguer word for an existing entry is an alias, not
  a new canonical.
- Multi-word job-description filler is a reject even when it contains a tech word."""


def _human_prompt(canonicals: list[str], batch: list[dict]) -> str:
    listed = ", ".join(canonicals)
    items = "\n".join(f"- {c['skill']}  (seen {c['occurrences']}x)" for c in batch)
    return (
        f"EXISTING CANONICALS ({len(canonicals)}):\n{listed}\n\n"
        f"CANDIDATES TO CLASSIFY ({len(batch)}):\n{items}\n\n"
        "Return one verdict per candidate, copying each candidate verbatim."
    )


async def _classify(batch: list[dict], canonicals: list[str]) -> list[_Verdict]:
    llm = chat_model("smart", max_tokens=8192, temperature=0).with_structured_output(_Verdicts)
    result: _Verdicts = await llm.ainvoke([
        SystemMessage(content=_SYSTEM),
        HumanMessage(content=_human_prompt(canonicals, batch)),
    ])
    return result.verdicts


async def propose(args: argparse.Namespace) -> None:
    rows = await fetch_candidates(limit=args.limit)
    rows = [r for r in rows if r["occurrences"] >= args.min_occurrences]
    print(f"{len(rows)} candidates at >= {args.min_occurrences} occurrences")

    canonicals = sorted(SKILLS)
    proposals: list[dict] = []
    to_classify: list[dict] = []

    for row in rows:
        reason = auto_reject(row["skill"])
        if reason:
            proposals.append({
                "candidate": row["skill"], "occurrences": row["occurrences"],
                "verdict": "reject", "canonical": None, "reason": f"auto: {reason}",
            })
        else:
            to_classify.append(row)

    auto = len(proposals)
    print(f"  {auto} auto-rejected (soft skill / workplace phrase)")
    print(f"  {len(to_classify)} sent to the model in batches of {_BATCH}")

    for i in range(0, len(to_classify), _BATCH):
        batch = to_classify[i:i + _BATCH]
        try:
            verdicts = await _classify(batch, canonicals)
        except Exception as e:  # noqa: BLE001 — keep partial results, report the gap
            print(f"  ! batch {i // _BATCH + 1} failed ({type(e).__name__}: {e}) — skipped")
            continue
        by_name = {v.candidate.strip().lower(): v for v in verdicts}
        for row in batch:
            v = by_name.get(row["skill"].strip().lower())
            if v is None:
                continue  # model dropped it; leaving it out is safer than guessing
            canonical = v.canonical if v.verdict == "alias" else None
            if canonical and not has_canonical(_GAZETTEER.read_text(encoding="utf-8"), canonical):
                # Model named a canonical that does not exist — demote, don't invent.
                canonical, v.verdict = None, "reject"
                v.reason = f"model mapped to unknown canonical: {v.canonical!r}"
            entry = {
                "candidate": row["skill"], "occurrences": row["occurrences"],
                "verdict": v.verdict, "canonical": canonical, "reason": v.reason,
            }
            if v.verdict == "canonical":
                warning = needs_disambiguation(row["skill"])
                if warning:
                    entry["warning"] = warning
            proposals.append(entry)
        print(f"  batch {i // _BATCH + 1}: {len(batch)} classified")

    proposals.sort(key=lambda p: (-p["occurrences"], p["candidate"]))
    _REVIEW.parent.mkdir(parents=True, exist_ok=True)
    _REVIEW.write_text(json.dumps(proposals, indent=2), encoding="utf-8")

    counts: dict[str, int] = {}
    for p in proposals:
        counts[p["verdict"]] = counts.get(p["verdict"], 0) + 1
    print(f"\nwrote {_REVIEW} ({len(proposals)} proposals): {counts}")
    print("REVIEW AND EDIT THAT FILE, then run: ... -m scripts.curate_gazetteer apply")


def apply(args: argparse.Namespace) -> None:
    if not _REVIEW.exists():
        raise SystemExit(f"{_REVIEW} not found — run `propose` first.")
    proposals = json.loads(_REVIEW.read_text(encoding="utf-8"))
    source = _GAZETTEER.read_text(encoding="utf-8")
    section = f"curated {date.today().isoformat()}"

    added_alias = added_canonical = skipped = 0

    # New canonicals go in FIRST so an alias may target one added in the same pass —
    # otherwise a human editing this file would have to get the ordering right.
    for p in proposals:
        if p["verdict"] == "canonical":
            new = add_canonical(
                source, p["candidate"], p.get("aliases") or [], section=section
            )
            added_canonical += new != source
            source = new

    for p in proposals:
        if p["verdict"] == "alias" and p.get("canonical"):
            try:
                new = add_alias(source, p["canonical"], p["candidate"])
            except KeyError:
                print(f"  ! unknown canonical {p['canonical']!r} for {p['candidate']!r}")
                skipped += 1
                continue
            added_alias += new != source
            source = new
        elif p["verdict"] != "canonical":
            skipped += 1

    if args.dry_run:
        print(f"dry run: +{added_alias} aliases, +{added_canonical} canonicals, {skipped} skipped")
        return

    # newline="\n" is load-bearing on Windows: the default translates every \n to
    # \r\n, which rewrites all ~570 lines and buries the real change in the diff.
    with _GAZETTEER.open("w", encoding="utf-8", newline="\n") as fh:
        fh.write(source)
    print(f"applied: +{added_alias} aliases, +{added_canonical} canonicals, {skipped} skipped")
    print("verify with: .venv/Scripts/python.exe -m pytest tests/ -q")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="command", required=True)

    p = sub.add_parser("propose", help="classify queued candidates into a review file")
    p.add_argument("--limit", type=int, default=1000)
    p.add_argument("--min-occurrences", type=int, default=2,
                   help="ignore the long tail seen only once")

    a = sub.add_parser("apply", help="write approved verdicts into the gazetteer")
    a.add_argument("--dry-run", action="store_true")

    args = ap.parse_args()
    if args.command == "propose":
        asyncio.run(propose(args))
    else:
        apply(args)


if __name__ == "__main__":
    main()
