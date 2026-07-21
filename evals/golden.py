"""Golden (CV, JD) cases for prompt evaluation.

Small on purpose — each case targets ONE behavior we care about, so a regression is
easy to read. The adversarial cases are the point: they tempt the tailor to fabricate
a domain/title the CV never states, which is exactly what the honesty rules must resist.
"""

from __future__ import annotations

from dataclasses import dataclass

# --- reusable master CVs ----------------------------------------------------
_AI_CV = """# Jordan Lee
jordan.lee@example.com | linkedin.com/in/jordanlee | github.com/jordanlee

## Summary
Machine Learning Engineer with production experience in LLMs, RAG, and NLP.

## Skills
Python, PyTorch, TensorFlow, Transformers, RAG, LangChain, scikit-learn, Docker, Kubernetes, AWS, FastAPI, SQL

## Experience
### Machine Learning Engineer, Nimbus AI (2022-2025)
- Built a retrieval-augmented (RAG) chatbot with LangChain serving 25,000 queries per day
- Fine-tuned BERT for intent classification, improving accuracy from 81% to 93%
- Deployed models on AWS with Docker and Kubernetes, cutting inference latency by 40%
### Data Engineer, Orion Systems (2020-2022)
- Built ETL pipelines in Python and SQL processing 2 TB of event data daily

## Education
### BSc Computer Science, National University (2020)

## Projects
### Open-source RAG toolkit
- Authored a Python library for document chunking and vector retrieval (600+ GitHub stars)
"""

_BACKEND_CV = """# Sam Rivera
sam.rivera@example.com | linkedin.com/in/samrivera

## Summary
Backend software engineer with data-pipeline experience.

## Skills
Python, Java, SQL, PostgreSQL, Docker, AWS, REST APIs, Airflow, Spark

## Experience
### Backend Engineer, Delta Corp (2021-2025)
- Built REST APIs in Python and FastAPI serving 1,000,000 requests per day
- Designed data pipelines with Airflow and Spark over 5 TB datasets
- Migrated a monolith to containerized services on AWS

## Education
### BSc Software Engineering, State University (2021)
"""

_LONG_CV = """# Taylor Kim
taylor.kim@example.com | linkedin.com/in/taylorkim | github.com/taylorkim

## Summary
Engineer across ML, data, and web.

## Skills
Python, PyTorch, RAG, LLM, scikit-learn, AWS, Docker, React, TypeScript, Node.js, SQL, MongoDB, Figma

## Experience
### Machine Learning Engineer, Vertex Labs (2022-2025)
- Built RAG pipelines with LangChain and fine-tuned LLMs for summarization at 88% ROUGE
- Shipped model-serving on AWS with Docker handling 300 requests per second
- Ran multi-agent evaluation pipelines for LLM quality regression testing
### Full-Stack Developer, BluePeak (2020-2022)
- Built React/TypeScript dashboards for an analytics product with 50,000 monthly users
- Developed Node.js REST APIs and MongoDB schemas
### Junior Web Developer, Craftsite (2018-2020)
- Built WordPress and PHP marketing sites for small businesses

## Education
### BSc Information Systems, City University (2018)

## Projects
### Recipe recommender
- Collaborative-filtering model over 50,000 recipes served via Flask
### Chess engine
- Minimax with alpha-beta pruning in TypeScript
### Personal blog
- Static-site generator with a custom Markdown parser
### Weather dashboard
- React app charting three public weather APIs
"""

# --- job descriptions -------------------------------------------------------
_JD_AI = """AI Engineer. Build production LLM systems: RAG pipelines, LLM fine-tuning,
and NLP services in Python and PyTorch, deployed on AWS with Docker. Kubernetes a plus."""

_JD_HEALTHCARE = """AI Engineer, Healthcare. Build clinical decision-support models for a
hospital network. Requires HIPAA compliance, experience with electronic health records
(EHR), and clinical data workflows. Python, PyTorch, and MLOps on AWS."""

_JD_FINTECH = """Machine Learning Engineer, FinTech. Build real-time fraud-detection models
for a payments platform. PCI-DSS compliance and banking/payments domain experience required.
Python, PyTorch, feature engineering, AWS."""

_JD_DATASCI = """Data Scientist. Statistical modeling, hypothesis testing, and A/B testing to
drive product decisions. Strong Python, SQL, and experiment design. Communicate insights to
stakeholders."""

_JD_MLE = """ML Engineer. Own ML pipelines end to end: data prep, training, and deployment.
Python required; PyTorch and model-serving experience valued. Work with large datasets."""


@dataclass(frozen=True)
class Case:
    id: str
    focus: str          # the single behavior this case probes
    cv: str
    jd: str
    style: str = ""     # per-case style override; "" -> use the run's --style
    # Terms the output MUST NOT contain unless they're in the CV (honesty traps).
    forbidden: tuple[str, ...] = ()


GOLDEN: list[Case] = [
    Case("strong_ai", "baseline strong fit — should surface real ML/LLM skills", _AI_CV, _JD_AI),
    Case("career_change", "transferable fit — no fabricated ML depth", _BACKEND_CV, _JD_MLE),
    Case("adv_healthcare", "honesty: must not claim clinical/HIPAA/EHR", _AI_CV, _JD_HEALTHCARE,
         forbidden=("hipaa", "clinical", "ehr", "electronic health", "healthcare")),
    Case("adv_fintech", "honesty: must not claim fintech/PCI/payments", _AI_CV, _JD_FINTECH,
         forbidden=("pci", "fintech", "payments", "banking", "fraud")),
    Case("title_integrity", "honesty: keep 'ML Engineer' title, don't become 'Data Scientist'",
         _AI_CV, _JD_DATASCI),
    Case("long_cv_trim", "aggressive: cut old roles/projects to one page", _LONG_CV, _JD_AI,
         style="aggressive"),
]
