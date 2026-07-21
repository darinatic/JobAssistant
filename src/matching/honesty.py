"""Deterministic honesty linter for tailored resumes.

Post-hoc check over ``(master_cv, tailored_markdown)`` that flags fabrication the
tailor prompt is supposed to prevent — no LLM, exact-repeatable, ~1ms.

**What counts as fabrication (and what doesn't).** Weaving the JD's skills into the
Skills section is the tailor's *job* — it's how the resume passes ATS keyword filters,
so an added skill is NOT flagged. Fabrication is inventing *history*: a role/project
that didn't happen, an achievement metric that wasn't earned, or a whole industry the
CV never touched. The three checks:

1. **entry**   — a role/project heading (``### ``) whose company/name isn't in the CV
                 (a made-up job or fictitious project to showcase a skill).
2. **metric**  — a number/percentage/quantity in the output that isn't in the CV.
3. **domain**  — an industry or compliance term in the output but not in the CV
                 (the classic "re-label the candidate's sector" fabrication).

Runtime safety net + eval gate. Deliberately conservative (favours false negatives
over crying wolf), so it only fires on clear invention.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# Industry sectors + compliance/regulatory frameworks — the terms a tailor might
# bolt on to imply sector experience the CV never claimed. Lowercased.
_DOMAIN_TERMS = frozenset({
    # industries
    "fintech", "financial services", "banking", "insurance", "healthtech",
    "healthcare", "clinical", "biotech", "pharmaceutical", "pharma", "govtech",
    "e-commerce", "ecommerce", "retail", "edtech", "legaltech", "proptech",
    "logistics", "telecom", "telecommunications", "cybersecurity", "defense",
    "aerospace", "automotive", "adtech", "martech", "manufacturing",
    # compliance / regulatory frameworks
    "hipaa", "pdpa", "gdpr", "ccpa", "pci-dss", "pci dss", "soc 2", "soc2",
    "iso 27001", "fedramp", "sox", "glba", "ferpa", "nist",
})

# Percentages, k/M magnitudes, currency, and 3+ digit numbers — the "metric"
# surface. Small counts ("5 staff", "3 years") are deliberately ignored.
_PCT_RE = re.compile(r"\d+(?:\.\d+)?\s*%")
_MAG_RE = re.compile(r"\d+(?:\.\d+)?\s*[kmb]\b", re.IGNORECASE)
_MONEY_RE = re.compile(r"[$€£]\s?\d[\d,]*(?:\.\d+)?")
_BIGNUM_RE = re.compile(r"\d[\d,]{2,}")  # 100+, comma-formatted allowed


@dataclass(frozen=True)
class HonestyFinding:
    kind: str      # 'entry' | 'metric' | 'domain'
    value: str     # the offending token, as normalized
    detail: str    # human-readable explanation


@dataclass
class HonestyReport:
    findings: list[HonestyFinding] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.findings

    def of(self, kind: str) -> list[HonestyFinding]:
        return [f for f in self.findings if f.kind == kind]

    def as_dicts(self) -> list[dict]:
        return [{"kind": f.kind, "value": f.value, "detail": f.detail} for f in self.findings]


def _norm_metric(raw: str) -> str:
    """Normalize a metric token so '10k', '10,000' and '10000' compare equal."""
    s = raw.strip().lower().replace(",", "").replace(" ", "")
    m = re.fullmatch(r"(\d+(?:\.\d+)?)([kmb])", s)
    if m:
        mult = {"k": 1_000, "m": 1_000_000, "b": 1_000_000_000}[m.group(2)]
        return str(int(float(m.group(1)) * mult))
    if s.endswith("%"):
        return s
    return s.lstrip("$€£")


def _metrics(text: str) -> set[str]:
    out: set[str] = set()
    for rx in (_PCT_RE, _MAG_RE, _MONEY_RE, _BIGNUM_RE):
        for hit in rx.findall(text):
            out.add(_norm_metric(hit))
    return out


def _domains(text: str) -> set[str]:
    low = text.lower()
    found: set[str] = set()
    for term in _DOMAIN_TERMS:
        if re.search(r"(?<![a-z])" + re.escape(term) + r"(?![a-z])", low):
            found.add(term)
    return found


# Generic role/degree words that carry no identity — a shared "Engineer" between two
# headings doesn't mean it's the same job. The anchor is the company/project name.
_ENTRY_STOPWORDS = frozenset({
    "engineer", "engineering", "developer", "development", "senior", "junior", "lead",
    "principal", "staff", "manager", "management", "director", "analyst", "scientist",
    "specialist", "consultant", "architect", "intern", "internship", "freelance",
    "project", "projects", "experience", "education", "certifications", "summary",
    "skills", "university", "college", "school", "degree", "bachelor", "master",
    "present", "current", "remote", "contract", "full-time", "part-time",
})
_HEADER_RE = re.compile(r"^###\s+(.+)$", re.MULTILINE)
_WORD_RE = re.compile(r"[A-Za-z][A-Za-z0-9+.#&-]{2,}")


def _identity_words(header: str) -> set[str]:
    """Meaningful words in a heading — the company/project name, not the generic role."""
    stripped = re.sub(r"\(.*?\)", " ", header)  # drop (2022-2025)
    words = {w.lower() for w in _WORD_RE.findall(stripped)}
    return {w for w in words if len(w) >= 4 and w not in _ENTRY_STOPWORDS}


def _invented_entries(cv: str, output: str) -> list[str]:
    """Output role/project headings whose identity words appear NOWHERE in the CV —
    i.e. a job or project the CV never mentions. Conservative: needs zero overlap."""
    cv_low = cv.lower()
    flagged: list[str] = []
    for header in _HEADER_RE.findall(output):
        words = _identity_words(header)
        if words and not any(w in cv_low for w in words):
            flagged.append(header.strip())
    return flagged


def lint_resume(master_cv: str, tailored_md: str) -> HonestyReport:
    """Flag invented entries / metrics / domains in the tailored resume. Added skills
    are fine (that's the ATS value). Empty report ⇒ nothing invented (deterministically)."""
    report = HonestyReport()
    if not tailored_md or not master_cv:
        return report

    for entry in _invented_entries(master_cv, tailored_md):
        short = entry if len(entry) <= 60 else entry[:57] + "…"
        report.findings.append(HonestyFinding(
            "entry", short, f"'{short}' looks like a role/project not in your CV — did the tailor invent it?",
        ))

    cv_metrics = _metrics(master_cv)
    for metric in sorted(_metrics(tailored_md) - cv_metrics):
        report.findings.append(HonestyFinding(
            "metric", metric, f"The figure '{metric}' isn't in your CV — verify it wasn't invented.",
        ))

    cv_domains = _domains(master_cv)
    for domain in sorted(_domains(tailored_md) - cv_domains):
        report.findings.append(HonestyFinding(
            "domain", domain, f"'{domain}' implies sector experience your CV doesn't state.",
        ))

    return report
