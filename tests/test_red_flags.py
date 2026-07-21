from datetime import date

from src.intel.red_flags import scan_red_flags


def _codes(flags):
    return {f.code for f in flags}


def test_clean_posting_has_no_flags():
    job = {"description": (
        "Senior Machine Learning Engineer at Acme. You will design, build, and "
        "deploy retrieval-augmented generation pipelines using PyTorch and modern "
        "LLM tooling, collaborating with product and data teams to ship reliable AI "
        "features. We look for 5+ years of experience and strong Python "
        "fundamentals. Apply via our careers page at acme.com/careers."),
        "company": "Acme", "posted_date": "2026-07-10"}
    assert scan_red_flags(job, today=date(2026, 7, 11)) == []


def test_flags_upfront_payment_and_messaging_only():
    job = {"description": ("Easy work-from-home role. Pay a registration fee of $50 "
                           "to start. Contact us only on WhatsApp +65 8000 0000."),
           "company": "X"}
    codes = _codes(scan_red_flags(job, today=date(2026, 7, 11)))
    assert "upfront_payment" in codes
    assert "messaging_only" in codes


def test_flags_personal_email_and_sensitive_data():
    job = {"description": ("Send your NRIC and bank account details to "
                           "hr.recruit2026@gmail.com to proceed."),
           "company": "X"}
    codes = _codes(scan_red_flags(job, today=date(2026, 7, 11)))
    assert "personal_email" in codes
    assert "sensitive_data" in codes


def test_flags_stale_posting():
    job = {"description": "A normal detailed job description that is quite long " * 10,
           "company": "X", "posted_date": "2026-04-01"}
    codes = _codes(scan_red_flags(job, today=date(2026, 7, 11)))
    assert "stale_posting" in codes


def test_flags_unlicensed_agency_but_not_when_ea_present():
    unlicensed = {"description": "We are hiring on behalf of our client in banking.",
                  "company": "X"}
    assert "unlicensed_agency" in _codes(scan_red_flags(unlicensed, today=date(2026, 7, 11)))
    licensed = {"description": ("Hiring on behalf of our client in banking. "
                                "EA Licence No. 12C3456."),
                "company": "X"}
    assert "unlicensed_agency" not in _codes(scan_red_flags(licensed, today=date(2026, 7, 11)))


def test_flags_vague_jd_on_thin_posting():
    job = {"description": "Great opportunity. Apply now.", "company": "X"}
    codes = _codes(scan_red_flags(job, today=date(2026, 7, 11)))
    assert "vague_jd" in codes


def test_scan_bounds_huge_description():
    huge = "Pay a registration fee. " + ("x" * 500_000)
    flags = scan_red_flags({"description": huge, "company": "X"}, today=date(2026, 7, 11))
    # still detects the early red flag, and doesn't choke on the size
    assert any(f.code == "upfront_payment" for f in flags)
