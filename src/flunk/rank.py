"""Ranking + rendering of findings.

Sort order: severity desc, category (oss-catalog > duplication >
anti-pattern), then file path. Render via `rich` table or JSON.
"""

from __future__ import annotations

import json
import sys

from rich.console import Console
from rich.table import Table

from flunk.findings import CATEGORY_ORDER, SEVERITY_ORDER, Finding

SEVERITY_STYLE = {
    "high": "bold red",
    "medium": "yellow",
    "nitpick": "dim",
    "skip": "dim italic",
    "suppressed": "dim strike",
}


def rank(findings: list[Finding]) -> list[Finding]:
    """Sort by severity desc, then category, then file path."""
    return sorted(
        findings,
        key=lambda f: (
            SEVERITY_ORDER.get(f.severity, 99),
            CATEGORY_ORDER.get(f.category, 99),
            str(f.file),
            f.line,
        ),
    )


def render_table(findings: list[Finding], *, top: int, console: Console) -> None:
    table = Table(
        title=f"flunk findings ({len(findings)} total, showing top {min(top, len(findings))})",
        show_lines=False,
        header_style="bold",
    )
    table.add_column("sev", no_wrap=True)
    table.add_column("category", no_wrap=True)
    table.add_column("file:line", overflow="fold")
    table.add_column("message", overflow="fold")
    table.add_column("replacement", overflow="fold")
    for f in findings[:top]:
        style = SEVERITY_STYLE.get(f.severity, "")
        sev_cell = f"[{style}]{f.severity}[/{style}]" if style else f.severity
        loc = f"{f.file}:{f.line}"
        msg = f.rationale or f.message
        if f.severity == "skip":
            msg = f"[skip — not worth doing] {msg}"
        if f.demoted_by:
            msg = f"{msg} [dim](demoted: {f.demoted_by})[/dim]"
        table.add_row(sev_cell, f.category, loc, msg, f.replacement or "")
    console.print(table)


def render_json(findings: list[Finding]) -> None:
    json.dump([f.to_json() for f in findings], sys.stdout, indent=2)
    sys.stdout.write("\n")
