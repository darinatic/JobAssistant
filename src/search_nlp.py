"""Natural-language → structured job-search filters (one Haiku call).

Turns "find 50 remote AI Engineer jobs on JobStreet posted this week" into a
``SearchQuery`` the scrapers understand. Note: only LinkedIn currently applies
date/experience/remote filters (MCF + JobStreet ignore them) — see search.py.
"""

from langchain_anthropic import ChatAnthropic
from pydantic import BaseModel, Field, field_validator

from src.utils.config import settings

_PLATFORM_ALIASES = {
    "mcf": "mycareersfuture", "my careers future": "mycareersfuture",
    "mycareersfuture": "mycareersfuture", "careersfuture": "mycareersfuture",
    "linkedin": "linkedin", "linked in": "linkedin",
    "jobstreet": "jobstreet", "job street": "jobstreet",
}
_DATES = {"past_24_hours", "past_week", "past_month", "any"}
_LEVELS = {"entry_level", "associate", "mid_senior", "director", "executive"}
_REMOTE = {"on_site", "remote", "hybrid"}


class SearchQuery(BaseModel):
    keyword: str = Field(description="The role or skills to search for, e.g. 'AI Engineer'")
    location: str = Field(default="Singapore", description="City/country; default Singapore")
    date_posted: str = Field(default="any", description="One of: past_24_hours, past_week, past_month, any")
    experience_levels: list[str] = Field(
        default_factory=list,
        description="Any of: entry_level, associate, mid_senior, director, executive",
    )
    remote_options: list[str] = Field(
        default_factory=list, description="Any of: on_site, remote, hybrid",
    )
    max_jobs: int = Field(default=25, description="How many jobs to return (1-50)")
    platforms: list[str] = Field(
        default_factory=list,
        description="Any of: mycareersfuture, linkedin, jobstreet. Empty = all platforms.",
    )

    @field_validator("platforms", mode="before")
    @classmethod
    def _norm_platforms(cls, v):
        if not isinstance(v, list):
            return []
        out = []
        for p in v:
            canon = _PLATFORM_ALIASES.get(str(p).strip().lower())
            if canon and canon not in out:
                out.append(canon)
        return out

    @field_validator("date_posted", mode="before")
    @classmethod
    def _norm_date(cls, v):
        v = str(v or "any").strip().lower().replace("-", "_").replace(" ", "_")
        return v if v in _DATES else "any"

    @field_validator("experience_levels", "remote_options", mode="before")
    @classmethod
    def _clean_list(cls, v):
        if not isinstance(v, list):
            return []
        return [str(x).strip().lower() for x in v]

    @field_validator("max_jobs", mode="before")
    @classmethod
    def _clamp_max(cls, v):
        try:
            return max(1, min(50, int(v)))
        except (TypeError, ValueError):
            return 25

    def model_post_init(self, __ctx) -> None:
        # Drop out-of-vocabulary enum values that slipped past.
        object.__setattr__(self, "experience_levels", [e for e in self.experience_levels if e in _LEVELS])
        object.__setattr__(self, "remote_options", [r for r in self.remote_options if r in _REMOTE])


class SearchFilters(SearchQuery):
    """Explicit filters coming straight from the UI dropdowns. Same fields and
    validators as SearchQuery, but `keyword` is optional (the raw search box text
    is used as a fallback). When a request carries these, the endpoints skip the
    Haiku parse entirely — a fully deterministic, no-LLM search path."""

    keyword: str = ""


def build_query(filters: SearchFilters, fallback_query: str) -> SearchQuery:
    """Turn explicit UI filters into a SearchQuery with no LLM call. `keyword`
    falls back to the raw search box text when the filters don't carry one."""
    data = filters.model_dump()
    if not data.get("keyword"):
        data["keyword"] = fallback_query.strip()[:100] or "jobs"
    return SearchQuery(**data)


_SYSTEM = (
    "Extract structured job-search filters from the user's request. Set only the fields "
    "the user actually specifies; leave the rest at their defaults. `keyword` is the role "
    "or skills to search for. Recognise counts ('find 50 jobs' -> max_jobs=50), platform "
    "names ('only on JobStreet' -> platforms=['jobstreet']), recency ('this week' -> "
    "date_posted='past_week'), remote/hybrid/onsite, and seniority."
)

_llm = None


def _get_llm():
    global _llm
    if _llm is None:
        _llm = ChatAnthropic(
            model=settings.anthropic_haiku_model,
            api_key=settings.anthropic_api_key.get_secret_value(),
            max_tokens=512,
            temperature=0,
        ).with_structured_output(SearchQuery)
    return _llm


async def parse_search_query(text: str) -> SearchQuery:
    from langchain_core.messages import HumanMessage, SystemMessage

    try:
        return await _get_llm().ainvoke([SystemMessage(content=_SYSTEM), HumanMessage(content=text)])
    except Exception:
        # Fall back to treating the whole text as the keyword.
        return SearchQuery(keyword=text.strip()[:100] or "jobs")
