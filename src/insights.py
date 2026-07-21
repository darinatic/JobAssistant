"""Stateless insights over a set of found jobs.

No LLM, no persistence: given the jobs the client already holds (a search
result set) and optionally the candidate's CV, aggregate skill demand and show
where the candidate stands. Reuses the gazetteer so "what's in demand" is
deterministic and free.
"""

from collections import Counter

from src.matching import extract_skills, rough_relevance


def aggregate_jobs(jobs: list[dict], master_cv: str | None = None, top_n: int = 15) -> dict:
    n = len(jobs)
    cv_skills = extract_skills(master_cv) if master_cv else set()

    demand: Counter[str] = Counter()
    for j in jobs:
        text = f"{j.get('description') or ''} {j.get('title') or ''}"
        demand.update(extract_skills(text))

    demanded_skills = [
        {
            "skill": skill,
            "count": count,
            "pct": round(100 * count / n) if n else 0,
            "candidate_has": skill in cv_skills,
        }
        for skill, count in demand.most_common(top_n)
    ]

    # Coverage: how well the CV matches this result set, when a CV is given.
    coverage = None
    if master_cv and n:
        rels = [rough_relevance(f"{j.get('description') or ''} {j.get('title') or ''}", master_cv) for j in jobs]
        coverage = {
            "avg_relevance": round(sum(rels) / len(rels)),
            "strong_matches": sum(1 for r in rels if r >= 60),  # jobs you match >= 60%
        }

    # Salary range across jobs that disclose one.
    mins = [j["salary_min"] for j in jobs if j.get("salary_min")]
    maxs = [j["salary_max"] for j in jobs if j.get("salary_max")]
    salary = {"min": min(mins) if mins else None, "max": max(maxs) if maxs else None,
              "disclosed": len(mins) + len(maxs)} if (mins or maxs) else None

    platforms = [{"platform": p, "count": c} for p, c in Counter(j.get("platform", "?") for j in jobs).most_common()]

    return {
        "job_count": n,
        "demanded_skills": demanded_skills,
        "your_strengths": [d["skill"] for d in demanded_skills if d["candidate_has"]],
        "your_gaps": [d["skill"] for d in demanded_skills if not d["candidate_has"]],
        "coverage": coverage,
        "platforms": platforms,
        "salary": salary,
    }
