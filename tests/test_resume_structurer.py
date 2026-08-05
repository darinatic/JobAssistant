"""Tests for the structured resume parse endpoint (LLM + MarkItDown mocked)."""

from unittest.mock import AsyncMock, MagicMock, patch

from src.agents.resume_structurer import (
    ResumeBlock,
    ResumeBullet,
    ResumeDocModel,
    ResumeField,
    ResumeSection,
)


def _fake_doc() -> ResumeDocModel:
    return ResumeDocModel(sections=[
        ResumeSection(id="contact", label="Contact", kind="fields", conf=0.99,
                      fields=[ResumeField(label="Full name", value="Jane Doe"),
                              ResumeField(label="Email", value="jane@x.com")]),
        ResumeSection(id="experience", label="Experience", kind="blocks", conf=0.7,
                      issue="One role reads 'Present'. Confirm it is still current.",
                      blocks=[ResumeBlock(title="Engineer", org="Acme", dates="2023",
                                          bullets=[ResumeBullet(text="Built things")])]),
    ])


def _markitdown(text: str):
    md = MagicMock()
    md.convert_stream.return_value = MagicMock(text_content=text)
    return MagicMock(return_value=md)


def test_resume_parse_returns_structured_doc(client):
    text = "Jane Doe — Engineer at Acme.\n" + "detail line. " * 30
    agent = MagicMock()
    agent.structure = AsyncMock(return_value=_fake_doc())
    with patch("markitdown.MarkItDown", _markitdown(text)), \
         patch("src.api.ResumeStructurerAgent", return_value=agent):
        r = client.post("/resume/parse",
                        files={"file": ("cv.pdf", b"%PDF-1.4 fake", "application/pdf")})
    assert r.status_code == 200
    body = r.json()
    assert body["chars"] == len(text)
    assert [s["id"] for s in body["doc"]["sections"]] == ["contact", "experience"]
    assert body["doc"]["sections"][0]["fields"][0]["value"] == "Jane Doe"
    assert body["doc"]["sections"][1]["blocks"][0]["bullets"][0]["text"] == "Built things"
    # slice 2: per-section confidence + review issue flow through the endpoint
    assert body["doc"]["sections"][1]["conf"] == 0.7
    assert "confirm" in body["doc"]["sections"][1]["issue"].lower()
    assert body["doc"]["sections"][0]["issue"] is None


def test_docx_upload_uses_the_text_path(client):
    text = "Jane Doe — Engineer at Acme.\n" + "detail line. " * 30
    agent = MagicMock()
    agent.structure = AsyncMock(return_value=_fake_doc())
    agent.structure_from_file = AsyncMock()
    with patch("markitdown.MarkItDown", _markitdown(text)) as md, \
         patch("src.api.ResumeStructurerAgent", return_value=agent):
        r = client.post("/resume/parse",
                        files={"file": ("cv.docx", b"PK\x03\x04fake", "application/vnd.openxmlformats-officedocument.wordprocessingml.document")})
    assert r.status_code == 200
    # DOCX is converted with the .docx extension, and structured via the text path.
    assert md.return_value.convert_stream.call_args.kwargs["file_extension"] == ".docx"
    agent.structure.assert_awaited_once()
    agent.structure_from_file.assert_not_awaited()


def test_scanned_pdf_falls_back_to_vision_ocr(client):
    agent = MagicMock()
    agent.structure = AsyncMock()
    agent.structure_from_file = AsyncMock(return_value=_fake_doc())
    with patch("markitdown.MarkItDown", _markitdown("")), \
         patch("src.api.ResumeStructurerAgent", return_value=agent):
        r = client.post("/resume/parse",
                        files={"file": ("scan.pdf", b"%PDF-1.4 image only", "application/pdf")})
    assert r.status_code == 200
    # No extractable text + a PDF → OCR via Claude vision, not a 422.
    agent.structure_from_file.assert_awaited_once()
    assert agent.structure_from_file.await_args.args[1] == "application/pdf"
    agent.structure.assert_not_awaited()


def test_empty_docx_is_rejected(client):
    with patch("markitdown.MarkItDown", _markitdown("short")):
        r = client.post("/resume/parse",
                        files={"file": ("empty.docx", b"PK\x03\x04", "application/vnd.openxmlformats-officedocument.wordprocessingml.document")})
    assert r.status_code == 422
    assert "docx" in r.json()["detail"].lower()
