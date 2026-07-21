"""Deterministic local job↔CV scorer (P1).

Produces a full :class:`SkillMatch` — the same shape the Haiku scorer returned —
so it drops into the existing endpoints, discovery agent, and UI unchanged. No
LLM call: scoring is exact skill-overlap over the gazetteer, with a substring
fallback (reused from the existing heuristic) for skills outside the gazetteer.

Also exposes :func:`gap_analysis`, which splits a JD's skills into two honesty
buckets that the tailoring phase must treat differently:
- ``surfaceable_skills`` — present in the master CV but missing from the current
  tailored resume → safe to suggest weaving in.
- ``genuine_gaps`` — absent from the master CV entirely → must NEVER be injected
  into the resume (that is fabrication); these feed the learning / skill-gap path.
"""

from dataclasses import dataclass, field

from src.agents.schemas import MatchRecommendation, ParsedJobDescription, SkillMatch
from src.agents.skills_matcher import _skill_appears_in_cv
from src.matching.gazetteer import canonicalize, extract_skills


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

    Weighting mirrors the previous heuristic/LLM prompt (60% required coverage,
    25% preferred, 15% baseline) so scores stay comparable across the migration.
    """
    cv_lower = master_cv.lower()
    cv_canon = extract_skills(master_cv)

    matched_req = [s for s in parsed_jd.required_skills if _has_skill(s, cv_canon, cv_lower)]
    missing_req = [s for s in parsed_jd.required_skills if s not in matched_req]
    matched_pref = [s for s in parsed_jd.preferred_skills if _has_skill(s, cv_canon, cv_lower)]
    missing_pref = [s for s in parsed_jd.preferred_skills if s not in matched_pref]

    req_total = max(1, len(parsed_jd.required_skills))
    req_ratio = len(matched_req) / req_total
    pref_ratio = (len(matched_pref) / len(parsed_jd.preferred_skills)) if parsed_jd.preferred_skills else 0.0

    score = max(0, min(100, int(round(60 * req_ratio + 25 * pref_ratio + 15))))

    # Transferable: skills the candidate genuinely has that the JD names in its
    # tech stack (or preferred) but not among required — a soft "adjacent" signal.
    jd_context_canon = {c for c in (canonicalize(t) for t in parsed_jd.tech_stack) if c}
    matched_canon = {c for c in (canonicalize(s) for s in matched_req + matched_pref) if c}
    transferable = sorted((cv_canon & jd_context_canon) - matched_canon)[:8]

    reasoning = (
        f"{len(matched_req)}/{len(parsed_jd.required_skills)} required and "
        f"{len(matched_pref)}/{len(parsed_jd.preferred_skills)} preferred skills matched "
        f"(deterministic gazetteer match)."
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


@dataclass
class GapAnalysis:
    """The honesty split for tailoring (see module docstring)."""

    surfaceable_skills: list[str] = field(default_factory=list)  # has it, not on resume → weave in
    genuine_gaps: list[str] = field(default_factory=list)        # lacks it → learning path, never inject


def gap_analysis(
    parsed_jd: ParsedJobDescription,
    master_cv: str,
    resume_md: str | None = None,
) -> GapAnalysis:
    """Split the JD's skills into surfaceable (real, underused) vs genuine gaps.

    ``resume_md`` is the *current tailored* resume; when omitted it defaults to
    the master CV, in which case ``surfaceable_skills`` is empty (nothing is
    hidden relative to the source of truth).
    """
    resume_text = resume_md if resume_md is not None else master_cv
    master_lower, resume_lower = master_cv.lower(), resume_text.lower()
    master_canon, resume_canon = extract_skills(master_cv), extract_skills(resume_text)

    jd_skills = list(dict.fromkeys(parsed_jd.required_skills + parsed_jd.preferred_skills))

    result = GapAnalysis()
    for skill in jd_skills:
        in_master = _has_skill(skill, master_canon, master_lower)
        in_resume = _has_skill(skill, resume_canon, resume_lower)
        if in_master and not in_resume:
            result.surfaceable_skills.append(skill)
        elif not in_master:
            result.genuine_gaps.append(skill)
    return result
