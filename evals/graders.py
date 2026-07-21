"""Deterministic graders for a tailored resume. No LLM — objective + repeatable.

Everything here reuses the app's own honesty/matching/page-budget logic, so the eval
measures exactly what production enforces."""

from __future__ import annotations

from src.matching import extract_skills, lint_resume
from src.utils.page_budget import page_fit


def _supportable_coverage(cv: str, jd: str, tailored: str) -> float:
    """Of the JD skills the CV can honestly back, what fraction did the output surface?
    (Coverage of SUPPORTABLE skills — not raw JD keywords — so it can't reward stuffing.)"""
    cv_sk, jd_sk, out_sk = extract_skills(cv), extract_skills(jd), extract_skills(tailored)
    supportable = jd_sk & cv_sk
    if not supportable:
        return 1.0
    return round(len(supportable & out_sk) / len(supportable), 3)


def _structure_ok(md: str) -> bool:
    lines = md.splitlines()
    has_name = any(l.startswith("# ") for l in lines)
    has_section = any(l.startswith("## ") for l in lines)
    has_bullet = any(l.strip().startswith("- ") for l in lines)
    return has_name and has_section and has_bullet


def grade(cv: str, jd: str, tailored: str, forbidden: tuple[str, ...] = ()) -> dict:
    """Score one tailored resume. Lower fabrication = better; higher coverage = better."""
    if not tailored:
        return {"ok": False, "reason": "empty output"}

    report = lint_resume(cv, tailored)
    fit = page_fit(tailored)
    low = tailored.lower()
    # Case-specific honesty traps (domain terms the CV never states).
    forbidden_hits = sorted(t for t in forbidden if t in low and t not in cv.lower())

    return {
        "ok": True,
        "fabrications": len(report.findings),
        "fab_skill": len(report.of("skill")),
        "fab_metric": len(report.of("metric")),
        "fab_domain": len(report.of("domain")),
        "fab_findings": [f"{f.kind}:{f.value}" for f in report.findings],  # WHAT was flagged
        "forbidden_hits": forbidden_hits,      # empty = passed the honesty trap
        "keyword_coverage": _supportable_coverage(cv, jd, tailored),
        "fits_one_page": fit["fits_one_page"],
        "est_pages": fit["estimated_pages"],
        "structure_ok": _structure_ok(tailored),
        "chars": len(tailored),
    }


def summarize(rows: list[dict]) -> dict:
    """Aggregate case grades into the headline numbers for a version×style run."""
    graded = [r for r in rows if r.get("ok")]
    n = len(graded) or 1
    clean = sum(1 for r in graded if r["fabrications"] == 0 and not r["forbidden_hits"])
    out = {
        "cases": len(rows),
        "graded": len(graded),
        "honesty_clean": clean,                                  # 0 fabrications AND no trap hits
        "honesty_clean_pct": round(100 * clean / n),
        "total_fabrications": sum(r["fabrications"] for r in graded),
        "total_forbidden_hits": sum(len(r["forbidden_hits"]) for r in graded),
        "avg_keyword_coverage": round(sum(r["keyword_coverage"] for r in graded) / n, 3),
        "one_page_pct": round(100 * sum(1 for r in graded if r["fits_one_page"]) / n),
        "structure_ok_pct": round(100 * sum(1 for r in graded if r["structure_ok"]) / n),
    }
    # LLM-judge averages, only when a run used --judge.
    for dim in ("relevance", "quality", "ats", "overall"):
        scored = [r[f"judge_{dim}"] for r in graded if isinstance(r.get(f"judge_{dim}"), (int, float))]
        if scored:
            out[f"avg_judge_{dim}"] = round(sum(scored) / len(scored), 2)
    return out
