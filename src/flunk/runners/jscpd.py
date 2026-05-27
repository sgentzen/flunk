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
from flunk.findings import Finding

JSCPD_RULE_ID = "flunk.duplication"


def run(project: Path, *, min_tokens: int = 50) -> list[Finding]:
    """Run jscpd. Returns [] if jscpd or node is unavailable."""
    # Prefer a globally installed jscpd; fall back to `npx --yes jscpd`.
    cmd_prefix: list[str]
    if shutil.which("jscpd"):
        cmd_prefix = ["jscpd"]
    elif shutil.which("npx"):
        cmd_prefix = ["npx", "--yes", "jscpd"]
    else:
        return []

    with tempfile.TemporaryDirectory() as tmp:
        out_dir = Path(tmp)
        cmd = [
            *cmd_prefix,
            "--min-tokens", str(min_tokens),
            "--reporters", "json",
            "--silent",
            "--output", str(out_dir),
            str(project),
        ]
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
