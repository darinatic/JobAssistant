"""Versioned prompt registry.

Every LLM-facing prompt in the app lives here, identified by ``name`` and
``version``. Agents resolve their active prompt via ``get_prompt(name)``.

Resolution order for the active prompt (when no explicit ``version`` is asked):
  1. **LangSmith Hub** — when tracing is enabled AND a hub ref is configured for
     the name (``LANGSMITH_PROMPT_REFS``), pull it so engineers can edit/version
     prompts in the LangSmith playground and have runtime pick them up. Any Hub
     failure falls through to the in-repo registry, so offline/prod-without-a-key
     never breaks.
  2. ``PROMPT_OVERRIDES`` env var, e.g. ``PROMPT_OVERRIDES=cover_letter=v1`` —
     A/B-testing a registered version without code changes.
  3. The version registered with ``latest=True``.

The in-repo registry stays the source of truth + offline fallback.
"""

from __future__ import annotations

import hashlib
import logging
import os
from dataclasses import dataclass, field
from typing import Optional

log = logging.getLogger("resumeagent.prompts")


@dataclass(frozen=True)
class Prompt:
    name: str
    version: str
    text: str
    tags: tuple[str, ...] = ()
    notes: str = ""  # one-line changelog explaining the version

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.text.encode("utf-8")).hexdigest()[:16]


# Internal: name → version → Prompt
_REGISTRY: dict[str, dict[str, Prompt]] = {}
# Internal: name → version  (the default if no override is set)
_LATEST: dict[str, str] = {}


def register(prompt: Prompt, *, latest: bool = False) -> Prompt:
    """Register a prompt version. If ``latest=True``, this version becomes the
    default returned by ``get_prompt(name)``. Multiple versions can be
    registered for the same ``name`` — only one is marked latest at a time."""
    versions = _REGISTRY.setdefault(prompt.name, {})
    versions[prompt.version] = prompt
    if latest:
        _LATEST[prompt.name] = prompt.version
    return prompt


def _parse_overrides() -> dict[str, str]:
    raw = os.environ.get("PROMPT_OVERRIDES", "")
    out: dict[str, str] = {}
    for item in raw.split(","):
        if "=" not in item:
            continue
        name, version = item.split("=", 1)
        name, version = name.strip(), version.strip()
        if name and version:
            out[name] = version
    return out


def _extract_prompt_text(obj) -> str:
    """Best-effort extraction of a system/template string from a pulled Hub prompt
    (ChatPromptTemplate or PromptTemplate). Returns '' when nothing usable found."""
    for msg in (getattr(obj, "messages", None) or []):
        tmpl = getattr(getattr(msg, "prompt", None), "template", None)
        if isinstance(tmpl, str) and tmpl.strip():
            return tmpl
    tmpl = getattr(obj, "template", None)
    return tmpl if isinstance(tmpl, str) and tmpl.strip() else ""


def _hub_prompt(name: str) -> Optional[Prompt]:
    """Pull a prompt from LangSmith Hub when tracing is on and a ref is configured
    for ``name``. Returns None (→ registry fallback) when disabled, unconfigured,
    or on ANY error — a Hub hiccup must never break tailoring."""
    from src.utils.config import settings
    if not settings.langsmith_enabled:
        return None
    ref = settings.langsmith_prompt_ref_map.get(name)
    if not ref:
        return None
    try:
        from langsmith import Client
        text = _extract_prompt_text(Client().pull_prompt(ref))
        if text:
            return Prompt(name=name, version=f"hub:{ref}", text=text,
                          notes="pulled from LangSmith Hub")
    except Exception as e:
        log.warning("LangSmith Hub pull failed for %r (%s) — using registry: %s", name, ref, e)
    return None


def get_prompt(name: str, *, version: Optional[str] = None) -> Prompt:
    """Resolve a prompt by name. Without ``version``, resolves in order: LangSmith
    Hub (when configured) → ``PROMPT_OVERRIDES`` env var → the ``latest=True``
    version. Raises ``KeyError`` if the name is unknown or no version is selected."""
    if version is None:
        hub = _hub_prompt(name)
        if hub is not None:
            return hub
        version = _parse_overrides().get(name) or _LATEST.get(name)
    if version is None:
        raise KeyError(f"No active version for prompt {name!r}")
    versions = _REGISTRY.get(name)
    if versions is None:
        raise KeyError(f"Unknown prompt name {name!r}")
    try:
        return versions[version]
    except KeyError as e:
        available = sorted(versions)
        raise KeyError(
            f"Prompt {name!r} has no version {version!r} — available: {available}"
        ) from e


def list_versions(name: str) -> list[str]:
    return sorted((_REGISTRY.get(name) or {}).keys())


def all_active() -> dict[str, Prompt]:
    """One Prompt per registered name, picking the currently-active version."""
    return {name: get_prompt(name) for name in _REGISTRY}
