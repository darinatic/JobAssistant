"""Persist gazetteer-growth candidates to Supabase for later curation.

When the JD parser reconciles skills onto the gazetteer (`matching.reconcile_jd_skills`),
any skill Haiku named that the gazetteer doesn't recognize is a "growth candidate" — a
term worth reviewing for addition to the taxonomy. This appends them to a frequency-
aggregated `growth_candidates` table (a ranked review queue) via the Supabase PostgREST
RPC `record_growth_candidates`.

Uses the REST API over HTTPS with **standard TLS verification** (`httpx`, already a core
dependency). Call `schedule()` (the fire-and-forget entry point) — it runs the write on
the event loop so it never adds latency to tailoring. The write is **fail-open**: it
never raises, so a slow or down database can't break tailoring, and it's a no-op when
the Supabase REST creds are unset (local dev without the DB).
"""

from __future__ import annotations

import asyncio
import logging

import httpx

from src.utils.config import settings

log = logging.getLogger(__name__)

# Hold references to in-flight fire-and-forget tasks so they aren't GC'd mid-run.
_pending: set[asyncio.Task] = set()


def schedule(candidates: list[str], title: str | None) -> None:
    """Fire-and-forget the persistence on the running event loop — **non-blocking**,
    so it never adds latency to tailoring even if Supabase is slow. No-op with no
    running loop (sync context) or when unconfigured."""
    if not settings.growth_persist_enabled or not candidates:
        return
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    task = loop.create_task(record_candidates(candidates, title))
    _pending.add(task)
    task.add_done_callback(_pending.discard)


async def record_candidates(candidates: list[str], title: str | None) -> None:
    """Append gazetteer-growth candidates (frequency-aggregated by the RPC). Never raises."""
    if not settings.growth_persist_enabled or not candidates:
        return
    key = settings.supabase_service_role_key.get_secret_value()  # type: ignore[union-attr]
    url = f"{settings.supabase_url.rstrip('/')}/rest/v1/rpc/record_growth_candidates"  # type: ignore[union-attr]
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                url,
                headers={
                    "apikey": key,
                    "Authorization": f"Bearer {key}",
                    "Content-Type": "application/json",
                },
                json={"p_candidates": candidates, "p_title": title},
            )
            resp.raise_for_status()
    except httpx.RequestError as e:
        # Supabase unreachable: paused free-tier project, offline dev box, DNS. This is
        # best-effort telemetry on a fail-open path, so a full traceback here reads like
        # a broken request and buries the real logs — one line is enough.
        log.warning("growth-candidate persistence unavailable (%s): %s", type(e).__name__, e)
    except Exception:  # noqa: BLE001 — best-effort telemetry, must not break tailoring
        # Anything else (auth, bad RPC, 4xx/5xx) is a real misconfiguration worth tracing.
        log.warning("growth-candidate persistence failed", exc_info=True)
