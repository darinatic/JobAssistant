"""Evaluate the live fit predictor on the dataset's held-out split (Phase 10).

A lightweight, model-appropriate complement to the LLM eval gate in
`scripts/run_evals.py`. The predictor is a tabular ONNX model — not a
LangSmith-traced LLM call — so it doesn't belong in that aevaluate flow; it gets
its own AUC/F1 check here, gated on the predictor being enabled.

    python -m scripts.eval_match_predictor                 # report AUC/F1
    python -m scripts.eval_match_predictor --min-auc 0.65  # exit 1 if below (CI gate)
"""

from __future__ import annotations

import argparse
import logging
import sys


def main() -> int:
    logging.basicConfig(level=logging.INFO)
    from dotenv import load_dotenv

    load_dotenv()
    log = logging.getLogger("resumeagent.eval_predictor")

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dataset", default="cnamuangtoun/resume-job-description-fit")
    ap.add_argument("--positive-labels", default="good fit,good,fit,1,true")
    ap.add_argument("--limit", type=int, default=0, help="cap rows for a quick check (0 = all)")
    ap.add_argument("--min-auc", type=float, default=None, help="exit 1 if AUC is below this")
    args = ap.parse_args()

    from src import match_predictor

    if not match_predictor.is_enabled():
        log.warning("MATCH_PREDICTOR_MODEL is off — set it + the artifact path to evaluate. Skipping.")
        return 0

    from datasets import load_dataset
    from sklearn.metrics import f1_score, roc_auc_score

    ds = load_dataset(args.dataset)
    split = "test" if "test" in ds else "validation"
    rows = ds[split]
    cols = rows.column_names
    rc = next(c for c in cols if "resume" in c.lower())
    jc = next(c for c in cols if "job" in c.lower() or "description" in c.lower())
    lc = next(c for c in cols if "label" in c.lower() or "fit" in c.lower())
    positives = {s.strip().lower() for s in args.positive_labels.split(",")}

    n = len(rows) if not args.limit else min(args.limit, len(rows))
    probs: list[float] = []
    ys: list[int] = []
    skipped = 0
    for i in range(n):
        r = rows[i]
        p = match_predictor.predict_fit(r[rc], r[jc])
        if p is None:
            skipped += 1
            continue
        probs.append(p)
        ys.append(1 if str(r[lc]).strip().lower() in positives else 0)
        if (i + 1) % 250 == 0:
            log.info("...scored %d/%d", i + 1, n)

    if not probs:
        log.error("No predictions produced — model load failed?")
        return 1

    auc = float(roc_auc_score(ys, probs))
    f1 = float(f1_score(ys, [p >= 0.5 for p in probs]))
    log.info("Predictor eval — %d rows (skipped %d): AUC=%.4f  F1=%.4f", len(probs), skipped, auc, f1)

    if args.min_auc is not None and auc < args.min_auc:
        log.error("AUC %.4f below threshold %.4f", auc, args.min_auc)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
