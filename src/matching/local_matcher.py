"""Deterministic local job↔CV scorer (P1).

Produces a full :class:`SkillMatch` — the same shape the Haiku scorer returned —
so it drops into the existing endpoints, discovery agent, and UI unchanged. No
LLM call: scoring is exact skill-overlap over the gazetteer, with a substring
fallback (reused from the existing heuristic) for skills outside the gazetteer.

Also exposes :func:`gap_analysis`, which splits a JD's skills into two honesty
buckets that the tailoring phase must treat differently:
- ``surfaceable_skills`` — named by the JD AND present in the master CV → honest
  to feature as keywords (you can back them up).
- ``genuine_gaps`` — named by the JD but absent from the master CV entirely → must
  NEVER be injected into the resume (that is fabrication); these feed the learning
  / skill-gap path.
"""

import logging
from dataclasses import dataclass, field

from src.agents.schemas import MatchRecommendation, ParsedJobDescription, SkillMatch
from src.agents.skills_matcher import _skill_appears_in_cv
from src.matching.gazetteer import canonicalize, extract_skills

log = logging.getLogger(__name__)


def _has_skill(skill: str, cv_canon: set[str], cv_lower: str) -> bool:
    """True if the CV demonstrates ``skill`` — via the gazetteer or a substring fallback."""
    canon = canonicalize(skill)
    if canon and canon in cv_canon:
        return True
    return _skill_appears_in_cv(skill, cv_lower)


def _recommendation(score: int) -> MatchRecommendation:
    if score >= 60:
        return MatchRecommendation.APPLY
    if score >= 40:
        return MatchRecommendation.STRETCH
    return MatchRecommendation.SKIP


def match_local(parsed_jd: ParsedJobDescription, master_cv: str) -> SkillMatch:
    """Score a candidate↔job match deterministically, with no LLM call.

    Flat scoring over the JD's skills (required + preferred pooled equally): the
    score is the % of the job's skills the CV covers, so it equals the search-card
    relevance for the same skill set. In the live app the JD's skills come from the
    gazetteer (see :func:`reconcile_jd_skills`), so search and tailor stay aligned.
    """
    cv_lower = master_cv.lower()
    cv_canon = extract_skills(master_cv)

    matched_req = [s for s in parsed_jd.required_skills if _has_skill(s, cv_canon, cv_lower)]
    missing_req = [s for s in parsed_jd.required_skills if s not in matched_req]
    matched_pref = [s for s in parsed_jd.preferred_skills if _has_skill(s, cv_canon, cv_lower)]
    missing_pref = [s for s in parsed_jd.preferred_skills if s not in matched_pref]

    total = max(1, len(parsed_jd.required_skills) + len(parsed_jd.preferred_skills))
    matched_count = len(matched_req) + len(matched_pref)
    score = round(100 * matched_count / total)

    # Transferable: skills the candidate genuinely has that the JD names in its
    # tech stack (or preferred) but not among required — a soft "adjacent" signal.
    jd_context_canon = {c for c in (canonicalize(t) for t in parsed_jd.tech_stack) if c}
    matched_canon = {c for c in (canonicalize(s) for s in matched_req + matched_pref) if c}
    transferable = sorted((cv_canon & jd_context_canon) - matched_canon)[:8]

    reasoning = (
        f"{matched_count}/{total} of the job's skills matched (deterministic gazetteer match)."
    )

    return SkillMatch(
        overall_score=score,
        matched_required=matched_req,
        matched_preferred=matched_pref,
        missing_required=missing_req,
        missing_preferred=missing_pref,
        transferable_skills=transferable,
        recommendation=_recommendation(score),
        reasoning=reasoning,
    )


def rough_relevance(jd_text: str, master_cv: str) -> int:
    """Cheap 0-100 relevance for a *raw* JD (no LLM parse) — the % of skills the
    gazetteer finds in the JD that the CV also has. Used to rank search results."""
    jd_skills = extract_skills(jd_text)
    if not jd_skills:
        return 0
    cv_skills = extract_skills(master_cv)
    return round(100 * len(jd_skills & cv_skills) / len(jd_skills))


def reconcile_jd_skills(parsed_jd: ParsedJobDescription, jd_text: str) -> None:
    """Make the gazetteer the single source of the JD's skills, so search and
    tailoring agree on the same set (and the tailor stops surfacing Haiku's noisy
    soft-skill phrases).

    Haiku still parses the JD's *structure* (title, company, seniority,
    responsibilities); this replaces its free-form skill lists with the
    deterministic gazetteer over the same text. Any skill Haiku named that the
    gazetteer doesn't recognize is logged as a growth candidate — the seed for a
    future curation pipeline that feeds new entries into the taxonomy. Mutates
    ``parsed_jd`` in place.
    """
    haiku_skills = list(dict.fromkeys(
        parsed_jd.required_skills + parsed_jd.preferred_skills + parsed_jd.tech_stack
    ))
    candidates = [s for s in haiku_skills if canonicalize(s) is None]
    if candidates:
        log.info("gazetteer_growth_candidates title=%r candidates=%s", parsed_jd.title, candidates)

    parsed_jd.required_skills = sorted(extract_skills(f"{parsed_jd.title}\n{jd_text}"))
    parsed_jd.preferred_skills = []
    parsed_jd.tech_stack = []
    parsed_jd.keywords_for_resume = []


@dataclass
class GapAnalysis:
    """The honesty split for tailoring (see module docstring)."""

    surfaceable_skills: list[str] = field(default_factory=list)  # JD skill you have (in CV) → honest to feature
    genuine_gaps: list[str] = field(default_factory=list)        # JD skill you lack → learning path, never inject


def gap_analysis(parsed_jd: ParsedJobDescription, master_cv: str) -> GapAnalysis:
    """Partition the JD's skills by presence in the master CV.

    Every JD skill lands in exactly one bucket: ``surfaceable_skills`` if the
    master CV demonstrates it (honest to feature as a keyword), else
    ``genuine_gaps`` (never inject — that would be fabrication). Independent of any
    tailored draft; the client decides which are currently in the Skills line.
    """
    master_lower = master_cv.lower()
    master_canon = extract_skills(master_cv)

    jd_skills = list(dict.fromkeys(parsed_jd.required_skills + parsed_jd.preferred_skills))

    result = GapAnalysis()
    for skill in jd_skills:
        if _has_skill(skill, master_canon, master_lower):
            result.surfaceable_skills.append(skill)
        else:
            result.genuine_gaps.append(skill)
    return result
