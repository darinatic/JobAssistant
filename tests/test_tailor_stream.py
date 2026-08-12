"""Streaming tailor: per-chunk PII restore and output cleanup.

The streaming path drops ``with_structured_output`` (a schema can only be delivered
complete), so two things that the schema used to guarantee now need their own guards:
identifiers must be restored before a chunk reaches the client, and the text must
actually be bare markdown.
"""

import pytest

from src.guardrails.output import StreamingRestorer
from src.guardrails.pii import anonymize
from src.services import _clean_streamed_resume

_CV = """# Jane Tan

jane.tan@example.com | +65 9123 4567 | linkedin.com/in/janetan

## Skills

Python, RAG
"""


@pytest.fixture
def redaction():
    r = anonymize(_CV)
    assert r.available and r.entity_mapping, "fixture needs a real redaction"
    return r


def _name_token(redaction) -> str:
    return redaction.entity_mapping["NAME"]["Jane Tan"]


def _drain(redaction, chunks) -> str:
    r = StreamingRestorer(redaction)
    return "".join(r.push(c) for c in chunks) + r.flush()


# --- the whole point: a token must never reach the client -------------------

def test_token_arriving_whole_is_restored(redaction):
    out = _drain(redaction, [f"# {_name_token(redaction)}\n"])
    assert out == "# Jane Tan\n"


def test_token_split_across_chunks_is_still_restored(redaction):
    token = _name_token(redaction)
    mid = len(token) // 2
    out = _drain(redaction, ["# ", token[:mid], token[mid:], "\n## Skills"])
    assert "Jane Tan" in out
    assert token not in out


@pytest.mark.parametrize("size", [1, 2, 3, 5, 7])
def test_restored_output_is_identical_at_every_chunk_size(redaction, size):
    src = f"# {_name_token(redaction)}\n\n## Skills\n\nPython, RAG\n"
    chunks = [src[i:i + size] for i in range(0, len(src), size)]
    assert _drain(redaction, chunks) == "# Jane Tan\n\n## Skills\n\nPython, RAG\n"


def test_no_partial_token_is_ever_emitted(redaction):
    """Every intermediate emission must be free of placeholder fragments."""
    token = _name_token(redaction)
    src = f"# {token}\n\n## Skills\n"
    r = StreamingRestorer(redaction)
    for i in range(0, len(src), 2):
        emitted = r.push(src[i:i + 2])
        assert "<" not in emitted, f"leaked a partial token: {emitted!r}"


# --- the stream must not stall ----------------------------------------------

def test_an_unclosed_angle_bracket_does_not_stall_the_stream(redaction):
    # Ordinary prose can contain a '<' that never closes. Holding forever would
    # freeze the UI mid-resume, so the hold is length-capped.
    long_tail = "x" * (StreamingRestorer._MAX_HOLD + 10)
    out = _drain(redaction, ["- built a service handling <", long_tail])
    assert long_tail in out


def test_flush_releases_a_held_tail(redaction):
    r = StreamingRestorer(redaction)
    assert r.push("done <NAM") == "done "  # holds the possible token
    assert "NAM" in r.flush()


def test_restorer_is_a_noop_when_redaction_unavailable():
    from src.guardrails.pii import Redaction

    r = StreamingRestorer(Redaction(text="x", available=False))
    assert r.push("<NAME_0> stays") == "<NAME_0> stays"


# --- output cleanup ----------------------------------------------------------

def test_clean_strips_a_code_fence():
    assert _clean_streamed_resume("```markdown\n# Jane\n\n## Skills\n```") == "# Jane\n\n## Skills"


def test_clean_strips_a_conversational_preamble():
    raw = "Here is the tailored resume:\n\n# Jane Tan\n\n## Skills\n\nPython"
    assert _clean_streamed_resume(raw).startswith("# Jane Tan")


def test_clean_leaves_good_markdown_untouched():
    good = "# Jane Tan\n\n## Skills\n\nPython, RAG"
    assert _clean_streamed_resume(good) == good


def test_clean_does_not_eat_a_leading_heading():
    # The '# ' search must not strip the document's own first heading.
    assert _clean_streamed_resume("# Jane\n\n## Skills\n\n# Not a name").startswith("# Jane")


# --- the service generator (offline, fake streaming model) -------------------

