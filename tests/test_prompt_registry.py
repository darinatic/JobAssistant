"""Prompt resolution: LangSmith Hub (when configured) with in-repo registry fallback."""

from src.prompts import registry
from src.prompts.registry import Prompt, register, get_prompt
from src.utils.config import settings


def test_registry_serves_when_hub_returns_none(monkeypatch):
    register(Prompt(name="t_reg", version="v1", text="registry text"), latest=True)
    monkeypatch.setattr(registry, "_hub_prompt", lambda name: None)
    assert get_prompt("t_reg").text == "registry text"


def test_hub_prompt_preferred_when_available(monkeypatch):
    register(Prompt(name="t_hub", version="v1", text="registry text"), latest=True)
    monkeypatch.setattr(
        registry, "_hub_prompt",
        lambda name: Prompt(name=name, version="hub:me/x", text="hub text", notes="hub"),
    )
    p = get_prompt("t_hub")
    assert p.text == "hub text"
    assert p.version == "hub:me/x"


def test_explicit_version_bypasses_hub(monkeypatch):
    register(Prompt(name="t_exp", version="v1", text="v1 text"), latest=True)

    def _boom(name):
        raise AssertionError("hub must not be consulted for an explicit version")

    monkeypatch.setattr(registry, "_hub_prompt", _boom)
    assert get_prompt("t_exp", version="v1").text == "v1 text"


def test_hub_prompt_is_noop_when_tracing_off(monkeypatch):
    monkeypatch.setattr(settings, "langsmith_tracing", False)
    assert registry._hub_prompt("resume_tailor") is None


def test_extract_prompt_text_handles_both_template_shapes():
    class _PromptTemplate:
        template = "hello {x}"

    assert registry._extract_prompt_text(_PromptTemplate()) == "hello {x}"

    class _Msg:
        class prompt:
            template = "system prompt text"

    class _ChatTemplate:
        messages = [_Msg()]

    assert registry._extract_prompt_text(_ChatTemplate()) == "system prompt text"
    assert registry._extract_prompt_text(object()) == ""
