"""Typer CLI entry for flunk."""

from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console

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
    """Audit a Python project for AI cut-corners.

    Wraps semgrep + jscpd, layers a curated catalog of reinvented-wheel
    patterns on top, demotes findings near justification comments, then
    prints a ranked report.
    """
    console.print(f"[bold]flunk[/bold] auditing [cyan]{project}[/cyan]")
    console.print(f"  --json      {json_out}")
    console.print(f"  --top       {top}")
    console.print(f"  --no-demote {no_demote}")
    console.print()
    console.print("[yellow]Pipeline not yet implemented — this is a wiring stub.[/yellow]")
    console.print("[dim]Next: src/flunk/findings.py + src/flunk/runners/semgrep.py[/dim]")
