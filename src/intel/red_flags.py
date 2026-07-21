"""Deterministic legitimacy red-flag scanner for the Intel panel.

No LLM, ~1ms, conservative (fires on clear evidence only). Modeled on
`src/matching/honesty.py`. Each flag cites a primary source (FTC / SPF / MOM /
ghost-job research). Advisory only — the panel never blocks on these.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

from src.intel.schemas import RedFlag

_PERSONAL_DOMAINS = ("gmail.com", "yahoo.com", "hotmail.com", "outlook.com",
                     "qq.com", "163.com", "protonmail.com", "gmx.com")
_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@([A-Za-z0-9.-]+\.[A-Za-z]{2,})")

# MOM Employment Agency licence, e.g. "EA Licence No. 12C3456" / "EA Reg No. R1234567".
_EA_RE = re.compile(r"EA\s*(?:Licence|License|Personnel\s*Reg(?:istration)?|Reg)\s*"
                    r"(?:No\.?|Number)?\s*[:.]?\s*([0-9A-Z]{5,10})", re.IGNORECASE)
_AGENCY_RE = re.compile(r"\b(on behalf of our client|our client(?=,|\s+(?:is|are)\b)|"
                        r"recruitment agency|staffing|head\s?hunt|"
                        r"talent acquisition partner|executive search)\b", re.IGNORECASE)


@dataclass
class AgencyInfo:
    agency_mediated: bool = False
    ea_licence: str = ""


def parse_agency(text: str) -> AgencyInfo:
    """Detect agency-mediated postings + any MOM EA licence cited on them."""
    text = text or ""
    ea = _EA_RE.search(text)
    ea_licence = ea.group(1) if ea else ""
    is_agency = bool(_AGENCY_RE.search(text)) or bool(ea_licence)
    return AgencyInfo(agency_mediated=is_agency, ea_licence=ea_licence)

_RULES = [
    ("upfront_payment", "warn", "FTC · SPF",
     r"\b(registration fee|training fee|processing fee|security deposit|"
     r"upfront payment|pay (?:a|the)? ?fee|pay to start|deposit to (?:start|earn))\b"),
    ("messaging_only", "high", "SPF",
     r"\b(whatsapp|telegram|wechat|wa\.me|t\.me)\b"),
    ("sensitive_data", "high", "SPF · MOM",
     r"\b(nric|fin number|bank account (?:details|number)|passport number|"
     r"ssn|social security number)\b"),
    ("urgency", "info", "FTC",
     r"\b(immediate start|start today|same[- ]day (?:offer|hire)|act now|"
     r"limited slots|apply urgently)\b"),
    ("too_good_salary", "warn", "FTC",
     r"\b(guaranteed income|lucrative returns|earn up to \$?\d[\d,]* (?:a|per) day|"
     r"high (?:pay|salary) no experience|minimal effort)\b"),
    ("evergreen", "info", "ghost-job research",
     r"\b(always hiring|always looking|talent pool|ongoing recruitment|"
     r"we are always|multiple positions available)\b"),
]

_STALE_DAYS = 60
_VAGUE_MIN_CHARS = 220
_MAX_SCAN_CHARS = 20_000


def _iso_or_none(s: str):
    try:
        return date.fromisoformat((s or "")[:10])
    except ValueError:
        return None


def scan_red_flags(job: dict, *, today: date | None = None) -> list[RedFlag]:
    today = today or date.today()
    text = (job.get("description") or "")[:_MAX_SCAN_CHARS]
    low = text.lower()
    flags: list[RedFlag] = []

    for code, severity, source, pattern in _RULES:
        m = re.search(pattern, low, re.IGNORECASE)
        if m:
            flags.append(RedFlag(code=code, label=code.replace("_", " "),
                                 severity=severity, evidence=m.group(0), source=source))

    # personal-email-domain contact
    for m in _EMAIL_RE.finditer(text):
        if m.group(1).lower() in _PERSONAL_DOMAINS:
            flags.append(RedFlag(code="personal_email", label="personal email contact",
                                 severity="warn", evidence=m.group(0), source="FTC"))
            break

    # vague / thin JD (soft ghost/scam signal)
    stripped = text.strip()
    if 0 < len(stripped) < _VAGUE_MIN_CHARS:
        flags.append(RedFlag(code="vague_jd", label="very short / generic description",
                             severity="info", evidence=f"{len(stripped)} chars",
                             source="FTC"))

    # stale posting
    posted = _iso_or_none(job.get("posted_date", ""))
    if posted and (today - posted).days > _STALE_DAYS:
        flags.append(RedFlag(code="stale_posting", label="posted over 60 days ago",
                             severity="info", evidence=job.get("posted_date", ""),
                             source="ghost-job research"))

    # unlicensed "agency"
    agency = parse_agency(text)
    if agency.agency_mediated and not agency.ea_licence:
        flags.append(RedFlag(code="unlicensed_agency",
                             label="recruiter with no MOM EA licence",
                             severity="warn", evidence="", source="MOM"))

    return flags
