"""LLM-as-judge for tailored resumes (OpenAI, dev-only).

Scores the SUBJECTIVE quality the deterministic graders can't see — relevance to the
JD, writing quality, and ATS keyword alignment. Cross-provider on purpose: the app
tailors with Claude, the judge is OpenAI, so a model isn't grading its own family.
"""

from __future__ import annotations

import json

from src.utils.config import settings

_SYSTEM = (
    "You are a strict technical recruiter and ATS expert. Score how well a tailored "
    "resume targets a specific job description. Be critical and consistent; reserve 5 "
    "for genuinely excellent, JD-aligned resumes. Respond with JSON only."
)

_RUBRIC = """Score each 1-5 (5 = best):
- relevance: how well the resume targets THIS job's stated requirements and responsibilities
- quality: professional writing — strong action verbs, quantified impact, clear and readable
- ats: uses the JD's important keywords/terminology where the resume content supports it
Also give an "overall" 1-5 and a one-sentence "rationale".
Return ONLY: {"relevance": int, "quality": int, "ats": int, "overall": int, "rationale": str}"""


async def judge_output(jd: str, tailored: str) -> dict | None:
    """Return the judge's scores, or None if disabled/empty, or {"error": ...} on failure."""
    if not tailored or not settings.openai_api_key:
        return None
    from openai import AsyncOpenAI

    client = AsyncOpenAI(api_key=settings.openai_api_key.get_secret_value())
    user = f"# Job Description\n{jd}\n\n# Tailored Resume\n{tailored}\n\n{_RUBRIC}"
    try:
        resp = await client.chat.completions.create(
            model=settings.openai_judge_model,
            messages=[{"role": "system", "content": _SYSTEM}, {"role": "user", "content": user}],
            response_format={"type": "json_object"},
            temperature=0,
        )
        data = json.loads(resp.choices[0].message.content or "{}")
    except Exception as e:  # never crash the eval on a judge hiccup
        return {"error": str(e)[:200]}
    return {k: data.get(k) for k in ("relevance", "quality", "ats", "overall", "rationale")}
