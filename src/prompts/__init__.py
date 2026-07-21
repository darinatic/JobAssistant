"""Versioned prompt registry.

Importing this package side-effect-registers every named prompt. Agents and
service-layer LLM call sites resolve their active prompt via::

    from src.prompts import get_prompt

    prompt = get_prompt("cover_letter")
    response = await llm.ainvoke([SystemMessage(content=prompt.text), ...])

Override the active version at runtime without touching code::

    PROMPT_OVERRIDES=cover_letter=v2,resume_tailor=v3
"""

# Side-effect imports: every module here registers its prompt versions.
from src.prompts import (  # noqa: F401
    cover_letter,
    jd_parser,
    resume_tailor,
)
from src.prompts.registry import (
    Prompt,
    all_active,
    get_prompt,
    list_versions,
    register,
)

__all__ = ["Prompt", "all_active", "get_prompt", "list_versions", "register"]
