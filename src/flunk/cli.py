"""Typer CLI entry for flunk."""

from __future__ import annotations

import sys
from pathlib import Path

import typer
from rich.console import Console

from flunk import agent as agent_mod
from flunk import decisions as decisions_mod
from flunk import demote as demote_mod
from flunk import detectors as detectors_mod
from flunk import judge as judge_mod
from flunk import profile as profile_mod
from flunk import rank as rank_mod
from flunk.runners import jscpd as jscpd_runner
from flunk.runners import semgrep as semgrep_runner

app = typer.Typer(
    no_args_is_help=True,
    help="A BS detector for AI-built Python code.",
    add_completion=False,
)
console = Console()
# Status spinner goes to stderr so --json (and piped) stdout stays clean.
err_console = Console(stderr=True)


def _build_judge_client(model: str):
    """Construct the Anthropic-backed judge client (kept here so tests can stub it)."""
    from flunk.judge_anthropic import AnthropicJudgeClient

    return AnthropicJudgeClient(model=model)


@app.command()
def audit(
    project: Path = typer.Argument(
        ...,
        help="Path to the Python project to audit.",
        exists=True,
        file_okay=False,
        dir_okay=True,
        resolve_path=True,
    ),
    json_out: bool = typer.Option(
        False,
        "--json",
        help="Emit findings as JSON instead of a rich table.",
    ),
    agent_out: bool = typer.Option(
        False,
        "--agent",
        help="Emit an agent-actionable markdown fix plan grouped by rule.",
    ),
    top: int = typer.Option(
        25,
        "--top",
        help="Max findings to render.",
        min=1,
    ),
    no_demote: bool = typer.Option(
        False,
        "--no-demote",
        help="Disable the justification-aware demote pass.",
    ),
    profile: str = typer.Option(
        "auto",
        "--profile",
        help=(
            "Project profile: auto | single-user-local | web-service | unknown. "
            "A single-user-local project down-weights infra rules (alembic, "
            "pydantic-settings, csrf, secure-headers) by one tier."
        ),
    ),
    judge: bool = typer.Option(
        False,
        "--judge",
        help="Send findings to an LLM to re-rate severity and rewrite rationale "
             "for the specific code (needs `pip install 'flunk[judge]'` + "
             "ANTHROPIC_API_KEY). Off by default; the static pipeline is unchanged.",
    ),
    judge_model: str = typer.Option(
        "claude-sonnet-4-6",
        "--judge-model",
        help="Model for the --judge pass.",
    ),
) -> None:
    """Audit a Python project for AI cut-corners."""
    with err_console.status("[bold]Auditing…", spinner="dots") as status:
        status.update("[bold]Running semgrep catalog rules…")
        try:
            findings = semgrep_runner.run(project)
        except semgrep_runner.SemgrepNotFound as e:
            status.stop()
            console.print(f"[bold red]error:[/bold red] {e}")
            raise typer.Exit(code=2)
        except RuntimeError as e:
            status.stop()
            console.print(f"[bold red]semgrep failed:[/bold red] {e}")
            raise typer.Exit(code=1)

        status.update("[bold]Running custom detectors…")
        findings.extend(detectors_mod.run_all(project))

        status.update("[bold]Scanning for duplication (jscpd)…")
        findings.extend(jscpd_runner.run(project))

        if not no_demote:
            status.update("[bold]Demoting justified findings…")
            findings = demote_mod.demote(findings)

        status.update("[bold]Applying project profile…")
        try:
            resolved_profile = profile_mod.resolve_profile(project, profile)
        except ValueError as e:
            status.stop()
            console.print(f"[bold red]error:[/bold red] {e}")
            raise typer.Exit(code=2)
        findings = profile_mod.apply_profile(findings, resolved_profile)

        status.update("[bold]Applying .flunkignore decisions…")
        findings = decisions_mod.apply_decisions(
            findings, decisions_mod.load_decisions(project)
        )

        if judge:
            status.update("[bold]Judging findings with the LLM…")
            try:
                client = _build_judge_client(judge_model)
            except RuntimeError as e:
                status.stop()
                console.print("[bold red]error:[/bold red] ", end="")
                console.print(str(e), markup=False)
                raise typer.Exit(code=2)
            findings = judge_mod.judge_findings(
                findings, client=client, project_root=project
            )

        status.update("[bold]Ranking findings…")
        findings = rank_mod.rank(findings)

    if not json_out and not agent_out:
        err_console.print(f"[dim]project profile: {resolved_profile.value}[/dim]")

    if agent_out:
        # The plan is UTF-8 markdown (emoji, arrows); Windows' default cp1252
        # stdout can't encode it, so emit UTF-8 explicitly.
        plan = agent_mod.build_plan(findings, project_root=project)
        sys.stdout.buffer.write(plan.encode("utf-8"))
    elif json_out:
        rank_mod.render_json(findings)
    else:
        rank_mod.render_table(findings, top=top, console=console)
