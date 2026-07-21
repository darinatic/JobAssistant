"""One-page estimator — calibrated against real Tectonic renders (see page_budget)."""

from src.utils.page_budget import estimate_rendered_lines, page_fit, page_fit_target

_HEAD = "# Jane Candidate\ncontact line here\n## Summary\nShort summary line.\n## Skills\nPython, PyTorch\n## Experience\n### ML Engineer, Acme (2023-2025)\n"
_BULLET = "- Built and shipped a production feature that improved a key metric by 30% for the platform\n"


def _resume(n_bullets: int) -> str:
    return _HEAD + _BULLET * n_bullets


def test_short_resume_fits_one_page():
    fit = page_fit(_resume(10))
    assert fit["fits_one_page"] is True
    assert fit["estimated_pages"] == 1
    assert fit["overflow_lines"] == 0


def test_long_resume_overflows_with_trim_estimate():
    fit = page_fit(_resume(50))
    assert fit["fits_one_page"] is False
    assert fit["estimated_pages"] >= 2
    assert fit["overflow_lines"] > 0


def test_boundary_matches_calibration():
    # Real renders: ~36 bullets = 1 page, ~37 = 2 pages (this header adds a few lines).
    assert page_fit(_resume(30))["fits_one_page"] is True
    assert page_fit(_resume(45))["fits_one_page"] is False


def test_long_bullets_wrap_to_multiple_lines():
    short = "- short bullet\n" * 5
    long = "- " + ("word " * 60) + "\n"  # ~300 chars -> wraps to ~3-4 lines
    assert estimate_rendered_lines(long) > estimate_rendered_lines(short) / 5 * 1  # one long > one short
    assert estimate_rendered_lines(long) >= 3


# --- page_fit_target: "avoid an under-used trailing page" -------------------

def test_target_one_page_resume_needs_no_trim():
    t = page_fit_target(_resume(20))
    assert t["estimated_pages"] == 1
    assert t["under_used_trailing_page"] is False
    assert t["target_pages"] == 1
    assert t["trim_lines"] == 0
    assert t["target_line_budget"] is None


def test_target_small_spill_onto_page_2_recommends_trim_to_one():
    # ~1.05 pages: page 2 has only a few lines -> under-used, trim down to 1 page.
    t = page_fit_target(_resume(45))
    assert t["estimated_pages"] == 2
    assert t["under_used_trailing_page"] is True
    assert t["target_pages"] == 1
    assert t["trim_lines"] > 0
    assert t["target_line_budget"] == 52.0


def test_target_small_spill_onto_page_3_recommends_trim_to_two():
    # ~2.05 pages: generalizes beyond one page — trim to the nearest full 2 pages.
    t = page_fit_target(_resume(100))
    assert t["estimated_pages"] == 3
    assert t["under_used_trailing_page"] is True
    assert t["target_pages"] == 2
    assert t["target_line_budget"] == 104.0
    assert t["trim_lines"] > 0


def test_target_well_used_trailing_page_is_left_alone():
    # ~1.7 pages: page 2 is genuinely ~2/3 full — do NOT suggest gutting it.
    t = page_fit_target(_resume(80))
    assert t["estimated_pages"] == 2
    assert t["under_used_trailing_page"] is False
    assert t["target_pages"] == 2
    assert t["trim_lines"] == 0
