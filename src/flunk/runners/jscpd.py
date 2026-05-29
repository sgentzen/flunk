"""Subprocess wrapper around `jscpd` for within-project duplication.

Runs `jscpd --reporters json --silent <project>` and parses the
`jscpd-report.json` artifact into `Finding` objects. One finding per
clone pair, attributed to the FIRST occurrence so it's actionable.

Falls back gracefully (returns []) if jscpd / node is not installed —
duplication is a nice-to-have signal, not the core value.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from pathlib import Path

from flunk.catalog.metadata import lookup
from flunk.classify import NON_SOURCE_GLOBS
from flunk.findings import Finding

JSCPD_RULE_ID = "flunk.duplication"


def build_jscpd_cmd(
    cmd_prefix: list[str], project: Path, out_dir: Path, *, min_tokens: int
) -> list[str]:
    """Assemble the jscpd argv, ignoring non-source files.

    Templates, test fixtures, and test modules legitimately repeat structure;
    counting that as duplication is pure noise, so we exclude it at the source
    rather than filtering findings after the fact.
    """
    return [
        *cmd_prefix,
        "--min-tokens", str(min_tokens),
        "--reporters", "json",
        "--silent",
        "--ignore", ",".join(NON_SOURCE_GLOBS),
        "--output", str(out_dir),
        # Forward slashes, even on Windows: jscpd feeds this path to fast-glob,
        # which treats backslashes as escape chars, so a native C:\path matches
        # zero files and silently produces no duplication findings.
        project.as_posix(),
    ]


def _wrap_executable(path: str) -> list[str]:
    """Make a resolved executable runnable without a shell.

    On Windows, npm installs CLIs as `.cmd`/`.bat` shims. These are batch
    scripts, not real executables, so `CreateProcess` (what `subprocess` uses
    with a list argv and no shell) raises FileNotFoundError on them. They must
    be invoked through `cmd /c`. POSIX executables are run directly.
    """
    if path.lower().endswith((".cmd", ".bat")):
        return ["cmd", "/c", path]
    return [path]


def resolve_cmd_prefix() -> list[str] | None:
    """Resolve how to invoke jscpd, or None if neither jscpd nor npx exists.

    Prefer a globally installed jscpd; fall back to `npx --yes jscpd`. We use
    the *resolved* path from `shutil.which` (not a bare name) so the `.cmd`
    shim wrapping in `_wrap_executable` can take effect on Windows.
    """
    jscpd = shutil.which("jscpd")
    if jscpd:
        return _wrap_executable(jscpd)
    npx = shutil.which("npx")
    if npx:
        return [*_wrap_executable(npx), "--yes", "jscpd"]
    return None


def run(project: Path, *, min_tokens: int = 50) -> list[Finding]:
    """Run jscpd. Returns [] if jscpd or node is unavailable."""
    cmd_prefix = resolve_cmd_prefix()
    if cmd_prefix is None:
        return []

    with tempfile.TemporaryDirectory() as tmp:
        out_dir = Path(tmp)
        cmd = build_jscpd_cmd(cmd_prefix, project, out_dir, min_tokens=min_tokens)
        try:
            subprocess.run(
                cmd, capture_output=True, text=True, encoding="utf-8",
                errors="replace", check=False, timeout=300,
            )
        except (OSError, subprocess.TimeoutExpired):
            return []
        report = out_dir / "jscpd-report.json"
        if not report.is_file():
            return []
        try:
            payload = json.loads(report.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return []

    meta = lookup(JSCPD_RULE_ID)
    findings: list[Finding] = []
    for dup in payload.get("duplicates", []):
        first = dup.get("firstFile", {})
        second = dup.get("secondFile", {})
        path = first.get("name") or first.get("path")
        if not path:
            continue
        lines = int(dup.get("lines") or 0)
        tokens = int(dup.get("tokens") or 0)
        findings.append(
            Finding(
                rule_id=JSCPD_RULE_ID,
                category=meta.category,
                severity=meta.severity,
                file=Path(path),
                line=int(first.get("startLoc", {}).get("line", first.get("start", 1)) or 1),
                message=(
                    f"Duplicated block ({lines} lines, {tokens} tokens) — also at "
                    f"{second.get('name') or second.get('path', '?')}:"
                    f"{second.get('startLoc', {}).get('line', second.get('start', '?'))}. "
                    f"Extract a shared helper."
                ),
                replacement=meta.replacement,
                replacement_url=meta.replacement_url,
            )
        )
    return findings
