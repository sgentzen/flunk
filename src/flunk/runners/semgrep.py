"""Subprocess wrapper around the `semgrep` CLI.

Runs flunk's curated catalog (YAML files in `flunk/catalog/patterns/`)
against a target project and returns a flat list of `Finding` objects.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

from flunk.catalog import PATTERNS_DIR, post_process
from flunk.catalog.metadata import lookup
from flunk.findings import Finding


class SemgrepNotFound(RuntimeError):
    """Raised when the `semgrep` CLI is not on PATH."""


def _semgrep_path() -> str:
    exe = shutil.which("semgrep")
    if not exe:
        raise SemgrepNotFound(
            "semgrep not found on PATH. Install with: `pipx install semgrep` "
            "or `uv tool install semgrep`."
        )
    return exe


def run(
    project: Path,
    *,
    patterns_dir: Path | None = None,
    extra_args: list[str] | None = None,
) -> list[Finding]:
    """Run semgrep over `project` using the flunk catalog. Returns Findings."""
    semgrep = _semgrep_path()
    config = str(patterns_dir or PATTERNS_DIR)
    cmd = [
        semgrep,
        "scan",
        "--config", config,
        "--json",
        "--quiet",
        "--metrics=off",
        "--disable-version-check",
        *(extra_args or []),
        str(project),
    ]
    # Don't redirect stderr on Windows / PowerShell — semgrep writes a banner
    # to stderr that's harmless. Capture both, but only fail on non-zero exit
    # AND empty stdout.
    completed = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if not completed.stdout.strip():
        raise RuntimeError(
            f"semgrep produced no JSON output (exit {completed.returncode}).\n"
            f"stderr:\n{completed.stderr[-2000:]}"
        )
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError as e:
        raise RuntimeError(
            f"Could not parse semgrep JSON (exit {completed.returncode}): {e}\n"
            f"first 500 chars: {completed.stdout[:500]!r}"
        ) from e

    raw_findings = [_parse_match(m) for m in payload.get("results", [])]
    return post_process(raw_findings)


def _parse_match(match: dict[str, Any]) -> Finding:
    rule_id = match["check_id"]
    # Semgrep prefixes check_id with the config dir when --config points at
    # a directory; strip everything before the last `.` so we keep our
    # canonical "flunk.pydantic-settings" form.
    if "." in rule_id:
        # Keep last two segments (e.g. "patterns.flunk.pydantic-settings"
        # → "flunk.pydantic-settings"), unless there are <2.
        parts = rule_id.split(".")
        if len(parts) >= 2:
            rule_id = ".".join(parts[-2:])
    meta = lookup(rule_id)
    return Finding(
        rule_id=rule_id,
        category=meta.category,
        severity=meta.severity,
        file=Path(match["path"]),
        line=int(match["start"]["line"]),
        message=match["extra"].get("message", "").strip().replace("\n", " "),
        replacement=meta.replacement,
        replacement_url=meta.replacement_url,
    )
