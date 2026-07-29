from src.jd_preprocess import preprocess_jd

JD = """About the company:
We are a fast-growing unicorn founded in 2010 with a great culture.

Responsibilities:
- Build RAG pipelines with Python and PyTorch
- Deploy LLM services on AWS

Requirements:
- 2+ years Python
- Experience with Kubernetes

Benefits:
- Free lunch, gym, stock options
- Equal Opportunity Employer

How to apply:
Send your CV to jobs@company.com
"""


def test_keeps_signal_sections():
    out = preprocess_jd(JD)
    assert "Responsibilities" in out and "RAG pipelines" in out
    assert "Requirements" in out and "Kubernetes" in out


def test_drops_boilerplate():
    out = preprocess_jd(JD)
    assert "unicorn" not in out              # about-the-company dropped
    assert "Free lunch" not in out           # benefits dropped
    assert "jobs@company.com" not in out     # how-to-apply dropped


def test_no_sections_falls_back_to_head():
    plain = "We need a strong Python engineer with RAG and AWS experience. " * 50
    out = preprocess_jd(plain, max_chars=200)
    assert out.startswith("We need a strong Python")
    assert len(out) <= 200


def test_empty():
    assert preprocess_jd("") == ""
    assert preprocess_jd("   ") == ""


def test_caps_length():
    out = preprocess_jd("Responsibilities:\n" + "- do things\n" * 500, max_chars=300)
    assert len(out) <= 300
