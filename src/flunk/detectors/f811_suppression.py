"""Rule #8: Function defs suppressed by per-file `F811` ruff/flake8
ignore. Almost always means "I have a duplicate def I don't want to
delete." Remove the duplicate, don't suppress the warning.

Expected fires: erate-prospector
"""

from __future__ import annotations

import re
from pathlib import Path

from flunk.catalog.metadata import RuleMeta, lookup
from flunk.detectors._source import iter_comments
from flunk.detectors._walk import walk_py
from flunk.findings import Finding

RULE_ID = "flunk.f811-suppression"
# Anchored to the start of a real comment: a `# noqa: F811` directive *is* the
# comment. Prose that merely quotes one (`# Inline \`# noqa: F811\``) or a
# string literal that contains the text is not a suppression and must not fire.
# Tradeoff: a noqa that isn't first in its comment (e.g. a stacked
# `# type: ignore  # noqa: F811`) is intentionally not matched — we favor
# precision over that rare case. The per-file-ignore config path below is
# unaffected and remains the rule's primary trigger.
_F811_RE = re.compile(r"^#\s*noqa\s*:.*\bF811\b", re.IGNORECASE)


_INLINE_MESSAGE = (
    "F811 suppression — function redefinition is silenced. Almost always "
    "means a duplicate def should be deleted, not suppressed."
)
_CONFIG_MESSAGE = (
    "F811 in ruff per-file-ignores — silences function redefinitions for a "
    "whole file. Delete the duplicate def instead of suppressing."
)


def _read(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def _finding(meta: RuleMeta, file: Path, line: int, message: str) -> Finding:
    return Finding(
        rule_id=RULE_ID,
        category=meta.category,
        severity=meta.severity,
        file=file,
        line=line,
        message=message,
        replacement=meta.replacement,
        replacement_url=meta.replacement_url,
    )


def _inline_hits(project: Path, meta: RuleMeta) -> list[Finding]:
    """Inline `# noqa: F811` directives in the project's Python source."""
    out: list[Finding] = []
    for path in walk_py(project):
        source = _read(path)
        if source is None:
            continue
        out.extend(
            _finding(meta, path, lineno, _INLINE_MESSAGE)
            for lineno, comment in iter_comments(source)
            if _F811_RE.search(comment)
        )
    return out


def _lists_f811_per_file(line: str) -> bool:
    """Crude but works: any config line that lists F811 in a per-file-ignore.

    Most ruff configs put F811 in a list under per-file-ignores rather than the
    top-level `ignore = [...]`. Skip the latter since that's a global blanket
    suppression with different semantics.
    """
    return "F811" in line and "ignore" not in line.lower()


def _config_hits(project: Path, meta: RuleMeta) -> list[Finding]:
    """Per-file-ignores in pyproject.toml / ruff.toml."""
    out: list[Finding] = []
    for cfg in (project / "pyproject.toml", project / "ruff.toml", project / ".ruff.toml"):
        if not cfg.is_file():
            continue
        text = _read(cfg)
        if text is None:
            continue
        out.extend(
            _finding(meta, cfg, lineno, _CONFIG_MESSAGE)
            for lineno, line in enumerate(text.splitlines(), start=1)
            if _lists_f811_per_file(line)
        )
    return out


def run(project: Path) -> list[Finding]:
    meta = lookup(RULE_ID)
    return _inline_hits(project, meta) + _config_hits(project, meta)
