"""Justification-aware demote pass.

For every finding, read N lines above and N lines below in the source
file. If the locality contains any of the configured marker phrases,
demote severity one tier.
"""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

from flunk.findings import Finding

CONTEXT_LINES = 3
DEMOTE_TIER = {"high": "medium", "medium": "nitpick", "nitpick": "suppressed"}

# Case-insensitive; matched inside a comment context. Anchored to the
# `#` so we don't accidentally demote on a string literal containing
# "fall back" (e.g. an error message).
MARKERS: list[str] = [
    r"#.*deliberately",
    r"#.*intentionally",
    r"#.*we chose",
    r"#.*fall back",
    r"#.*rather than",
    r"#.*tradeoff",
    r"#.*justified",
    r"#.*on purpose",
]
_MARKER_RE = re.compile("|".join(MARKERS), re.IGNORECASE)


@lru_cache(maxsize=2048)
def _read_lines(path: Path) -> tuple[str, ...]:
    try:
        return tuple(path.read_text(encoding="utf-8", errors="replace").splitlines())
    except OSError:
        return ()


def _find_marker(path: Path, line: int) -> str | None:
    """Return the matched marker phrase, or None."""
    lines = _read_lines(path)
    if not lines:
        return None
    # 1-indexed lines; convert and clamp.
    idx = max(0, line - 1)
    start = max(0, idx - CONTEXT_LINES)
    end = min(len(lines), idx + CONTEXT_LINES + 1)
    window = "\n".join(lines[start:end])
    m = _MARKER_RE.search(window)
    return m.group(0).strip() if m else None


def demote(findings: list[Finding]) -> list[Finding]:
    """Return a new list, with eligible findings demoted (or suppressed)."""
    out: list[Finding] = []
    for f in findings:
        marker = _find_marker(f.file, f.line)
        if not marker:
            out.append(f)
            continue
        next_tier = DEMOTE_TIER.get(f.severity, "suppressed")
        if next_tier == "suppressed":
            # Drop the finding entirely.
            continue
        out.append(f.with_demote(next_tier, marker))
    return out
