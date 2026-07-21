"""Schema robustness — Claude's structured output sometimes emits 'null' for lists."""

from src.agents.schemas import ParsedJobDescription


def _base(**kw):
    return {
        "company": "Acme", "title": "AI Engineer", "location": "Singapore",
        "experience_required": "1-2y", "experience_level": "junior", **kw,
    }


def test_null_string_list_coerced_to_empty():
    # The exact payload that used to 500: benefits='null'.
    jd = ParsedJobDescription(**_base(benefits="null", required_skills=None))
    assert jd.benefits == []
    assert jd.required_skills == []


def test_bare_string_wrapped_into_list():
    jd = ParsedJobDescription(**_base(tech_stack="Python"))
    assert jd.tech_stack == ["Python"]


def test_red_flags_null_coerced():
    jd = ParsedJobDescription(**_base(red_flags="null"))
    assert jd.red_flags == []


def test_normal_lists_untouched():
    jd = ParsedJobDescription(**_base(required_skills=["Python", "RAG"]))
    assert jd.required_skills == ["Python", "RAG"]


def test_enum_tag_leak_sanitized():
    # The exact payload that failed the whole tailor pipeline: a leaked closing tag
    # inside the enum value -> would raise an enum validation error.
    jd = ParsedJobDescription(**_base(work_arrangement="unspecified</work_arrangement>\n</invoke>"))
    assert jd.work_arrangement.value == "unspecified"


def test_string_tag_leak_stripped_but_clean_kept():
    jd = ParsedJobDescription(**_base(title="AI Engineer</title></invoke>"))
    assert jd.title == "AI Engineer"
    jd2 = ParsedJobDescription(**_base(title="C++ Engineer"))   # '<' without a closing tag is fine
    assert jd2.title == "C++ Engineer"
