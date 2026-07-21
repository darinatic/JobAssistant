from src.match_predictor_calibration import apply_calibration, fit_calibration


def test_apply_identity_when_no_calibration():
    assert apply_calibration(0.42, None) == 0.42


def test_fit_then_apply_is_monotonic_and_stretches():
    # raw preds compressed into [0.1, 0.6]; targets span [0,1].
    raw = [0.10, 0.20, 0.30, 0.40, 0.50, 0.60]
    tgt = [0.0, 0.0, 0.5, 0.5, 1.0, 1.0]
    calib = fit_calibration(raw, tgt)
    lo, hi = apply_calibration(0.12, calib), apply_calibration(0.58, calib)
    assert 0.0 <= lo <= hi <= 1.0        # monotonic, clipped
    assert hi > 0.7                       # a strong raw pred stretches upward
    assert apply_calibration(0.001, calib) <= lo   # clamps below the fitted range


def test_apply_clips_out_of_range():
    calib = fit_calibration([0.2, 0.8], [0.0, 1.0])
    assert 0.0 <= apply_calibration(2.0, calib) <= 1.0


def test_display_stretch_maps_percentile_band_to_full_range():
    from src.match_predictor_calibration import apply_calibration, fit_display_stretch
    raw = [0.20, 0.25, 0.30, 0.35, 0.40, 0.45, 0.50, 0.55]  # compressed into [0.2, 0.55]
    calib = fit_display_stretch(raw, lo_pct=5, hi_pct=95)
    lo, hi = apply_calibration(0.21, calib), apply_calibration(0.54, calib)
    assert 0.0 <= lo < hi <= 1.0        # monotonic within [0,1]
    assert hi > 0.8                       # a top-of-range score reads high
    assert lo < 0.2                       # a bottom-of-range score reads low
    assert apply_calibration(0.9, calib) <= 0.95 and apply_calibration(0.0, calib) >= 0.0  # clipped
