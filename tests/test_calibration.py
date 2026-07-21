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
