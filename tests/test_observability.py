"""Optional LangSmith tracing wiring — off by default, PII-redacted when on."""

import os

from pydantic import SecretStr

from src import observability
from src.utils.config import settings

_KEYS = (
    "LANGSMITH_TRACING", "LANGSMITH_API_KEY", "LANGSMITH_PROJECT",
    "LANGSMITH_HIDE_INPUTS", "LANGSMITH_HIDE_OUTPUTS",
    "LANGCHAIN_HIDE_INPUTS", "LANGCHAIN_HIDE_OUTPUTS",
)


def _isolate_env(monkeypatch):
    # delenv records the original and restores it at teardown, even if the code
    # under test re-adds the key — so nothing leaks into other tests.
    for k in _KEYS:
        monkeypatch.delenv(k, raising=False)


def test_disabled_is_a_pure_noop(monkeypatch):
    _isolate_env(monkeypatch)
    monkeypatch.setattr(settings, "langsmith_tracing", False)
    assert observability.configure_langsmith() is False
    assert "LANGSMITH_TRACING" not in os.environ


def test_tracing_flag_without_key_stays_off(monkeypatch):
    _isolate_env(monkeypatch)
    monkeypatch.setattr(settings, "langsmith_tracing", True)
    monkeypatch.setattr(settings, "langsmith_api_key", None)
    assert observability.configure_langsmith() is False
    assert "LANGSMITH_TRACING" not in os.environ


def test_enabled_sets_env_and_redacts_payloads(monkeypatch):
    _isolate_env(monkeypatch)
    monkeypatch.setattr(settings, "langsmith_tracing", True)
    monkeypatch.setattr(settings, "langsmith_api_key", SecretStr("ls-key"))
    monkeypatch.setattr(settings, "langsmith_project", "test-proj")
    monkeypatch.setattr(settings, "langsmith_hide_io", True)

    assert observability.configure_langsmith() is True
    assert os.environ["LANGSMITH_TRACING"] == "true"
    assert os.environ["LANGSMITH_API_KEY"] == "ls-key"
    assert os.environ["LANGSMITH_PROJECT"] == "test-proj"
    # payloads redacted under both env-name variants
    assert os.environ["LANGSMITH_HIDE_INPUTS"] == "true"
    assert os.environ["LANGCHAIN_HIDE_OUTPUTS"] == "true"


def test_enabled_without_hide_io_keeps_payloads(monkeypatch):
    _isolate_env(monkeypatch)
    monkeypatch.setattr(settings, "langsmith_tracing", True)
    monkeypatch.setattr(settings, "langsmith_api_key", SecretStr("ls-key"))
    monkeypatch.setattr(settings, "langsmith_hide_io", False)

    assert observability.configure_langsmith() is True
    assert "LANGSMITH_HIDE_INPUTS" not in os.environ
