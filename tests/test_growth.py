"""Tests for gazetteer-growth persistence (src/growth.py).

Offline — no real Supabase call. Covers the two behaviours that matter for safety:
it's a no-op when unconfigured, and it fails open (never raises) on any error.
"""

import pytest
from pydantic import SecretStr

import src.growth as growth


async def test_record_candidates_noop_when_unconfigured(monkeypatch):
    monkeypatch.setattr(growth.settings, "supabase_url", None)
    monkeypatch.setattr(growth.settings, "supabase_service_role_key", None)

    def explode(*a, **k):
        raise AssertionError("must not touch the network when unconfigured")

    monkeypatch.setattr(growth.httpx, "AsyncClient", explode)
    await growth.record_candidates(["Foo"], "Title")  # no-op, no raise


async def test_record_candidates_noop_on_empty(monkeypatch):
    monkeypatch.setattr(growth.settings, "supabase_url", "https://x.supabase.co")
    monkeypatch.setattr(growth.settings, "supabase_service_role_key", SecretStr("k"))

    def explode(*a, **k):
        raise AssertionError("must not touch the network for an empty candidate list")

    monkeypatch.setattr(growth.httpx, "AsyncClient", explode)
    await growth.record_candidates([], "Title")


async def test_record_candidates_fails_open(monkeypatch):
    monkeypatch.setattr(growth.settings, "supabase_url", "https://x.supabase.co")
    monkeypatch.setattr(growth.settings, "supabase_service_role_key", SecretStr("k"))

    def boom(*a, **k):
        raise RuntimeError("supabase down")

    monkeypatch.setattr(growth.httpx, "AsyncClient", boom)
    await growth.record_candidates(["Foo"], "Title")  # swallowed, never raises


async def test_unreachable_supabase_logs_one_line_without_a_traceback(monkeypatch, caplog):
    """An unreachable Supabase is expected (paused project, offline dev box).

    Dumping a full stack trace for best-effort telemetry made a working tailor look
    like a crashed one — it was the only traceback in the log, so it read as the cause.
    """
    import httpx

    monkeypatch.setattr(growth.settings, "supabase_url", "https://x.supabase.co")
    monkeypatch.setattr(growth.settings, "supabase_service_role_key", SecretStr("k"))

    def unreachable(*a, **k):
        raise httpx.ConnectError("[Errno 11001] getaddrinfo failed")

    monkeypatch.setattr(growth.httpx, "AsyncClient", unreachable)
    with caplog.at_level("WARNING"):
        await growth.record_candidates(["Foo"], "Title")

    assert len(caplog.records) == 1
    assert caplog.records[0].exc_info is None, "network errors must not log a traceback"
    assert "unavailable" in caplog.records[0].getMessage()


async def test_an_unexpected_failure_still_logs_a_traceback(monkeypatch, caplog):
    # A real misconfiguration (bad key, missing RPC) is worth the full trace.
    monkeypatch.setattr(growth.settings, "supabase_url", "https://x.supabase.co")
    monkeypatch.setattr(growth.settings, "supabase_service_role_key", SecretStr("k"))

    def boom(*a, **k):
        raise RuntimeError("unexpected")

    monkeypatch.setattr(growth.httpx, "AsyncClient", boom)
    with caplog.at_level("WARNING"):
        await growth.record_candidates(["Foo"], "Title")

    assert caplog.records[0].exc_info is not None


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