@pytest.mark.asyncio
async def test_stream_tailoring_emits_match_then_deltas_then_done(monkeypatch):
    """End-to-end shape of the generator with the LLM faked out."""
    from src import services
    from src.agents.schemas import (
        ExperienceLevel,
        MatchRecommendation,
        ParsedJobDescription,
        SkillMatch,
    )

    parsed = ParsedJobDescription(
        title="AI Engineer", company="Globex", location="Singapore",
        experience_level=ExperienceLevel.MID, experience_required="3+ years",
        required_skills=["Python"], responsibilities=["Build things"],
    )
    match = SkillMatch(overall_score=80, recommendation=MatchRecommendation.APPLY,
                       reasoning="ok", matched_required=["Python"])

    async def fake_parse(jd_text, **kw):
        return parsed

    async def fake_score(pj, master_cv=None):
        return match

    # Echo every placeholder, as a real model at temperature 0 does. Dropping one
    # would fire the header safety net and legitimately rewrite the header (covered
    # by the next test), which is not what this test is about.
    rd = anonymize(_CV)
    tokens = [ph for by_type in rd.entity_mapping.values() for ph in by_type.values()]
    header = f"# {rd.entity_mapping['NAME']['Jane Tan']}\n\n" + " | ".join(
        t for t in tokens if not t.startswith("<NAME")
    ) + "\n"

    class FakeTailor:
        async def stream_tailor(self, *a, **kw):
            for piece in [header, "\n## Skills\n", "\nPython, RAG\n"]:
                yield piece

    monkeypatch.setattr(services, "parse_jd", fake_parse)
    monkeypatch.setattr(services, "score_jd", fake_score)
    monkeypatch.setattr(services, "_get_resume_tailor", lambda: FakeTailor())

    events = [m async for m in services.stream_tailoring("a JD long enough", master_cv=_CV)]

    assert events[0]["type"] == "match"
    assert events[0]["data"]["overall_score"] == 80
    assert events[0]["parsed_jd"]["title"] == "AI Engineer"

    deltas = [e for e in events if e["type"] == "delta"]
    assert deltas, "expected streamed text"

    done = events[-1]
    assert done["type"] == "done"
    assert done["guardrails"]["all_restored"] is True

    md = done["tailored_resume_markdown"]
    # `done` is authoritative and may differ from the deltas: the contact header is
    # always rebuilt from the CV (see guardrails.output.restore_and_verify), so the
    # displayed text is not required to match it byte for byte.
    assert md.startswith("# Jane Tan")
    assert "jane.tan@example.com | +65 9123 4567 | linkedin.com/in/janetan" in md
    # The body is the model's, and it is what streamed.
    assert "Python, RAG" in md
    assert "Python, RAG" in "".join(d["text"] for d in deltas)


@pytest.mark.asyncio
async def test_done_is_authoritative_when_the_header_safety_net_fires(monkeypatch):
    """The client must adopt `done`, not the concatenated deltas.

    When the model fails to echo an identifier placeholder, restore_and_verify
    force-restores the contact header from the real CV. That is content the user
    never saw stream, so the two legitimately differ and `done` wins.
    """
    from src import services
    from src.agents.schemas import (
        ExperienceLevel,
        MatchRecommendation,
        ParsedJobDescription,
        SkillMatch,
    )

    parsed = ParsedJobDescription(
        title="AI Engineer", company="Globex", location="Singapore",
        experience_level=ExperienceLevel.MID, experience_required="3+ years",
        required_skills=["Python"], responsibilities=["Build things"],
    )
    match = SkillMatch(overall_score=80, recommendation=MatchRecommendation.APPLY, reasoning="ok")

    class ForgetfulTailor:
        async def stream_tailor(self, *a, **kw):
            # Name echoed, contact placeholders dropped.
            name = anonymize(_CV).entity_mapping["NAME"]["Jane Tan"]
            yield f"# {name}\n\n## Skills\n\nPython\n"

    async def fake_parse(jd_text, **kw):
        return parsed

    async def fake_score(pj, master_cv=None):
        return match

    monkeypatch.setattr(services, "parse_jd", fake_parse)
    monkeypatch.setattr(services, "score_jd", fake_score)
    monkeypatch.setattr(services, "_get_resume_tailor", lambda: ForgetfulTailor())

    events = [m async for m in services.stream_tailoring("a JD long enough", master_cv=_CV)]
    done = events[-1]
    shown = "".join(e["text"] for e in events if e["type"] == "delta")

    assert done["guardrails"]["header_forced"] is True
    assert "jane.tan@example.com" in done["tailored_resume_markdown"]
    assert "jane.tan@example.com" not in shown  # never streamed; the net added it


