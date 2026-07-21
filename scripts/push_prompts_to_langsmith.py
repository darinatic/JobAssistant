"""Dev tool: push the in-repo registry prompts to LangSmith Hub.

So engineers can edit/version prompts in the LangSmith playground and have the
app pull them at runtime (set ``LANGSMITH_PROMPT_REFS=resume_tailor=<owner>/resume_tailor,...``).
The in-repo registry stays the source of truth + offline fallback; this just
seeds the Hub from the shipped prompts.

Requires ``LANGSMITH_API_KEY``. Run::

    .venv/Scripts/python.exe -m scripts.push_prompts_to_langsmith [--owner me]
"""

from __future__ import annotations

import argparse

import src.prompts  # noqa: F401  — side-effect: registers every prompt
from src.prompts import all_active


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--owner", default="-",
                        help="LangSmith handle to push under (default '-' = your private workspace)")
    args = parser.parse_args()

    from langchain_core.prompts import ChatPromptTemplate
    from langsmith import Client

    client = Client()
    for name, prompt in all_active().items():
        ref = f"{args.owner}/{name}" if args.owner and args.owner != "-" else name
        template = ChatPromptTemplate.from_messages([("system", prompt.text)])
        url = client.push_prompt(ref, object=template)
        print(f"pushed {name} (v{prompt.version}, sha {prompt.sha256}) -> {url}")


if __name__ == "__main__":
    main()
