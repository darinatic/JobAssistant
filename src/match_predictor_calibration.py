"""Monotonic calibration for the fit predictor's raw ONNX output.

Fit-time (dev, needs scikit-learn) turns held-out (raw_prob, target) pairs into an
isotonic map serialized as sorted knots. Apply-time (prod path) is pure Python —
linear interpolation between knots — so serving needs no sklearn/torch. Shipped as
calibration.json alongside model.onnx; applied in src/match_predictor.predict_fit.
"""

from __future__ import annotations

from bisect import bisect_right


def fit_calibration(raw: list[float], targets: list[float]) -> dict:
    """Fit an isotonic (monotonic non-decreasing) map raw->target; return knots."""
    from sklearn.isotonic import IsotonicRegression

    iso = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0)
    iso.fit(raw, targets)
    xs = sorted(set(float(x) for x in raw))
    ys = [float(min(1.0, max(0.0, iso.predict([x])[0]))) for x in xs]
    return {"type": "isotonic", "x": xs, "y": ys}


def _percentile(sorted_vals: list[float], pct: float) -> float:
    if not sorted_vals:
        return 0.0
    k = (len(sorted_vals) - 1) * pct / 100.0
    lo = int(k)
    hi = min(lo + 1, len(sorted_vals) - 1)
    return sorted_vals[lo] + (sorted_vals[hi] - sorted_vals[lo]) * (k - lo)


def fit_display_stretch(raw: list[float], lo_pct: float = 5.0, hi_pct: float = 95.0) -> dict:
    """Percentile min-max stretch: map the raw score's [lo_pct, hi_pct] percentile
    band onto [0.05, 0.95], so a compressed score range reads across the full 0-100
    display. Honest as a RELATIVE fit score (rank on the scale), not a probability."""
    s = sorted(float(x) for x in raw)
    lo, hi = _percentile(s, lo_pct), _percentile(s, hi_pct)
    if hi <= lo:
        hi = lo + 1e-6
    return {"type": "stretch", "x": [lo, hi], "y": [0.05, 0.95]}


def apply_calibration(prob: float, calib: dict | None) -> float:
    """Map a raw prob through the calibration knots (linear interp), clip to [0,1].
    Identity when calib is None."""
    if not calib:
        return prob
    xs, ys = calib["x"], calib["y"]
    if not xs:
        return prob
    if prob <= xs[0]:
        return ys[0]
    if prob >= xs[-1]:
        return ys[-1]
    i = bisect_right(xs, prob)
    x0, x1, y0, y1 = xs[i - 1], xs[i], ys[i - 1], ys[i]
    t = (prob - x0) / (x1 - x0) if x1 > x0 else 0.0
    return max(0.0, min(1.0, y0 + t * (y1 - y0)))
