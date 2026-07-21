"""Run a resume-tailor prompt version over the golden set and score it.

    python -m evals.run --version v3 --style faithful      # eval one version
    python -m evals.run --compare v3 v4 --style faithful    # diff two saved runs

Deterministic graders only (honesty, coverage, one-page fit, structure) — no LLM judge,
no tracker. Real Sonnet calls per case, so it costs tokens; runs at temperature 0.
Results are saved to evals/results/<version>_<style>.json for later comparison.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path

_RESULTS = Path(__file__).parent / "results"


def _fmt_summary(s: dict) -> str:
    lines = [
        f"  honesty-clean : {s['honesty_clean']}/{s['graded']} ({s['honesty_clean_pct']}%)  "
        f"[fabrications={s['total_fabrications']} trap-hits={s['total_forbidden_hits']}]",
        f"  keyword cover : {s['avg_keyword_coverage']}",
        f"  one page      : {s['one_page_pct']}%",
        f"  structure ok  : {s['structure_ok_pct']}%",
    ]
    if "avg_judge_overall" in s:
        lines.append(f"  judge (1-5)   : overall {s['avg_judge_overall']}  "
                     f"[relevance {s.get('avg_judge_relevance')} quality {s.get('avg_judge_quality')} "
                     f"ats {s.get('avg_judge_ats')}]")
    return "\n".join(lines)


async def _run(version: str, style: str, use_judge: bool = False) -> dict:
    os.environ["PROMPT_OVERRIDES"] = f"resume_tailor={version}"  # get_prompt reads this per call
    from evals import graders
    from evals.golden import GOLDEN
    from src import services

    rows = []
    for case in GOLDEN:
        case_style = case.style or style
        try:
            result = await services.run_full_tailoring(
                case.jd, master_cv=case.cv, style=case_style, include_cover_letter=False,
            )
            md = result.tailored_resume.markdown_content if result.tailored_resume else ""
        except Exception as e:  # a failed tailor is itself a data point, not a crash
            md = ""
            print(f"  ! {case.id}: tailoring failed: {e}")
        g = graders.grade(case.cv, case.jd, md, case.forbidden)
        g["id"], g["focus"], g["style"] = case.id, case.focus, case_style
        g["output"] = md      # keep the tailored resume for manual review of flags
        if use_judge and md:
            from evals.judge import judge_output
            j = await judge_output(case.jd, md) or {}
            for k in ("relevance", "quality", "ats", "overall"):
                if isinstance(j.get(k), (int, float)):
                    g[f"judge_{k}"] = j[k]
            g["judge_rationale"] = j.get("rationale") or j.get("error")
        rows.append(g)
        flag = "" if g.get("ok") and g["fabrications"] == 0 and not g["forbidden_hits"] else "  <-- REVIEW"
        judge = f" judge={g.get('judge_overall','-')}/5" if use_judge else ""
        print(f"  {case.id:16} style={case_style:10} fab={g.get('fabrications','-')} "
              f"trap={g.get('forbidden_hits',[])} cover={g.get('keyword_coverage','-')} "
              f"1pg={g.get('fits_one_page','-')}{judge}{flag}")

    summary = graders.summarize(rows)
    out = {"version": version, "style": style, "summary": summary, "cases": rows}
    _RESULTS.mkdir(exist_ok=True)
    path = _RESULTS / f"{version}_{style}.json"
    path.write_text(json.dumps(out, indent=2))
    print(f"\n=== {version} / {style} ===\n{_fmt_summary(summary)}\n  saved -> {path}")
    _log_mlflow(out)
    return out


def _log_mlflow(out: dict) -> None:
    """Track the run in MLflow (local ./mlruns file store — no server). Optional:
    `pip install -e '.[eval]'`; view with `mlflow ui`. Also serves the fit-predictor
    evals later — one experiment tracker for both."""
    try:
        import mlflow
    except ImportError:
        print("  (mlflow not installed — skipping tracking; `pip install -e \".[eval]\"`)")
        return
    from src.prompts import get_prompt
    from src.utils.config import settings

    version, style, summary = out["version"], out["style"], out["summary"]
    try:
        sha = get_prompt("resume_tailor", version=version).sha256
    except Exception:
        sha = "unknown"
    mlflow.set_experiment("resume_tailor_prompts")
    with mlflow.start_run(run_name=f"{version}_{style}"):
        mlflow.log_params({
            "prompt": "resume_tailor", "version": version, "style": style,
            "model": settings.anthropic_sonnet_model, "prompt_sha": sha,
            "n_cases": summary["cases"],
        })
        mlflow.log_metrics({k: v for k, v in summary.items() if isinstance(v, (int, float))})
        mlflow.log_dict(out, "results.json")
    print("  logged to MLflow (experiment 'resume_tailor_prompts')")


def _compare(v_a: str, v_b: str, style: str) -> None:
    a = json.loads((_RESULTS / f"{v_a}_{style}.json").read_text())["summary"]
    b = json.loads((_RESULTS / f"{v_b}_{style}.json").read_text())["summary"]
    keys = ["honesty_clean_pct", "total_fabrications", "total_forbidden_hits",
            "avg_keyword_coverage", "one_page_pct", "structure_ok_pct",
            "avg_judge_overall", "avg_judge_relevance", "avg_judge_quality", "avg_judge_ats"]
    print(f"{'metric':22} {v_a:>10} {v_b:>10}   delta")
    for k in keys:
        if k not in a and k not in b:
            continue
        da, db = a.get(k, 0), b.get(k, 0)
        print(f"{k:22} {da:>10} {db:>10}   {db - da:+.3g}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--version", default="v3", help="resume_tailor prompt version to eval")
    ap.add_argument("--style", default="faithful", choices=["faithful", "balanced", "aggressive"])
    ap.add_argument("--compare", nargs=2, metavar=("VER_A", "VER_B"),
                    help="diff two already-saved runs instead of running")
    ap.add_argument("--judge", action="store_true",
                    help="also score each output with the OpenAI LLM-judge (costs OpenAI tokens)")
    args = ap.parse_args()
    if args.compare:
        _compare(args.compare[0], args.compare[1], args.style)
    else:
        asyncio.run(_run(args.version, args.style, use_judge=args.judge))


if __name__ == "__main__":
    main()
