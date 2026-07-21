"""Skill-overlap helpers.

The nuanced scorer moved to the deterministic local matcher (`src/matching`);
what remains here is the synonym-aware substring check that the matcher reuses
as a fallback for skills outside the gazetteer.
"""

import re

# Common skill-name normalizations so matching handles obvious synonyms.
_SYNONYMS = {
    "llm": ["large language model", "llms", "gpt", "claude", "openai"],
    "rag": ["retrieval augmented generation", "retrieval-augmented"],
    "aws": ["amazon web services"],
    "gcp": ["google cloud", "google cloud platform"],
    "azure": ["microsoft azure"],
    "k8s": ["kubernetes"],
    "ci/cd": ["cicd", "continuous integration"],
    "fastapi": ["fast api"],
    "sql": ["postgres", "postgresql", "mysql"],
    "ml": ["machine learning"],
    "ai": ["artificial intelligence"],
    "tf": ["tensorflow"],
    "torch": ["pytorch"],
}


def _normalize_skill(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", s.lower())


def _skill_appears_in_cv(skill: str, cv_lower: str) -> bool:
    """True if skill (or any known synonym) appears in the (lower-cased) CV."""
    norm = _normalize_skill(skill)
    if norm and norm in re.sub(r"[^a-z0-9]+", "", cv_lower):
        return True
    if re.search(rf"\b{re.escape(skill.lower())}\b", cv_lower):
        return True
    for canonical, alts in _SYNONYMS.items():
        if norm == canonical or norm in [_normalize_skill(a) for a in alts]:
            for variant in [canonical, *alts]:
                if re.search(rf"\b{re.escape(variant)}\b", cv_lower):
                    return True
    return False
