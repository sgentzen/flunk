"""Justification-aware demote pass.

For every finding, look for a justification in order of specificity: the N
lines above and below (comment markers), then the enclosing function/class
docstring, then the module docstring. If any of those contain a configured
marker phrase, demote severity one tier.
"""

from __future__ import annotations

import ast
import re
from functools import lru_cache
from pathlib import Path

from flunk.findings import Finding

CONTEXT_LINES = 3
DEMOTE_TIER = {"high": "medium", "medium": "nitpick", "nitpick": "suppressed"}

# The justification phrases. Used two ways: anchored to `#` for nearby
# comments (so a string literal like "we deliberately fail" doesn't match),
# and unanchored for the module docstring (a deliberate string, where the
# author is documenting a project-/module-level design choice).
JUSTIFICATION_PHRASES: list[str] = [
    "deliberately",
    "intentionally",
    "we chose",
    "fall back",
    "rather than",
    "tradeoff",
    "justified",
    "on purpose",
]
_MARKER_RE = re.compile(
    "|".join(rf"#.*{p}" for p in JUSTIFICATION_PHRASES), re.IGNORECASE
)
_DOCSTRING_RE = re.compile("|".join(JUSTIFICATION_PHRASES), re.IGNORECASE)

# Back-compat alias: the comment-anchored patterns were previously exposed
# as MARKERS (and mirrored in CATALOG.md).
MARKERS: list[str] = [rf"#.*{p}" for p in JUSTIFICATION_PHRASES]


@lru_cache(maxsize=2048)
def _read_lines(path: Path) -> tuple[str, ...]:
    try:
        return tuple(path.read_text(encoding="utf-8", errors="replace").splitlines())
    except OSError:
        return ()


@lru_cache(maxsize=2048)
def _module_docstring(path: Path) -> str | None:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
    except (OSError, SyntaxError):
        return None
    return ast.get_docstring(tree)


@lru_cache(maxsize=2048)
def _scope_docstrings(path: Path) -> tuple[tuple[int, int, str], ...]:
    """Docstrings of every function/class in the file, with their line spans.

    Returns ``(start_line, end_line, docstring)`` tuples (1-indexed, inclusive)
    for each ``def``/``async def``/``class`` that has a docstring. A justification
    in a function or class docstring documents a scope-level design choice — the
    same intent a module docstring carries, but narrower — so findings inside
    that scope should be demoted too.
    """
    try:
        tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
    except (OSError, SyntaxError):
        return ()
    spans: list[tuple[int, int, str]] = []
    for node in ast.walk(tree):
        if isinstance(
            node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
        ):
            docstring = ast.get_docstring(node)
            if docstring and node.end_lineno is not None:
                # `node.lineno` is the `def`/`class` line; decorators sit above
                # it. Start the span at the earliest decorator so a finding on a
                # decorator line is still covered by the scope's justification.
                start = min(
                    (d.lineno for d in node.decorator_list),
                    default=node.lineno,
                )
                spans.append((start, node.end_lineno, docstring))
    return tuple(spans)


def _find_marker(path: Path, line: int) -> str | None:
    """Return the matched justification phrase, or None.

    Looks, in order of specificity: comments within +-CONTEXT_LINES of the
    finding, then the enclosing function/class docstring (innermost first), then
    the module docstring (a module-level justification applies to the whole file).
    """
    lines = _read_lines(path)
    if not lines:
        return None
    # 1-indexed lines; convert and clamp.
    idx = max(0, line - 1)
    start = max(0, idx - CONTEXT_LINES)
    end = min(len(lines), idx + CONTEXT_LINES + 1)
    window = "\n".join(lines[start:end])
    m = _MARKER_RE.search(window)
    if m:
        return m.group(0).strip()

    # Enclosing function/class docstrings, innermost (smallest span) first so the
    # most specific rationale is the one reported.
    enclosing = sorted(
        (
            (span_end - span_start, docstring)
            for span_start, span_end, docstring in _scope_docstrings(path)
            if span_start <= line <= span_end
        ),
        key=lambda item: item[0],
    )
    for _, docstring in enclosing:
        dm = _DOCSTRING_RE.search(docstring)
        if dm:
            return f"docstring: …{dm.group(0)}…"

    module_docstring = _module_docstring(path)
    if module_docstring:
        dm = _DOCSTRING_RE.search(module_docstring)
        if dm:
            return f"module docstring: …{dm.group(0)}…"
    return None


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
