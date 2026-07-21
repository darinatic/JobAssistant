"""Evaluate the live fit predictor on the dataset's held-out split (Phase 10).

A lightweight, model-appropriate complement to the LLM eval gate in
`scripts/run_evals.py`. The predictor is a tabular ONNX model — not a
LangSmith-traced LLM call — so it doesn't belong in that aevaluate flow; it gets
its own AUC/F1(+ordinal) check here, gated on the predictor being enabled.

In addition to AUC/F1 (binary, "good fit" vs rest via --positive-labels — works
for any dataset), this also maps labels to the ordinal fit targets used at
training time (`scripts.train_match_predictor._ordinal_label`: No Fit=0.0,
Potential Fit=0.5, Good Fit=1.0) and reports MAE, per-tier mean prediction, and
a calibration error (mean |pred - target|; same formula as MAE today — kept as
a separate named metric since "is the model accurate" and "is it calibrated to
the 0/0.5/1 scale" are different questions even though they currently share one
computation).

When `LANGSMITH_API_KEY` is set, the run is also logged to LangSmith as a
Dataset (`resume-jd-fit-holdout`, created once and reused — re-running does not
duplicate it) + an Experiment (prefixed `resumeagent-evals`, a name distinct
from the app's own tracing project) with per-example predicted-vs-target rows
and the summary metrics above. Without a key (e.g. CI), this step logs a
warning and is skipped — local metrics + --min-auc still work.

    python -m scripts.eval_match_predictor                 # report AUC/F1/MAE/...
    python -m scripts.eval_match_predictor --min-auc 0.65  # exit 1 if below (CI gate)
"""

from __future__ import annotations

import argparse
import logging
import os
import sys

LANGSMITH_DATASET_NAME = "resume-jd-fit-holdout"
LANGSMITH_EXPERIMENT_PREFIX = "resumeagent-evals"


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

    from scripts.train_match_predictor import _ordinal_label

    ds = load_dataset(args.dataset)
    split = "test" if "test" in ds else "validation"
    rows = ds[split]
    cols = rows.column_names
    rc = next(c for c in cols if "resume" in c.lower())
    jc = next(c for c in cols if "job" in c.lower() or "description" in c.lower())
    lc = next(c for c in cols if "label" in c.lower() or "fit" in c.lower())
    positives = {s.strip().lower() for s in args.positive_labels.split(",")}

    n = len(rows) if not args.limit else min(args.limit, len(rows))
    resumes: list[str] = []
    jds: list[str] = []
    labels: list[str] = []
    probs: list[float] = []
    ys: list[int] = []          # binary "good fit" vs rest (via --positive-labels)
    targets: list[float] = []   # ordinal soft target in {0, 0.5, 1}
    skipped = 0
    for i in range(n):
        r = rows[i]
        resume_text, jd_text, label = r[rc], r[jc], str(r[lc])
        p = match_predictor.predict_fit(resume_text, jd_text)
        if p is None:
            skipped += 1
            continue
        resumes.append(resume_text)
        jds.append(jd_text)
        labels.append(label)
        probs.append(p)
        ys.append(1 if label.strip().lower() in positives else 0)
        targets.append(_ordinal_label(label))
        if (i + 1) % 250 == 0:
            log.info("...scored %d/%d", i + 1, n)

    if not probs:
        log.error("No predictions produced — model load failed?")
        return 1

    auc = float(roc_auc_score(ys, probs))
    f1 = float(f1_score(ys, [p >= 0.5 for p in probs]))
    mae = float(sum(abs(p - t) for p, t in zip(probs, targets)) / len(probs))
    calibration_error = mae  # see module docstring
    tier_means: dict[str, float] = {}
    for tier, tv in (("no_fit", 0.0), ("potential_fit", 0.5), ("good_fit", 1.0)):
        tp = [p for p, t in zip(probs, targets) if abs(t - tv) < 1e-6]
        if tp:
            tier_means[tier] = float(sum(tp) / len(tp))

    log.info(
        "Predictor eval — %d rows (skipped %d): AUC=%.4f  F1=%.4f  MAE=%.4f  calib_err=%.4f",
        len(probs), skipped, auc, f1, mae, calibration_error,
    )
    for tier, m in tier_means.items():
        log.info("  tier mean[%s] = %.4f", tier, m)

    gate_failed = args.min_auc is not None and auc < args.min_auc
    if gate_failed:
        log.error("AUC %.4f below threshold %.4f", auc, args.min_auc)

    _log_to_langsmith(log, args, match_predictor, resumes, jds, labels, targets)

    return 1 if gate_failed else 0


