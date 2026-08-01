"""PII guardrail layer — data minimization before third-party LLM calls.

Input guard  : ``anonymize`` strips direct identifiers (name/email/phone/URL) from
               the CV before it reaches Anthropic.
Output guard : ``restore_and_verify`` restores them locally and confirms the
               round-trip; ``lint_resume`` (re-exported) is the honesty output guard.

Everything fails open — a redaction error tailors on the real CV rather than breaking.
"""

from src.guardrails.output import lint_resume, restore_and_verify, summary_report
from src.guardrails.pii import Redaction, anonymize, restore
from src.guardrails.schemas import GuardrailReport, RedactionSummary

__all__ = [
    "anonymize",
    "restore",
    "restore_and_verify",
    "summary_report",
    "lint_resume",
    "Redaction",
    "GuardrailReport",
    "RedactionSummary",
]
