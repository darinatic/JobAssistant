"""LLM-judge parsing + aggregation — mocked (no OpenAI call).

The judge is a dev-only tool; `openai` ships in the optional `[eval]` extra, not
`[dev]`. Skip cleanly when it isn't installed (e.g. CI runs `-e ".[dev]"`)."""

import json
from unittest.mock import AsyncMock, patch

import pytest

pytest.importorskip("openai", reason="openai only installed with the [eval] extra")

from evals.graders import summarize
from evals.judge import judge_output


class _Msg:
    def __init__(self, content): self.message = type("m", (), {"content": content})


@pytest.mark.asyncio
async def test_judge_parses_scores():
    payload = json.dumps({"relevance": 4, "quality": 5, "ats": 4, "overall": 4, "rationale": "solid"})
    fake = AsyncMock(return_value=type("r", (), {"choices": [_Msg(payload)]}))
    with patch("openai.AsyncOpenAI") as C:
        C.return_value.chat.completions.create = fake
        out = await judge_output("some JD", "# Resume\n- did things")
    assert out == {"relevance": 4, "quality": 5, "ats": 4, "overall": 4, "rationale": "solid"}


@pytest.mark.asyncio
async def test_judge_empty_output_returns_none():
    assert await judge_output("jd", "") is None


def test_summary_includes_judge_averages_when_present():
    rows = [
        {"ok": True, "fabrications": 0, "forbidden_hits": [], "keyword_coverage": 1.0,
         "fits_one_page": True, "structure_ok": True, "judge_overall": 4, "judge_relevance": 4},
        {"ok": True, "fabrications": 0, "forbidden_hits": [], "keyword_coverage": 1.0,
         "fits_one_page": True, "structure_ok": True, "judge_overall": 2, "judge_relevance": 3},
    ]
    s = summarize(rows)
    assert s["avg_judge_overall"] == 3.0 and s["avg_judge_relevance"] == 3.5
