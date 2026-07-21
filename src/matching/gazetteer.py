"""AI/ML skills gazetteer + deterministic phrase matcher.

A curated ``canonical -> aliases`` taxonomy plus an exact, case-insensitive
phrase matcher. Deterministic and fully local: the same text always yields the
same skills — which is the whole point of replacing the probabilistic Haiku
scorer. This is **seed** data scoped to the AI/ML/data/cloud domain the product
targets; grow it from the live JD corpus over time.

Why a gazetteer and not a trained NER: the skill vocabulary is finite and known,
so exact matching is both more precise and 100% repeatable, whereas a statistical
NER would reintroduce the very inconsistency we're trying to remove.

Single-letter / highly-ambiguous skills (Go, R, C) are deliberately mapped only
via disambiguated aliases (``golang``, ``r language``) — a bare ``go`` or ``r``
would false-match ordinary prose.
"""

import re

# canonical display name -> list of lowercase surface aliases.
# The canonical's own lowercased form is always matched too (no need to repeat).
SKILLS: dict[str, list[str]] = {
    # --- Languages ---------------------------------------------------------
    "Python": ["py"],
    "Java": [],
    "C++": ["cpp"],
    "C#": ["c sharp", "csharp"],
    "JavaScript": ["js"],
    "TypeScript": ["ts"],
    "Go": ["golang"],
    "Rust": [],
    "Scala": [],
    "R": ["r language", "rlang"],
    "SQL": [],
    "Bash": ["shell scripting", "shell script"],
    "MATLAB": [],
    # --- Core ML / DL ------------------------------------------------------
    "Machine Learning": ["ml"],
    "Deep Learning": ["dl"],
    "Neural Networks": ["neural network", "cnn", "rnn", "convolutional", "recurrent neural"],
    "PyTorch": ["torch"],
    "TensorFlow": ["tf", "tensor flow"],
    "Keras": [],
    "scikit-learn": ["sklearn", "scikit learn"],
    "JAX": [],
    "XGBoost": ["xgb"],
    "LightGBM": ["lightgbm"],
    "pandas": [],
    "NumPy": ["numpy"],
    "SciPy": [],
    "OpenCV": ["computer vision"],
    "Reinforcement Learning": ["rl"],
    "Time Series": ["time-series", "forecasting"],
    "Statistics": ["statistical analysis", "statistical modeling"],
    "Feature Engineering": [],
    "Model Evaluation": ["model validation", "cross-validation", "cross validation"],
    # --- NLP / LLM ---------------------------------------------------------
    "NLP": ["natural language processing"],
    "LLM": ["large language model", "large language models", "llms"],
    "RAG": ["retrieval augmented generation", "retrieval-augmented generation", "retrieval augmentation"],
    "Prompt Engineering": ["prompting", "prompt design"],
    "Fine-tuning": ["fine tuning", "finetuning", "fine-tune"],
    "PEFT": ["parameter efficient fine-tuning", "parameter-efficient fine-tuning"],
    "LoRA": ["low-rank adaptation"],
    "Transformers": ["transformer models", "transformer architecture"],
    "BERT": [],
    "SBERT": ["sentence transformers", "sentence-transformers", "sentence bert"],
    "GPT": ["gpt-4", "gpt4"],
    "Hugging Face": ["huggingface"],
    "LangChain": [],
    "LangGraph": [],
    "LlamaIndex": ["llama index"],
    "Embeddings": ["embedding", "text embeddings", "word embeddings"],
    "Semantic Search": ["vector search"],
    "Multi-agent Systems": ["multi-agent", "multi agent", "agentic", "agent orchestration"],
    "TTS": ["text-to-speech", "text to speech", "speech synthesis"],
    "ASR": ["automatic speech recognition", "speech recognition", "speech-to-text", "speech to text"],
    "Named Entity Recognition": ["ner"],
    # --- MLOps / serving ---------------------------------------------------
    "MLOps": ["ml ops"],
    "MLflow": ["ml flow"],
    "Weights & Biases": ["wandb", "w&b", "weights and biases"],
    "Kubeflow": [],
    "Docker": ["containerization", "containers"],
    "Kubernetes": ["k8s"],
    "CI/CD": ["cicd", "continuous integration", "continuous delivery", "continuous deployment"],
    "Airflow": ["apache airflow"],
    "DVC": ["data version control"],
    "ONNX": ["onnx runtime", "onnxruntime"],
    "TensorRT": [],
    "Model Serving": ["model deployment", "model inference", "inference serving"],
    "Ray": [],
    "vLLM": [],
    # --- Cloud -------------------------------------------------------------
    "AWS": ["amazon web services"],
    "GCP": ["google cloud", "google cloud platform"],
    "Azure": ["microsoft azure"],
    "SageMaker": ["aws sagemaker", "amazon sagemaker"],
    "Vertex AI": ["vertexai"],
    "Lambda": ["aws lambda"],
    "S3": ["amazon s3"],
    "EC2": [],
    # --- Data engineering --------------------------------------------------
    "Spark": ["apache spark", "pyspark"],
    "Hadoop": [],
    "Kafka": ["apache kafka"],
    "ETL": ["elt", "data pipeline", "data pipelines"],
    "Snowflake": [],
    "Databricks": [],
    "dbt": [],
    "BigQuery": ["big query"],
    "Data Warehousing": ["data warehouse", "data lake"],
    # --- Databases ---------------------------------------------------------
    "PostgreSQL": ["postgres", "postgresql"],
    "MySQL": [],
    "MongoDB": ["mongo"],
    "Redis": [],
    "Elasticsearch": ["elastic search"],
    "pgvector": [],
    "Pinecone": [],
    "Weaviate": [],
    "Chroma": ["chromadb"],
    "FAISS": [],
    "Milvus": [],
    "Qdrant": [],
    # --- Backend / web -----------------------------------------------------
    "FastAPI": ["fast api"],
    "Flask": [],
    "Django": [],
    "REST API": ["rest apis", "restful api", "restful"],
    "GraphQL": [],
    "gRPC": [],
    "Microservices": ["microservice"],
    "Node.js": ["nodejs", "node js"],
    "React": ["react.js", "reactjs"],
    "Vue": ["vue.js", "vuejs"],
    # --- Infra / DevOps ----------------------------------------------------
    "Terraform": [],
    "GitHub Actions": [],
    "Jenkins": [],
    "Prometheus": [],
    "Grafana": [],
    "Linux": ["unix"],
    "Git": ["version control"],
    # --- Security (candidate holds Security+) ------------------------------
    "Cybersecurity": ["cyber security", "information security", "infosec"],
    "Penetration Testing": ["pen testing", "pentesting"],
    "SIEM": [],
    # --- Ways of working ---------------------------------------------------
    "Agile": ["scrum", "kanban"],
    "A/B Testing": ["a/b test", "ab testing", "experimentation"],
    "Data Visualization": ["dataviz", "data viz", "tableau", "power bi", "powerbi"],
    # --- Web / frontend ---
    "Next.js": ["nextjs", "next js"],
    "Angular": [],
    "Svelte": ["sveltekit"],
    "Tailwind CSS": ["tailwind", "tailwindcss"],
    "HTML": ["html5"],
    "CSS": ["css3"],
    "Redux": [],
    # --- Backend frameworks / protocols ---
    "Express": ["express.js", "expressjs"],
    "Spring Boot": ["spring boot", "springboot"],
    ".NET": ["dotnet", "asp.net", ".net core"],
    "Ruby on Rails": ["rails", "ruby on rails"],
    "WebSockets": ["websocket"],
    "OAuth": ["oauth2", "oauth 2.0"],
    "JWT": ["json web token"],
    "RabbitMQ": [],
    "Celery": [],
    # --- More languages ---
    "Kotlin": [],
    "Swift": [],
    "PHP": [],
    "Ruby": [],
    # --- Data stores ---
    "DynamoDB": ["dynamo db"],
    "Cassandra": [],
    "Neo4j": ["neo 4j"],
    "Redshift": ["amazon redshift"],
    "ClickHouse": ["click house"],
    # --- Cloud / infra / devops ---
    "Firebase": [],
    "Cloudflare": [],
    "Nginx": [],
    "Datadog": ["data dog"],
    "Helm": [],
    "Ansible": [],
    "GitLab CI": ["gitlab ci/cd", "gitlab ci"],
    # --- Testing ---
    "pytest": [],
    "Jest": [],
    "Selenium": [],
    "Cypress": [],
    "Playwright": [],
    # --- ML / NLP libraries ---
    "spaCy": ["spacy"],
    "NLTK": [],
    "Diffusion Models": ["stable diffusion", "diffusion model"],
    "GitHub Copilot": ["copilot"],
}


