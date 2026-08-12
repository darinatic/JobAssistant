"""Provider-agnostic chat-model factory (src/llm.py).

All offline: assertions are on the objects the factory constructs, never a call.
"""

import pytest
from langchain_core.messages import HumanMessage
from langchain_core.runnables import RunnableWithFallbacks

from src import llm
from src.llm import LLMConfigError, chat_model, model_for
from src.utils.config import settings


@pytest.fixture(autouse=True)
def _no_fallback(monkeypatch):
    """Most tests want the plain (unwrapped) model."""
    monkeypatch.setattr(settings, "llm_fallback_model", "", raising=False)


# --- role resolution ---------------------------------------------------------

def test_roles_default_to_the_anthropic_model_settings(monkeypatch):
    # Back-compat: a deployment that sets only ANTHROPIC_*_MODEL (as prod does)
    # must keep working with no new env vars.
    monkeypatch.setattr(settings, "llm_fast_model", "", raising=False)
    monkeypatch.setattr(settings, "llm_smart_model", "", raising=False)
    monkeypatch.setattr(settings, "anthropic_haiku_model", "claude-haiku-test")
    monkeypatch.setattr(settings, "anthropic_sonnet_model", "claude-sonnet-test")

    assert model_for("fast") == "anthropic:claude-haiku-test"
    assert model_for("smart") == "anthropic:claude-sonnet-test"


def test_explicit_role_config_wins(monkeypatch):
    monkeypatch.setattr(settings, "llm_fast_model", "openai:gpt-4o-mini", raising=False)
    assert model_for("fast") == "openai:gpt-4o-mini"


def test_split_handles_prefixed_and_bare_specs():
    assert llm._split("anthropic:claude-x") == ("anthropic", "claude-x")
    assert llm._split("gpt-4o") == ("", "gpt-4o")


# --- construction ------------------------------------------------------------

def test_builds_the_configured_anthropic_model(monkeypatch):
    monkeypatch.setattr(settings, "llm_fast_model", "anthropic:claude-haiku-4-5-20251001", raising=False)
    model = chat_model("fast", max_tokens=512, temperature=0)
    assert type(model).__name__ == "ChatAnthropic"
    assert model.model == "claude-haiku-4-5-20251001"
    assert model.max_tokens == 512


def test_override_pins_a_specific_model(monkeypatch):
    monkeypatch.setattr(settings, "llm_fast_model", "anthropic:claude-haiku-4-5-20251001", raising=False)
    model = chat_model("fast", override="anthropic:claude-sonnet-4-5-20250929", max_tokens=64)
    assert model.model == "claude-sonnet-4-5-20250929"


def test_api_key_is_passed_explicitly_not_left_to_the_environment():
    # pydantic-settings reads .env WITHOUT populating os.environ, so a provider SDK
    # reading its own env var would find nothing. The factory must pass the key.
    assert llm._api_key_kwargs("anthropic") == {
        "api_key": settings.anthropic_api_key.get_secret_value()
    }


def test_provider_without_a_configured_key_passes_no_key(monkeypatch):
    monkeypatch.setattr(settings, "google_api_key", None, raising=False)
    assert llm._api_key_kwargs("google_genai") == {}


def test_unknown_provider_is_not_given_a_key():
    assert llm._api_key_kwargs("some_future_vendor") == {}


def test_a_missing_provider_package_raises_a_config_error(monkeypatch):
    monkeypatch.setattr(settings, "llm_fast_model", "cohere:command-r", raising=False)
    with pytest.raises(LLMConfigError) as e:
        chat_model("fast", max_tokens=64)
    assert "cohere:command-r" in str(e.value)


# --- fallback ----------------------------------------------------------------

def test_no_fallback_configured_returns_the_plain_model(monkeypatch):
    monkeypatch.setattr(settings, "llm_fallback_model", "", raising=False)
    assert not isinstance(chat_model("fast", max_tokens=64), RunnableWithFallbacks)


def test_fallback_wraps_the_primary(monkeypatch):
    monkeypatch.setattr(settings, "llm_fast_model", "anthropic:claude-haiku-4-5-20251001", raising=False)
    monkeypatch.setattr(settings, "llm_fallback_model", "anthropic:claude-sonnet-4-5-20250929", raising=False)
    model = chat_model("fast", max_tokens=64)
    assert isinstance(model, RunnableWithFallbacks)
    assert len(model.fallbacks) == 1


def test_fallback_identical_to_primary_is_skipped(monkeypatch):
    same = "anthropic:claude-haiku-4-5-20251001"
    monkeypatch.setattr(settings, "llm_fast_model", same, raising=False)
    monkeypatch.setattr(settings, "llm_fallback_model", same, raising=False)
    assert not isinstance(chat_model("fast", max_tokens=64), RunnableWithFallbacks)


def test_a_broken_fallback_never_takes_down_a_working_primary(monkeypatch):
    monkeypatch.setattr(settings, "llm_fast_model", "anthropic:claude-haiku-4-5-20251001", raising=False)
    monkeypatch.setattr(settings, "llm_fallback_model", "cohere:command-r", raising=False)
    model = chat_model("fast", max_tokens=64)
    assert not isinstance(model, RunnableWithFallbacks)
    assert model.model == "claude-haiku-4-5-20251001"


# --- multimodal portability --------------------------------------------------

def _anthropic_payload(content: list) -> list:
    from langchain_anthropic.chat_models import _format_messages

    return _format_messages([HumanMessage(content=content)])[1]


def test_standard_file_block_matches_the_previous_anthropic_document_block():
    # The OCR path swapped a provider-native block for langchain's standard one so it
    # follows whichever provider the role points at. On Anthropic it must be a no-op.
    b64 = "JVBERi0xLjQK"
    native = [{"type": "document", "source": {"type": "base64", "media_type": "application/pdf", "data": b64}}]
    standard = [{"type": "file", "base64": b64, "mime_type": "application/pdf", "filename": "resume.pdf"}]
    assert _anthropic_payload(standard) == _anthropic_payload(native)


def test_standard_image_block_matches_the_previous_anthropic_image_block():
    b64 = "iVBORw0KGgo="
    native = [{"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": b64}}]
    standard = [{"type": "image", "base64": b64, "mime_type": "image/png"}]
    assert _anthropic_payload(standard) == _anthropic_payload(native)
