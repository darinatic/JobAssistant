from scripts.train_match_predictor import _ordinal_label


def test_ordinal_label_maps_three_tiers():
    assert _ordinal_label("Good Fit") == 1.0
    assert _ordinal_label("good fit") == 1.0
    assert _ordinal_label("Potential Fit") == 0.5
    assert _ordinal_label("No Fit") == 0.0


def test_ordinal_label_unknown_defaults_to_zero():
    assert _ordinal_label("garbage") == 0.0
    assert _ordinal_label("") == 0.0