def _norm(s: str) -> str:
    return s.strip().lower()


# Canonicals whose bare display form is an ordinary English word — only their
# explicit aliases may match, never the canonical itself ("go" ≠ Golang).
_NO_BARE = {"Go", "R"}

# alias (lowercased surface) -> canonical display name.
_ALIAS_TO_CANON: dict[str, str] = {}
for _canon, _aliases in SKILLS.items():
    if _canon not in _NO_BARE:
        _ALIAS_TO_CANON[_norm(_canon)] = _canon
    for _a in _aliases:
        _ALIAS_TO_CANON[_norm(_a)] = _canon

# One alternation over every surface form, longest-first so multi-word phrases
# win over their fragments. Boundaries treat +, # and & as part of a token so
# "c++", "c#" and "w&b" match cleanly and "java" does not fire inside
# "javascript" — but a trailing "." or "/" (sentence punctuation) still delimits,
# so "LLMs." and "PyTorch," match.
_BOUNDARY_CHARS = r"a-z0-9+#&"
_surfaces = sorted(_ALIAS_TO_CANON.keys(), key=len, reverse=True)
_MATCH_RE = re.compile(
    rf"(?<![{_BOUNDARY_CHARS}])(?:"
    + "|".join(re.escape(s) for s in _surfaces)
    + rf")(?![{_BOUNDARY_CHARS}])",
    re.IGNORECASE,
)


