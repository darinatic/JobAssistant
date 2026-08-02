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


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
