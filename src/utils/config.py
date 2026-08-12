"""Configuration management for ResumeAgent."""

from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    project_root: Path = Path(__file__).parent.parent.parent
    master_cv_path: Path = Field(default_factory=lambda: Path("master_cv.md"))
    outputs_dir: Path = Field(default_factory=lambda: Path("outputs/tailored"))

    anthropic_api_key: SecretStr

    # Model IDs (env-overridable, e.g. ANTHROPIC_HAIKU_MODEL=...). Haiku parses
    # the JD (cheap); Sonnet tailors + writes the cover letter (quality).
    # These remain the Anthropic-specific defaults that feed the role settings below.
    anthropic_haiku_model: str = "claude-haiku-4-5-20251001"
    anthropic_sonnet_model: str = "claude-sonnet-4-5-20250929"

    # --- provider-agnostic model roles ---------------------------------------
    # The app selects models by ROLE, not by name: the prompts are tuned to a
    # capability tier, not to a vendor. Each is a "provider:model" string resolved
    # through langchain's init_chat_model (see src/llm.py), so switching provider is
    # an env change: LLM_SMART_MODEL=openai:gpt-4o.
    #
    # Blank means "derive from the anthropic_* fields above", which keeps every
    # existing deployment working untouched (prod sets ANTHROPIC_*_MODEL).
    llm_fast_model: str = ""    # JD parse, resume structuring, NL search query
    llm_smart_model: str = ""   # resume tailoring, cover letter
    # Optional: a second model tried when the primary errors (e.g. an Anthropic 529
    # overload). Same "provider:model" form. Blank = no fallback, failures surface.
    llm_fallback_model: str = ""

    # OpenAI: embeddings + the (dev-only) eval LLM-judge, and available as an app
    # provider via LLM_*_MODEL=openai:... The judge is deliberately a different
    # provider to avoid a model grading its own family's output.
    openai_api_key: SecretStr | None = None
    openai_judge_model: str = "gpt-4o-mini"

    # Google Gemini — only needed when an LLM_*_MODEL points at google_genai:...
    google_api_key: SecretStr | None = None

    @property
    def fast_model(self) -> str:
        """Effective 'provider:model' for the cheap/structural role."""
        return self.llm_fast_model or f"anthropic:{self.anthropic_haiku_model}"

    @property
    def smart_model(self) -> str:
        """Effective 'provider:model' for the quality/writing role."""
        return self.llm_smart_model or f"anthropic:{self.anthropic_sonnet_model}"

    linkedin_search_keyword: str = "AI Engineer"
    linkedin_search_location: str = "Singapore"
    # past_24_hours, past_week, past_month, any
    linkedin_search_date_posted: str = "past_24_hours"
    # entry_level, associate, mid_senior, director, executive
    linkedin_search_experience: list[str] = []
    # on_site, remote, hybrid
    linkedin_search_remote: list[str] = []

    # Browserbase — optional cloud browser + residential proxies. When both key and
    # project id are set, LinkedIn descriptions are fetched through a proxied cloud
    # browser (dodges the guest IP soft-wall). Off by default; paid per browser-minute.
    browserbase_api_key: SecretStr | None = None
    browserbase_project_id: str | None = None
    browserbase_region: str = "ap-southeast-1"  # Singapore-nearest region
    # Residential proxies require a PAID Browserbase plan (free plan → 402). Even
    # without them, the cloud browser's real fingerprint reads LinkedIn fine; turn
    # this on for extra wall-resistance once you're on a paid plan.
    browserbase_proxies: bool = False
    # Geo-target the residential proxy so its IP matches the SG session region +
    # SG locale/timezone (removes a fingerprint mismatch, reads as a local user).
    # ISO-2 country + uppercase city; blank country → Browserbase's default geo.
    browserbase_proxy_country: str = "SG"
    browserbase_proxy_city: str = "SINGAPORE"
    # Route the browser-based scraper (JobStreet) through Browserbase too, so it
    # survives datacenter-IP blocking in production. LinkedIn already uses Browserbase
    # whenever browserbase_enabled. Off by default — local dev uses in-container Chromium.
    browserbase_scrapers: bool = False

    # Predictor-gated search: only jobs with calibrated fit >= threshold (0-100) are
    # surfaced; scrape at most cap_mult x N candidates before falling back to the
    # best found (floor). Gating is active only when the predictor is enabled.
    match_gate_threshold: float = 40
    gate_scrape_cap_mult: int = 3
    # Global ceiling on concurrent Browserbase sessions across ALL requests, so a
    # burst of users can't exceed the plan. Used by src/browser/pool.py.
    browserbase_max_sessions: int = 8
    # LinkedIn detail fetches rotate to a fresh Browserbase session (new IP with
    # proxies) every N jobs, so a batch can't burst past LinkedIn's ~5-10 req/IP
    # soft-wall and lose the tail. Small = wall-safe but more sessions; 0/1 = per-job.
    browserbase_jobs_per_session: int = 6

    # Per-IP rate limits for the expensive endpoints (LLM + scrape). 0 = disabled.
    # Sized for a public no-auth demo; override via env in production.
    rate_limit_per_min: int = 12
    rate_limit_per_day: int = 120

    generate_cover_letters: bool = True

    # PII guardrail: strip the candidate's direct identifiers (name/email/phone/URL)
    # from the CV before it is sent to Anthropic, restore them locally afterward.
    # On by default; fails open (a Presidio error tailors on the real CV). See
    # src/guardrails. Set false to disable locally for debugging.
    pii_redaction_enabled: bool = True

    # Supabase REST creds. When both are set, the JD parser persists gazetteer-growth
    # candidates (skills Haiku named that the gazetteer doesn't know) to a
    # `growth_candidates` table for later curation, via a PostgREST RPC — see
    # src/growth.py. Unset = feature off (writes are a no-op). Fail-open; never blocks
    # tailoring. (SUPABASE_DB_POOL_URL / SUPABASE_ANON_KEY may also live in .env for
    # direct-SQL / future data-platform work; not used by the app runtime.)
    supabase_url: str | None = None
    supabase_service_role_key: SecretStr | None = None

    @property
    def growth_persist_enabled(self) -> bool:
        return bool(self.supabase_url and self.supabase_service_role_key)

    headless_mode: bool = False
    browser_slowmo_ms: int = 100

    # Explicit path to the Tectonic binary (LaTeX→PDF). Optional — the renderer also
    # checks PATH and common install locations. Set TECTONIC_PATH if it lives somewhere
    # unusual or the server is launched from a shell without it on PATH.
    tectonic_path: str | None = None

    # Phase 10 — shared resume↔JD fit predictor (bi-encoder + LoRA, ONNX served).
    # 'none' (default) = feature off, predict_fit() is a no-op. 'v1' = load model.
    match_predictor_model: str = "none"
    # Local dir holding the baked ONNX artifact (model.onnx + tokenizer.json).
    match_predictor_path: str | None = None

    # LangSmith observability (optional, OFF by default). When enabled, LangChain
    # LLM calls trace to LangSmith (env-driven at startup — no call-site changes).
    # Prompt inputs/outputs (CV/JD text) are hidden from traces by default to keep
    # the app's "nothing stored" stance; set langsmith_hide_io=False for local dev.
    langsmith_tracing: bool = False
    langsmith_api_key: SecretStr | None = None
    langsmith_project: str = "resumeagent"
    langsmith_hide_io: bool = True
    # Optional LangSmith Hub prompt refs (owner/name[:commit]) keyed by registry
    # prompt name — when set AND tracing is on, get_prompt pulls from the Hub;
    # otherwise the in-repo registry serves. e.g. "resume_tailor=me/tailor,jd_parser=me/jdp".
    langsmith_prompt_refs: str = ""

    cors_origins: str = ""
    # Set to false in production. When true, any http(s)://localhost(:port) and
    # http(s)://127.0.0.1(:port) origin is allowed — fine for local dev where
    # Vite roams between 5173/5174/etc.
    cors_allow_dev_localhost: bool = True

    log_level: str = "INFO"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def cors_origin_regex(self) -> str | None:
        # Dev: allow any localhost / 127.0.0.1 port so Vite can roam between
        # 5173/5174/etc. In production, pin exact origins via CORS_ORIGINS.
        if self.cors_allow_dev_localhost:
            return r"https?://(localhost|127\.0\.0\.1)(:\d+)?"
        return None

    @property
    def browserbase_enabled(self) -> bool:
        return bool(self.browserbase_api_key and self.browserbase_project_id)

    @property
    def langsmith_enabled(self) -> bool:
        """Trace only when explicitly turned on AND a key is present."""
        return bool(self.langsmith_tracing and self.langsmith_api_key)

    @property
    def langsmith_prompt_ref_map(self) -> dict[str, str]:
        """Parse ``langsmith_prompt_refs`` into {prompt_name: hub_ref}."""
        out: dict[str, str] = {}
        for pair in self.langsmith_prompt_refs.split(","):
            if "=" in pair:
                k, v = pair.split("=", 1)
                if k.strip() and v.strip():
                    out[k.strip()] = v.strip()
        return out

    def get_master_cv(self) -> str:
        cv_path = self.project_root / self.master_cv_path
        if not cv_path.exists():
            raise FileNotFoundError(f"Master CV not found at {cv_path}")
        return cv_path.read_text(encoding="utf-8")


settings = Settings()
