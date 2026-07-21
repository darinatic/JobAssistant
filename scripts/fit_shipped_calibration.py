"""Produce the shipped ``calibration.json`` for a fit-predictor model dir.

The raw ONNX fit predictor is trained as an ordinal regressor (targets 0 / 0.5 /
1.0 for No / Potential / Good Fit) and its raw sigmoid output is compressed —
even a strong resume<->JD pair only reaches ~0.5. This script fits a
**percentile min-max display-stretch** (``fit_display_stretch`` in
``src/match_predictor_calibration.py``) on a shuffled held-out sample so a
strong pair reads high on the 0-100 display scale while the relative ordering
of jobs stays honest (it is a display calibration, not a probability fix).

It scores the dataset's held-out split with the TRUE RAW (uncalibrated) model
— any existing calibration.json in the model dir is deleted first and the
predictor's module-level cache is reset so ``predict_fit`` cannot pick up a
stale calibration mid-run — fits the stretch, writes ``calibration.json`` into
the model dir, then reloads (picking up the new calibration this time) and
prints a distribution report so the choice is auditable before shipping:

    * per-ordinal-tier mean of the STRETCHED (calibrated) score
    * two concrete pairs, calibrated: a strong AI/ML resume vs a matching
      AI/ML JD, and the same resume vs an unrelated (nursing) JD
    * the final stretch knots

Usage:
    .venv/Scripts/python.exe -m scripts.fit_shipped_calibration \\
        --model-path artifacts/fit-predictor-v2
"""

from __future__ import annotations

import argparse
import json
import logging
import os
from pathlib import Path

log = logging.getLogger("resumeagent.fit_shipped_calibration")

DEFAULT_MODEL_PATH = "artifacts/fit-predictor-v2"
DEFAULT_DATASET = "cnamuangtoun/resume-job-description-fit"

_STRONG_RESUME = """\
AI Engineer with a Bachelor's in Computer Science. Experienced in designing multi-agent systems,
identifying process gaps, and collaborating with cross-functional teams to deploy production-grade
LLM workflows that streamline manual redundancies. Certified in Cloud (AWS, Azure) and Security+.
Skilled in Python, SQL, and prompt engineering across major LLMs including GPT, Claude and Gemini.

SKILLS
Python (LangChain, LangGraph, FastAPI, Scikit-learn), SQL, AI Agent Development, LLM Integration
(GPT, Claude, Llama, Ollama), Prompt Engineering, RAG, Multi-Agent Systems, LLM Evaluation,
Workflow Automation, Vector Databases (ChromaDB, FAISS), Process Optimization, AWS, Azure, Docker,
CI/CD, Stakeholder Communication.

WORK EXPERIENCE
AI Engineer, HeyHi Pte Ltd
- Architected and built a low-latency conversational AI product with RAG-grounded responses using
  OpenAI models, integrated with humanlike TTS for voice output, on an event-driven serverless
  backend (FastAPI + AWS Lambda).
- Built a multi-agent "LLM-as-a-judge" evaluation pipeline for a conversational AI agent, automating
  simulation of user inputs and scoring of conversation quality, reducing manual evaluation effort by 70%.

xCloud Intern, Home Team Science and Technology Agency
- Engineered a text classification system using BERT with PEFT fine-tuning, performed data
  augmentation to simulate real-world inputs.
"""

_MATCHING_JD = """\
We are hiring an AI Engineer to design and ship production LLM systems. You will build
retrieval-augmented generation (RAG) pipelines, multi-agent orchestration, and evaluation
harnesses ("LLM-as-a-judge") for conversational AI products. Required: strong Python, experience
with LangChain/LangGraph, prompt engineering across GPT/Claude/Llama, vector databases (FAISS or
ChromaDB), and cloud deployment (AWS or Azure). Bonus: fine-tuning transformer models (BERT, PEFT),
FastAPI, CI/CD, and experience reducing manual QA effort via automated evaluation pipelines.
"""

_UNRELATED_JD = """\
We are hiring a Registered Nurse for our inpatient medical-surgical ward. Responsibilities include
direct patient care, administering medications per physician orders, monitoring vital signs,
wound care, and coordinating with physicians and allied health staff on care plans. Required:
valid nursing license, BLS/ACLS certification, at least 2 years of acute-care hospital experience,
and strong bedside manner. Familiarity with electronic health record (EHR) charting systems
(e.g. Epic, Cerner) is required.
"""


