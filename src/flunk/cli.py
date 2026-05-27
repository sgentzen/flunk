"""Typer CLI entry for flunk."""

from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console

from flunk import demote as demote_mod
from flunk import detectors as detectors_mod
from flunk import rank as rank_mod
from flunk.runners import jscpd as jscpd_runner
from flunk.runners import semgrep as semgrep_runner

app = typer.Typer(
    no_args_is_help=True,
    help="A BS detector for AI-built Python code.",
    add_completion=False,
)
console = Console()


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
) -> None:
    """Audit a Python project for AI cut-corners."""
    try:
        findings = semgrep_runner.run(project)
    except semgrep_runner.SemgrepNotFound as e:
        console.print(f"[bold red]error:[/bold red] {e}")
        raise typer.Exit(code=2)
    except RuntimeError as e:
        console.print(f"[bold red]semgrep failed:[/bold red] {e}")
        raise typer.Exit(code=1)

    findings.extend(detectors_mod.run_all(project))
    findings.extend(jscpd_runner.run(project))

    if not no_demote:
        findings = demote_mod.demote(findings)

    findings = rank_mod.rank(findings)

    if json_out:
        rank_mod.render_json(findings)
    else:
        rank_mod.render_table(findings, top=top, console=console)
