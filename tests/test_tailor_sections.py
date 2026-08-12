"""The tailor must mirror the master CV's sections, never invent one.

v1-v3 hardcoded a 7-section Output Format listing "Professional Summary" as
mandatory, so the tailor wrote a summary even for CVs that deliberately have none.
That is a fabricated *section*, and on a full resume it costs ~5 rendered lines —
measured as exactly the gap between one page and two in the retuned template.
"""

import pytest

from src.agents.resume_tailor import _STYLE_RULES, ResumeTailorAgent
from src.agents.schemas import (
    ExperienceLevel,
    MatchRecommendation,
    ParsedJobDescription,
    SkillMatch,
)
from src.prompts import get_prompt

_CV_NO_SUMMARY = """# Jane Candidate

jane@example.com | github.com/jane

## Skills

Python, PyTorch, RAG

## Experience

### ML Engineer, Acme | 2023 - Present

- Shipped a production RAG pipeline.
"""


@pytest.fixture
def jd() -> ParsedJobDescription:
    return ParsedJobDescription(
        title="AI Engineer",
        company="Globex",
        location="Singapore",
        experience_level=ExperienceLevel.MID,
        experience_required="3+ years",
        required_skills=["Python", "RAG"],
        responsibilities=["Build LLM features"],
    )


@pytest.fixture
def match() -> SkillMatch:
    return SkillMatch(
        overall_score=80,
        matched_required=["Python", "RAG"],
        missing_required=["Kubernetes"],
        recommendation=MatchRecommendation.APPLY,
        reasoning="Strong overlap on the core stack.",
    )


# --- the registered prompt ---------------------------------------------------

def test_v4_is_the_active_prompt():
    assert get_prompt("resume_tailor").version == "v4"


def test_v3_stays_registered_for_ab_comparison():
    # The old behaviour must remain pinnable via PROMPT_OVERRIDES.
    assert get_prompt("resume_tailor", version="v3").version == "v3"


def _flat(text: str) -> str:
    """Lowercased, whitespace-collapsed — the prompt is hard-wrapped."""
    return " ".join(text.lower().split())


def test_v4_forbids_inventing_a_summary():
    text = _flat(get_prompt("resume_tailor").text)
    assert "never invent a section the cv lacks" in text
    assert "never add a professional summary to a cv that doesn't have one" in text


def test_v4_drops_the_mandatory_section_list():
    # v3 enumerated "2. Professional Summary" as a required output section.
    v3 = get_prompt("resume_tailor", version="v3").text
    v4 = get_prompt("resume_tailor", version="v4").text
    assert "2. Professional Summary" in v3
    assert "2. Professional Summary" not in v4


def test_v4_bans_machine_written_summary_filler():
    text = _flat(get_prompt("resume_tailor").text)
    for tell in ("results-driven", "proven track record", "passionate about"):
        assert tell in text, tell


def test_v4_caps_the_summary_at_two_sentences():
    assert "2 sentences maximum" in get_prompt("resume_tailor").text


# --- the per-request human prompt --------------------------------------------

def test_human_prompt_tells_the_model_to_mirror_cv_sections(jd, match):
    agent = ResumeTailorAgent.__new__(ResumeTailorAgent)  # no LLM client needed
    prompt = agent._build_tailor_prompt(jd, match, master_cv=_CV_NO_SUMMARY)
    assert "Mirror the CV's sections" in prompt
    assert "do NOT write one" in prompt


def test_human_prompt_numbers_its_rules_uniquely(jd, match):
    # v3's instruction block had two rules labelled "3.", so the length rule and the
    # closing rule were mis-numbered. Every leading number must appear once.
    agent = ResumeTailorAgent.__new__(ResumeTailorAgent)
    prompt = agent._build_tailor_prompt(jd, match, master_cv=_CV_NO_SUMMARY)
    body = prompt.split("## Instructions", 1)[1]
    numbers = [
        line.split(".", 1)[0].strip()
        for line in body.splitlines()
        if line[:2].strip().isdigit() and "." in line[:3]
    ]
    assert numbers == sorted(numbers, key=int)
    assert len(numbers) == len(set(numbers)), numbers


@pytest.mark.parametrize("style", sorted(_STYLE_RULES))
def test_style_rules_treat_the_summary_as_conditional(style):
    assert "only if" in _STYLE_RULES[style].lower()