# PDF extraction (MarkItDown) often splits tokens: "Scikit- learn", "Multi -Agent",
# "CI/ CD", "Node. js". Rejoin around hyphens/slashes/dots so the matcher sees the
# real skill. Kept conservative: only collapses whitespace *adjacent to* a joiner.
_ARTIFACT_HYPHEN = re.compile(r"(\w)\s*-\s+(\w)|(\w)\s+-\s*(\w)")
_ARTIFACT_SLASH = re.compile(r"(\w)\s*/\s+(\w)|(\w)\s+/\s*(\w)")
_ARTIFACT_DOT = re.compile(r"(\w)\.\s+(js|net|io|ai)\b", re.IGNORECASE)


def _normalize_text(text: str) -> str:
    text = _ARTIFACT_HYPHEN.sub(lambda m: f"{m.group(1) or m.group(3)}-{m.group(2) or m.group(4)}", text)
    text = _ARTIFACT_SLASH.sub(lambda m: f"{m.group(1) or m.group(3)}/{m.group(2) or m.group(4)}", text)
    text = _ARTIFACT_DOT.sub(r"\1.\2", text)
    return text


def extract_skills(text: str) -> set[str]:
    """Return the set of canonical skills whose any surface form appears in ``text``."""
    if not text:
        return set()
    return {_ALIAS_TO_CANON[m.group(0).lower()] for m in _MATCH_RE.finditer(_normalize_text(text))}


def canonicalize(term: str) -> str | None:
    """Map a single skill term to its canonical name, or None if unrecognized.

    Tries an exact alias lookup first; falls back to extracting a known skill
    from inside the term (e.g. "Python programming" -> "Python").
    """
    if not term:
        return None
    key = _norm(term)
    if key in _ALIAS_TO_CANON:
        return _ALIAS_TO_CANON[key]
    found = extract_skills(term)
    return next(iter(found)) if len(found) == 1 else None
