"""Local, deterministic job↔CV matching (P1).

Replaces the per-job Haiku scorer with a gazetteer-based skills matcher: same
input always yields the same score (the consistency the LLM couldn't give),
runs locally in <1ms, and costs nothing. See `local_matcher.match_local`.
"""

from src.matching.gazetteer import canonicalize, extract_skills
from src.matching.honesty import HonestyFinding, HonestyReport, lint_resume
from src.matching.local_matcher import (
    GapAnalysis,
    gap_analysis,
    match_local,
    rough_relevance,
)

__all__ = [
    "extract_skills",
    "canonicalize",
    "match_local",
    "gap_analysis",
    "GapAnalysis",
    "rough_relevance",
    "lint_resume",
    "HonestyReport",
    "HonestyFinding",
]