def _log_to_langsmith(log, args, match_predictor, resumes, jds, labels, targets) -> None:
    """Log the held-out eval to LangSmith as a Dataset + Experiment. Best-effort:
    any failure (missing key, network, API error) is a warning, never fatal — the
    predictor eval must stay runnable in CI, which has no LangSmith key."""
    if not os.environ.get("LANGSMITH_API_KEY"):
        log.warning("LANGSMITH_API_KEY not set — skipping LangSmith dataset/experiment logging.")
        return

    try:
        from langsmith import Client
        from langsmith.evaluation import evaluate
        from sklearn.metrics import f1_score, roc_auc_score

        client = Client()

        if client.has_dataset(dataset_name=LANGSMITH_DATASET_NAME):
            dataset = client.read_dataset(dataset_name=LANGSMITH_DATASET_NAME)
            log.info("Reusing existing LangSmith dataset %r (%s)", LANGSMITH_DATASET_NAME, dataset.id)
        else:
            dataset = client.create_dataset(
                LANGSMITH_DATASET_NAME,
                description="Held-out resume/JD pairs for the fit-predictor eval "
                "(cnamuangtoun/resume-job-description-fit test split). outputs.target "
                "is the ordinal fit magnitude: 0=No Fit, 0.5=Potential Fit, 1=Good Fit.",
            )
            examples = [
                {
                    "inputs": {"resume": resume, "jd": jd},
                    "outputs": {"label": label, "target": target},
                }
                for resume, jd, label, target in zip(resumes, jds, labels, targets)
            ]
            client.create_examples(dataset_id=dataset.id, examples=examples)
            log.info("Created LangSmith dataset %r with %d examples", LANGSMITH_DATASET_NAME, len(examples))

        def predict(inputs: dict) -> dict:
            prob = match_predictor.predict_fit(inputs["resume"], inputs["jd"])
            return {"fit_prob": prob if prob is not None else 0.0}

        def abs_error(run, example) -> dict:
            target = (example.outputs or {}).get("target", 0.0)
            pred = (run.outputs or {}).get("fit_prob", 0.0)
            return {"key": "abs_error", "score": abs(pred - target)}

        def ordinal_summary(runs, examples) -> dict:
            preds = [(r.outputs or {}).get("fit_prob", 0.0) for r in runs]
            tgts = [(e.outputs or {}).get("target", 0.0) for e in examples]
            mae_ = sum(abs(p - t) for p, t in zip(preds, tgts)) / len(preds)
            results = [
                {"key": "mae", "score": mae_},
                {"key": "calibration_error", "score": mae_},
            ]
            for tier, tv in (("no_fit", 0.0), ("potential_fit", 0.5), ("good_fit", 1.0)):
                tp = [p for p, t in zip(preds, tgts) if abs(t - tv) < 1e-6]
                if tp:
                    results.append({"key": f"mean_pred_{tier}", "score": sum(tp) / len(tp)})
            bin_y = [1 if abs(t - 1.0) < 1e-6 else 0 for t in tgts]
            if 0 < sum(bin_y) < len(bin_y):
                results.append({"key": "auc_good_vs_rest", "score": float(roc_auc_score(bin_y, preds))})
                results.append({
                    "key": "f1_good_vs_rest",
                    "score": float(f1_score(bin_y, [p >= 0.5 for p in preds])),
                })
            return {"results": results}

        results = evaluate(
            predict,
            data=LANGSMITH_DATASET_NAME,
            evaluators=[abs_error],
            summary_evaluators=[ordinal_summary],
            experiment_prefix=LANGSMITH_EXPERIMENT_PREFIX,
            description="Fit-predictor holdout eval — ordinal MAE/calibration/AUC "
            "against the No/Potential/Good Fit soft targets.",
            metadata={"model": "match_predictor", "source_dataset": args.dataset, "n_examples": len(resumes)},
        )
        log.info("LangSmith experiment: %s", results.experiment_name)
        if results.url:
            log.info("LangSmith experiment URL: %s", results.url)
    except Exception as e:
        log.warning("LangSmith logging failed (metrics above still stand): %s", e)


if __name__ == "__main__":
    sys.exit(main())
