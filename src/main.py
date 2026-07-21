"""ResumeAgent CLI entry point.

Commands:
    resume-agent process <jd_file_or_text> [--url URL]   # tailor against local master_cv.md
    resume-agent interactive
    resume-agent search <keyword> [--location L] [--max-jobs N]
    resume-agent serve [--host HOST] [--port PORT] [--reload]
"""

import argparse
import asyncio
import sys
from pathlib import Path

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.prompt import Confirm, Prompt

from src.graph import WorkflowStatus, process_job

console = Console()


async def process_job_command(jd_source: str, url: str | None = None) -> int:
    jd_path = Path(jd_source)
    jd_text = jd_path.read_text(encoding="utf-8") if jd_path.exists() else jd_source

    console.print("\n[yellow]Processing job application...[/yellow]\n")
    result = await process_job(jd_text=jd_text, job_url=url)

    if result.parsed_jd:
        console.print(Panel(
            f"[bold]{result.parsed_jd.title}[/bold] at [cyan]{result.parsed_jd.company}[/cyan]",
            title="Job",
        ))
    if result.skill_match:
        score = result.skill_match.overall_score
        color = "green" if score >= 80 else "yellow" if score >= 60 else "orange3" if score >= 40 else "red"
        console.print(f"\nMatch Score: [{color}]{score}/100[/{color}] → {result.skill_match.recommendation.value.upper()}")
        console.print(f"Reasoning: {result.skill_match.reasoning}")
    if result.tailored_resume:
        console.print("\n[green]Resume tailored[/green]")
        if result.tailored_resume_path:
            console.print(f"  Saved to: {result.tailored_resume_path}")
    if result.cover_letter:
        console.print("[green]Cover letter generated[/green]")

    if result.status in (WorkflowStatus.PENDING_REVIEW, WorkflowStatus.SKIPPED):
        return 0
    console.print(f"\n[red]Status: {result.status.value}[/red]")
    for error in result.errors:
        console.print(f"  Error: {error}")
    return 1


async def search_command(keyword: str, location: str, max_jobs: int) -> int:
    from src import search as job_search

    console.print(f"\n[yellow]Searching '{keyword}' in {location}...[/yellow]\n")
    jobs = await job_search.search_jobs(keyword=keyword, location=location, max_jobs=max_jobs)
    console.print(f"[bold]{len(jobs)} jobs found[/bold]\n")
    for j in jobs[:max_jobs]:
        console.print(f"[cyan]{j['company']}[/cyan] — {j['title']}  [dim]({j['platform']})[/dim]")
    return 0


async def interactive_mode():
    console.print(Panel.fit(
        "[bold blue]ResumeAgent Interactive Mode[/bold blue]\nPaste a job description to get a tailored resume",
        border_style="blue",
    ))
    while True:
        console.print("\n[bold]Paste the job description (blank line when done):[/bold]")
        lines = []
        while True:
            try:
                line = input()
                if line == "" and lines:
                    break
                lines.append(line)
            except EOFError:
                break
        if not lines:
            if Confirm.ask("No input received. Exit?"):
                break
            continue

        result = await process_job(jd_text="\n".join(lines), job_url=Prompt.ask("Job URL (optional)", default="") or None)
        if result.parsed_jd:
            console.print(f"\n[bold]Company:[/bold] {result.parsed_jd.company}")
            console.print(f"[bold]Role:[/bold] {result.parsed_jd.title}")
        if result.skill_match:
            console.print(f"[bold]Match:[/bold] {result.skill_match.overall_score}/100 → {result.skill_match.recommendation.value}")
        if result.tailored_resume:
            console.print("\n[bold green]Tailored Resume:[/bold green]")
            console.print(Markdown(result.tailored_resume.markdown_content))
        if result.cover_letter:
            console.print("\n[bold green]Cover Letter:[/bold green]")
            console.print(result.cover_letter.content)
        if not Confirm.ask("\nProcess another job?"):
            break
    console.print("[dim]Goodbye![/dim]")


def main():
    parser = argparse.ArgumentParser(description="ResumeAgent - resume tailoring + job search")
    subparsers = parser.add_subparsers(dest="command", help="Commands")

    process_parser = subparsers.add_parser("process", help="Tailor against a JD (uses local master_cv.md)")
    process_parser.add_argument("jd_source", help="Path to JD file or JD text")
    process_parser.add_argument("--url", help="Job posting URL")

    subparsers.add_parser("interactive", help="Interactive mode")

    search_parser = subparsers.add_parser("search", help="Search jobs across platforms")
    search_parser.add_argument("keyword")
    search_parser.add_argument("--location", default="Singapore")
    search_parser.add_argument("--max-jobs", type=int, default=25)

    serve_parser = subparsers.add_parser("serve", help="Run the FastAPI backend")
    serve_parser.add_argument("--host", default="127.0.0.1")
    serve_parser.add_argument("--port", type=int, default=8000)
    serve_parser.add_argument("--reload", action="store_true")

    args = parser.parse_args()

    if args.command == "process":
        sys.exit(asyncio.run(process_job_command(args.jd_source, args.url)))
    elif args.command == "interactive":
        asyncio.run(interactive_mode())
    elif args.command == "search":
        sys.exit(asyncio.run(search_command(args.keyword, args.location, args.max_jobs)))
    elif args.command == "serve":
        import uvicorn
        uvicorn.run("src.api:app", host=args.host, port=args.port, reload=args.reload)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
