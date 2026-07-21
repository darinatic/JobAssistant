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
    anthropic_haiku_model: str = "claude-haiku-4-5-20251001"
    anthropic_sonnet_model: str = "claude-sonnet-4-5-20250929"

    # OpenAI: embeddings + the (dev-only) eval LLM-judge. Everything the app SERVES
    # stays on Anthropic / Claude; the judge is deliberately a different provider to
    # avoid a model grading its own family's output.
    openai_api_key: SecretStr | None = None
    openai_judge_model: str = "gpt-4o-mini"

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
    # Route the browser-based scraper (JobStreet) through Browserbase too, so it
    # survives datacenter-IP blocking in production. LinkedIn already uses Browserbase
    # whenever browserbase_enabled. Off by default — local dev uses in-container Chromium.
    browserbase_scrapers: bool = False

    # Per-IP rate limits for the expensive endpoints (LLM + scrape). 0 = disabled.
    # Sized for a public no-auth demo; override via env in production.
    rate_limit_per_min: int = 12
    rate_limit_per_day: int = 120

    generate_cover_letters: bool = True
    headless_mode: bool = False
    browser_slowmo_ms: int = 100

    # Explicit path to the Tectonic binary (LaTeX→PDF). Optional — the renderer also
    # checks PATH and common install locations. Set TECTONIC_PATH if it lives somewhere
    # unusual or the server is launched from a shell without it on PATH.
    tectonic_path: str | None = None

    # Phase 10 — shared resume↔JD fit predictor (bi-encoder + LoRA, ONNX served).
    # 'none' (default) = feature off, predict_fit() is a no-op. 'v1' = load model.
    match_predictor_model: str = "none"
    # HF Hub repo id holding the versioned ONNX artifact (private), or a local path.
    match_predictor_repo: str | None = None
    match_predictor_path: str | None = None
    hf_token: SecretStr | None = None      # download the private artifact
    wandb_api_key: SecretStr | None = None  # training-box only

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
