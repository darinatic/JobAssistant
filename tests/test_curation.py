"""Gazetteer curation: reject rules + safe source editing.

The gazetteer's precision is what makes the deterministic matcher trustworthy, so
these guard the two ways curation could damage it: letting soft skills in, and
corrupting the hand-maintained SKILLS source.
"""

import pytest

from src.matching.curation import add_alias, add_canonical, auto_reject, has_canonical

_SOURCE = '''"""Docstring."""

import re

SKILLS: dict[str, list[str]] = {
    # --- Languages ---
    "Python": ["py"],
    "Java": [],
    "Go": ["golang"],
    # --- Cloud ---
    "Kubernetes": ["k8s", "kube"],
}

_OTHER = 1
'''


# --- deterministic rejects ---------------------------------------------------

@pytest.mark.parametrize("candidate", [
    "Collaboration",
    "Initiative",
    "Problem-solving",
    "Curiosity about emerging AI technologies",
    "AI fluency",
    "Stakeholder communication",
    "Fast-paced startup environment",
    "Enterprise SaaS platforms",
    "Cross-functional teamwork",
])
def test_soft_skills_and_workplace_phrases_are_auto_rejected(candidate):
    assert auto_reject(candidate) is not None, candidate


@pytest.mark.parametrize("candidate", [
    "Azure OpenAI",
    "Azure Kubernetes Service (AKS)",
    "GitHub",
    "Data engineering",
    "Cloud-native architecture",
    "Generative AI APIs",
    "Full-stack development",
])
def test_real_technical_candidates_are_left_for_review(candidate):
    # The pre-filter must be conservative: anything plausibly technical goes to the
    # LLM proposal and then to a human, never straight to the bin.
    assert auto_reject(candidate) is None, candidate


def test_empty_candidate_is_rejected():
    assert auto_reject("   ") == "empty"


# --- adding an alias to an existing canonical --------------------------------

def test_add_alias_appends_to_the_existing_list():
    out = add_alias(_SOURCE, "Kubernetes", "Azure Kubernetes Service (AKS)")
    assert '"Kubernetes": ["k8s", "kube", "azure kubernetes service (aks)"],' in out


def test_add_alias_lowercases():
    out = add_alias(_SOURCE, "Python", "PyPI")
    assert '"Python": ["py", "pypi"],' in out


def test_add_alias_to_an_empty_alias_list():
    out = add_alias(_SOURCE, "Java", "jvm")
    assert '"Java": ["jvm"],' in out


def test_add_alias_is_idempotent():
    once = add_alias(_SOURCE, "Kubernetes", "k8s")
    assert once == _SOURCE
    twice = add_alias(add_alias(_SOURCE, "Python", "pypi"), "Python", "pypi")
    assert twice == add_alias(_SOURCE, "Python", "pypi")


def test_add_alias_ignores_an_alias_equal_to_the_canonical():
    assert add_alias(_SOURCE, "Python", "python") == _SOURCE


def test_add_alias_rejects_an_unknown_canonical():
    with pytest.raises(KeyError):
        add_alias(_SOURCE, "Fortran", "f77")


def test_add_alias_leaves_other_entries_untouched():
    out = add_alias(_SOURCE, "Python", "pypi")
    assert '"Go": ["golang"],' in out
    assert '"Kubernetes": ["k8s", "kube"],' in out
    assert "_OTHER = 1" in out


# --- adding a new canonical --------------------------------------------------

def test_add_canonical_appends_under_a_named_section():
    out = add_canonical(_SOURCE, "Azure OpenAI", ["azure oai"], section="curated 2026-08-13")
    assert "# --- curated 2026-08-13 ---" in out
    assert '"Azure OpenAI": ["azure oai"],' in out


def test_add_canonical_stays_inside_the_dict():
    out = add_canonical(_SOURCE, "Data Engineering", [], section="curated")
    dict_end = out.index("\n}\n")
    assert out.index('"Data Engineering"') < dict_end


def test_add_canonical_is_idempotent():
    once = add_canonical(_SOURCE, "Azure OpenAI", [], section="curated")
    assert add_canonical(once, "Azure OpenAI", [], section="curated") == once


def test_add_canonical_drops_an_alias_equal_to_the_canonical():
    out = add_canonical(_SOURCE, "Helm", ["helm"], section="curated")
    assert '"Helm": [],' in out


def test_add_canonical_dedupes_and_lowercases_aliases():
    out = add_canonical(
        _SOURCE, "Kubernetes Service", ["AKS", "aks", "eks"], section="curated"
    )
    assert '"Kubernetes Service": ["aks", "eks"],' in out


def test_add_canonical_drops_aliases_that_only_repeat_the_canonical():
    # The matcher always matches a canonical's own lowercased form, so repeating it
    # as an alias is dead weight.
    out = add_canonical(_SOURCE, "AKS", ["aks", "AKS"], section="curated")
    assert '"AKS": [],' in out


def test_has_canonical():
    assert has_canonical(_SOURCE, "Python")
    assert not has_canonical(_SOURCE, "Fortran")


# --- the edited source must still be valid, importable Python ----------------

def test_edited_source_still_parses_and_keeps_every_entry():
    import ast

    out = add_alias(_SOURCE, "Kubernetes", "aks")
    out = add_canonical(out, "Azure OpenAI", ["azure oai"], section="curated")
    tree = ast.parse(out)  # must remain syntactically valid

    skills = next(
        node.value for node in ast.walk(tree)
        if isinstance(node, ast.AnnAssign) and getattr(node.target, "id", "") == "SKILLS"
    )
    parsed = ast.literal_eval(skills)
    assert parsed["Kubernetes"] == ["k8s", "kube", "aks"]
    assert parsed["Azure OpenAI"] == ["azure oai"]
    assert set(parsed) == {"Python", "Java", "Go", "Kubernetes", "Azure OpenAI"}


# --- ambiguous single-word canonicals ----------------------------------------
# A false skill match is the one failure this taxonomy exists to prevent, and the
# cheapest way to cause one is a product name that is also an English word.

@pytest.mark.parametrize("name", ["Cursor", "Hive", "Impala", "Oracle", "Spark", "Pandas"])
def test_ambiguous_single_word_canonicals_are_flagged(name):
    from src.matching.curation import needs_disambiguation

    assert needs_disambiguation(name) is not None, name


@pytest.mark.parametrize("name", [
    "Informatica", "CrewAI", "Kubernetes", "Teradata", "PyTorch", "n8n",
    "Azure OpenAI", "Model Context Protocol", "MS Access",
])
def test_specific_names_are_not_flagged(name):
    from src.matching.curation import needs_disambiguation

    assert needs_disambiguation(name) is None, name


def test_multi_word_names_are_never_flagged():
    from src.matching.curation import needs_disambiguation

    # "Apache Hive" is unambiguous even though "Hive" alone is not.
    assert needs_disambiguation("Apache Hive") is None