def _reset_predictor_cache() -> None:
    """Force src.match_predictor to forget any loaded bundle so the next
    predict_fit() call reloads from disk (picking up a just-written or
    just-deleted calibration.json instead of a cached stale one)."""
    from src import match_predictor

    match_predictor._bundle = None
    match_predictor._load_failed = False


def _score_pairs(pairs: list[tuple[str, str]]) -> list[float]:
    from src import match_predictor

    out = []
    for resume, jd in pairs:
        p = match_predictor.predict_fit(resume, jd)
        out.append(0.0 if p is None else p)
    return out


def main() -> int:
    logging.basicConfig(level=logging.INFO)
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--model-path", default=DEFAULT_MODEL_PATH)
    ap.add_argument("--dataset", default=DEFAULT_DATASET)
    ap.add_argument("--limit", type=int, default=1000)
    ap.add_argument("--lo-pct", type=float, default=5.0)
    ap.add_argument("--hi-pct", type=float, default=95.0)
    args = ap.parse_args()

    model_path = Path(args.model_path)
    calib_path = model_path / "calibration.json"

    # Score TRUE RAW: delete any existing calibration.json and reset the
    # predictor cache so predict_fit() is uncalibrated during scoring.
    if calib_path.exists():
        log.info("Removing existing %s so scoring is uncalibrated", calib_path)
        calib_path.unlink()

    os.environ["MATCH_PREDICTOR_MODEL"] = "v1"
    os.environ["MATCH_PREDICTOR_PATH"] = str(model_path)

    from src import match_predictor  # import AFTER env vars are set

    _reset_predictor_cache()

    from datasets import load_dataset

    from scripts.train_match_predictor import _ordinal_label

    ds = load_dataset(args.dataset)
    split = "test" if "test" in ds else "validation"
    data = ds[split].shuffle(seed=13)  # the split is ORDERED BY LABEL — must shuffle
    n = min(args.limit, len(data))
    data = data.select(range(n))

    cols = data.column_names
    resume_col = next(c for c in cols if "resume" in c.lower())
    jd_col = next(c for c in cols if "job" in c.lower() or "description" in c.lower())
    label_col = next(c for c in cols if "label" in c.lower() or "fit" in c.lower())
    log.info("Scoring %d held-out rows (%s split) — resume=%s jd=%s label=%s",
              n, split, resume_col, jd_col, label_col)

    raw_scores: list[float] = []
    tiers: list[float] = []
    for row in data:
        p = match_predictor.predict_fit(row[resume_col], row[jd_col])
        raw_scores.append(0.0 if p is None else p)
        tiers.append(_ordinal_label(row[label_col]))

    if not raw_scores:
        log.error("No rows scored; aborting.")
        return 1

    from src.match_predictor_calibration import fit_display_stretch

    calib = fit_display_stretch(raw_scores, lo_pct=args.lo_pct, hi_pct=args.hi_pct)

    model_path.mkdir(parents=True, exist_ok=True)
    with open(calib_path, "w", encoding="utf-8") as f:
        json.dump(calib, f)
    log.info("Wrote %s", calib_path)

    # Reload so predict_fit() now applies the freshly written calibration.
    _reset_predictor_cache()

    from src.match_predictor_calibration import apply_calibration

    stretched = [apply_calibration(p, calib) for p in raw_scores]

    print("\n=== Per-tier mean STRETCHED (calibrated) score, n=%d ===" % n)
    for tier_name, tv in (("No Fit", 0.0), ("Potential Fit", 0.5), ("Good Fit", 1.0)):
        vals = [s for s, y in zip(stretched, tiers) if abs(y - tv) < 1e-6]
        if vals:
            mean = sum(vals) / len(vals)
            print(f"  {tier_name:15s} n={len(vals):4d}  mean={mean * 100:5.1f}%")
        else:
            print(f"  {tier_name:15s} n=0 (none in this sample)")

    strong_raw = _score_pairs([(_STRONG_RESUME, _MATCHING_JD)])[0]
    weak_raw = _score_pairs([(_STRONG_RESUME, _UNRELATED_JD)])[0]
    strong_pct = apply_calibration(strong_raw, calib) * 100
    weak_pct = apply_calibration(weak_raw, calib) * 100

    print("\n=== Concrete pairs (calibrated %) ===")
    print(f"  Strong AI/ML resume vs matching AI/ML JD : raw={strong_raw:.4f} -> {strong_pct:5.1f}%")
    print(f"  Strong AI/ML resume vs unrelated nursing JD: raw={weak_raw:.4f} -> {weak_pct:5.1f}%")

    print("\n=== Final stretch knots ===")
    print(json.dumps(calib, indent=2))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
