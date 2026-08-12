"""Provider-agnostic chat-model factory.

Every LLM call in the app goes through :func:`chat_model`. Call sites ask for a
**role** (``"fast"`` or ``"smart"``), never a vendor or a model name — the prompts
are tuned to a capability tier, not to Claude. Which model backs each role is a
config string of the form ``"provider:model"`` resolved by langchain's
``init_chat_model``, so changing provider is an env change:

    LLM_SMART_MODEL=openai:gpt-4o
    LLM_FAST_MODEL=google_genai:gemini-2.0-flash
    LLM_FAST_MODEL=ollama:llama3.1

Defaults derive from the existing ``ANTHROPIC_*_MODEL`` settings, so a deployment
that sets nothing new keeps its current behaviour exactly.

**Structured output.** Five of the six call sites use ``with_structured_output``.
That is langchain's own abstraction and it already picks the right per-provider
strategy (tool calling vs JSON mode), so we deliberately do NOT wrap it — a bespoke
layer on top is the part that would rot. The practical consequence is that a
provider without tool-calling support (many small local models) will fail at those
call sites; that is a model-choice constraint, not something this module can hide.

**Multimodal.** The OCR path sends standard langchain content blocks
(``{"type": "file", "base64": ..., "mime_type": ...}``), which each integration
translates to its provider's native shape. See ``agents/resume_structurer.py``.
"""

from __future__ import annotations

import logging
from typing import Literal

from langchain.chat_models import init_chat_model
from langchain_core.language_models import BaseChatModel

from src.utils.config import settings

log = logging.getLogger("resumeagent.llm")

Role = Literal["fast", "smart"]

# provider prefix -> (settings attribute holding the key, kwarg the integration wants).
# Providers absent from this map are still usable; they just have to pick their key
# up from the ambient environment the way their SDK normally does.
_PROVIDER_KEYS: dict[str, tuple[str, str]] = {
    "anthropic": ("anthropic_api_key", "api_key"),
    "openai": ("openai_api_key", "api_key"),
    "azure_openai": ("openai_api_key", "api_key"),
    "google_genai": ("google_api_key", "google_api_key"),
}


class LLMConfigError(RuntimeError):
    """A role points at a provider whose package or API key is missing."""


def _split(spec: str) -> tuple[str, str]:
    """'anthropic:claude-x' -> ('anthropic', 'claude-x'). No prefix -> ('', spec)."""
    provider, sep, model = spec.partition(":")
    return (provider, model) if sep else ("", spec)


def _api_key_kwargs(provider: str) -> dict[str, object]:
    """Explicit key for `provider`, pulled from settings.

    Settings are loaded from .env by pydantic-settings, which does NOT populate
    os.environ — so a provider SDK looking for its own env var would not find a key
    that only exists in .env. Passing it explicitly closes that gap.
    """
    entry = _PROVIDER_KEYS.get(provider)
    if not entry:
        return {}
    attr, kwarg = entry
    secret = getattr(settings, attr, None)
    if secret is None:
        return {}
    return {kwarg: secret.get_secret_value()}


def model_for(role: Role) -> str:
    """The effective ``provider:model`` string backing `role`."""
    return settings.smart_model if role == "smart" else settings.fast_model


def _build(spec: str, **kwargs: object) -> BaseChatModel:
    provider, model = _split(spec)
    try:
        return init_chat_model(
            model,
            model_provider=provider or None,
            **_api_key_kwargs(provider),
            **kwargs,
        )
    except ImportError as e:
        raise LLMConfigError(
            f"Model {spec!r} needs a provider package that isn't installed. "
            f"Install the extras: pip install -e '.[providers]'  ({e})"
        ) from e
    except Exception as e:  # noqa: BLE001 — surface any init failure as config error
        raise LLMConfigError(f"Could not initialise model {spec!r}: {e}") from e


def chat_model(role: Role, *, override: str | None = None, **kwargs: object) -> BaseChatModel:
    """A chat model for `role`, with the optional fallback chain attached.

    ``override`` pins an explicit ``"provider:model"`` (or a bare model name, which
    langchain infers a provider for), bypassing the role config — used by the agent
    constructors' ``model=`` argument.

    ``kwargs`` (``max_tokens``, ``temperature``, ...) are forwarded to the
    integration unchanged. Parameter names are largely but not perfectly uniform
    across providers, so an exotic provider may need its own call-site tuning.
    """
    spec = override or model_for(role)
    primary = _build(spec, **kwargs)

    fallback_spec = settings.llm_fallback_model
    if not fallback_spec or fallback_spec == spec:
        return primary

    try:
        fallback = _build(fallback_spec, **kwargs)
    except LLMConfigError as e:
        # A broken fallback must never take down a working primary.
        log.warning("Ignoring LLM_FALLBACK_MODEL %r: %s", fallback_spec, e)
        return primary

    log.info("LLM role=%s primary=%s fallback=%s", role, model_for(role), fallback_spec)
    return primary.with_fallbacks([fallback])
