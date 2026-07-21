"""Optional LangSmith tracing — env-driven, OFF by default.

When ``settings.langsmith_enabled`` is true, LangChain's built-in LangSmith
tracer activates from these env vars with no changes at the LLM call sites.
Prompt inputs/outputs (CV/JD text) are hidden from traces by default to preserve
the app's "nothing stored" stance — only trace structure, latency, tokens, model,
the resolved prompt version, and errors are captured.
"""

from __future__ import annotations

import logging
import os

from src.utils.config import settings

log = logging.getLogger("resumeagent.observability")


def configure_langsmith() -> bool:
    """Wire LangSmith tracing from settings. Returns True when enabled. Safe to
    call once at startup; a pure no-op (touches no env) when disabled."""
    if not settings.langsmith_enabled:
        return False

    os.environ["LANGSMITH_TRACING"] = "true"
    os.environ["LANGSMITH_API_KEY"] = settings.langsmith_api_key.get_secret_value()
    os.environ["LANGSMITH_PROJECT"] = settings.langsmith_project

    if settings.langsmith_hide_io:
        # Redact prompt payloads (CV/JD text). Set both the current LANGSMITH_* and
        # legacy LANGCHAIN_* env names so whichever the installed SDK honors wins —
        # never send raw candidate data off-box.
        for name in ("LANGSMITH_HIDE_INPUTS", "LANGSMITH_HIDE_OUTPUTS",
                     "LANGCHAIN_HIDE_INPUTS", "LANGCHAIN_HIDE_OUTPUTS"):
            os.environ[name] = "true"

    log.info("LangSmith tracing enabled (project=%s, hide_io=%s)",
             settings.langsmith_project, settings.langsmith_hide_io)
    return True