@pytest.mark.asyncio
async def test_stream_tailoring_restores_identifiers_before_they_are_displayed(monkeypatch):
    from src import services
    from src.agents.schemas import (
        ExperienceLevel,
        MatchRecommendation,
        ParsedJobDescription,
        SkillMatch,
    )

    parsed = ParsedJobDescription(
        title="AI Engineer", company="Globex", location="Singapore",
        experience_level=ExperienceLevel.MID, experience_required="3+ years",
        required_skills=["Python"], responsibilities=["Build things"],
    )
    match = SkillMatch(overall_score=80, recommendation=MatchRecommendation.APPLY, reasoning="ok")
    token = anonymize(_CV).entity_mapping["NAME"]["Jane Tan"]

    class FakeTailor:
        async def stream_tailor(self, *a, **kw):
            # split the placeholder straight down the middle
            mid = len(token) // 2
            for piece in ["# ", token[:mid], token[mid:], "\n\n## Skills\n\nPython\n"]:
                yield piece

    async def fake_parse(jd_text, **kw):
        return parsed

    async def fake_score(pj, master_cv=None):
        return match

    monkeypatch.setattr(services, "parse_jd", fake_parse)
    monkeypatch.setattr(services, "score_jd", fake_score)
    monkeypatch.setattr(services, "_get_resume_tailor", lambda: FakeTailor())

    events = [m async for m in services.stream_tailoring("a JD long enough", master_cv=_CV)]
    shown = "".join(e["text"] for e in events if e["type"] == "delta")

    assert "Jane Tan" in shown
    assert token not in shown
    assert "<" not in shown


# --- endpoint payload shape --------------------------------------------------

def test_match_event_carries_the_same_shape_as_done():
    """Both events must carry a full MatchOut.

    The `match` event originally shipped a raw SkillMatch, which has no
    surfaceable_skills/genuine_gaps/keyword_* fields. The client renders those the
    moment the event lands, so the tailor stage crashed on `undefined.length`
    mid-stream while the server happily logged 200.
    """
    import json
    from unittest.mock import patch

    from fastapi.testclient import TestClient

    from src.api import MatchOut, app

    async def fake_stream(jd_text, **kw):
        yield {
            "type": "match",
            "data": {
                "overall_score": 80, "matched_required": ["Python"], "matched_preferred": [],
                "missing_required": [], "missing_preferred": [], "transferable_skills": [],
                "recommendation": "apply", "reasoning": "ok",
            },
            "parsed_jd": {
                "company": "Globex", "title": "AI Engineer", "location": "Singapore",
                "work_arrangement": "onsite", "required_skills": ["Python"],
                "preferred_skills": [], "experience_required": "3+ years",
                "experience_level": "mid", "responsibilities": [], "tech_stack": [],
                "benefits": [], "red_flags": [], "keywords_for_resume": [],
            },
        }
        yield {"type": "delta", "text": "# Jane Tan\n\n## Skills\n\nPython\n"}
        yield {
            "type": "done",
            "tailored_resume_markdown": "# Jane Tan\n\n## Skills\n\nPython\n",
            "guardrails": {"available": False},
        }

    with patch("src.api.services.stream_tailoring", new=fake_stream):
        with TestClient(app) as client, client.stream(
            "POST", "/tailor/stream",
            json={"jd_text": "a" * 40, "resume_markdown": _CV},
        ) as r:
            assert r.status_code == 200
            events = [json.loads(line) for line in r.iter_lines() if line.strip()]

    match_ev = next(e for e in events if e["type"] == "match")
    done_ev = next(e for e in events if e["type"] == "done")

    expected = set(MatchOut.model_fields)
    assert set(match_ev["data"]) == expected, "match event is not a full MatchOut"
    assert set(done_ev["match"]) == expected
    # The fields the UI dereferences immediately must be present and list-typed.
    for field in ("surfaceable_skills", "genuine_gaps", "keyword_have", "keyword_missing"):
        assert isinstance(match_ev["data"][field], list), field
