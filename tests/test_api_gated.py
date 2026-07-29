import json
from unittest.mock import patch

from fastapi.testclient import TestClient


def _client():
    from src.api import app
    return TestClient(app)


async def _fake_gated(**kwargs):
    yield {"type": "progress", "found": 0, "target": 1, "scanned": 1}
    yield {"type": "job", "data": {"platform": "mycareersfuture", "external_id": "1",
                                   "title": "AI Engineer", "fit": 80, "below_threshold": False}}


def _lines(resp):
    return [json.loads(line) for line in resp.text.splitlines() if line.strip()]


def test_stream_uses_gate_when_predictor_enabled():
    with patch("src.match_predictor.is_enabled", return_value=True), \
         patch("src.search.search_jobs_gated_stream", _fake_gated):
        r = _client().post("/search/stream", json={"query": "AI Engineer", "resume_markdown": "cv"})
    kinds = [m["type"] for m in _lines(r)]
    assert "interpreted" in kinds and "progress" in kinds and "job" in kinds and "done" in kinds


def test_stream_uses_lazy_when_predictor_off():
    async def _fake_lazy(**kwargs):
        if False:
            yield {}

    with patch("src.match_predictor.is_enabled", return_value=False), \
         patch("src.search.search_jobs_stream", _fake_lazy), \
         patch("src.search.search_jobs_gated_stream") as gated:
        r = _client().post("/search/stream", json={"query": "AI Engineer", "resume_markdown": "cv"})
    assert r.status_code == 200
    gated.assert_not_called()
