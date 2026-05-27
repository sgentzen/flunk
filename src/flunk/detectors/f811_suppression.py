"""Rule #8: Function defs suppressed by per-file `F811` ruff/flake8
ignore. Almost always means "I have a duplicate def I don't want to
delete." Remove the duplicate, don't suppress the warning.

Expected fires: erate-prospector
"""

from __future__ import annotations

import re
from pathlib import Path

from flunk.catalog.metadata import lookup
from flunk.detectors._walk import walk_py
from flunk.findings import Finding

RULE_ID = "flunk.f811-suppression"
_F811_RE = re.compile(r"#\s*noqa\s*:.*\bF811\b", re.IGNORECASE)


def run(project: Path) -> list[Finding]:
    meta = lookup(RULE_ID)
    out: list[Finding] = []

    # Inline `# noqa: F811`
    for path in walk_py(project):
        try:
            for lineno, line in enumerate(
                path.read_text(encoding="utf-8", errors="replace").splitlines(),
                start=1,
            ):
                if _F811_RE.search(line):
                    out.append(
                        Finding(
                            rule_id=RULE_ID,
                            category=meta.category,
                            severity=meta.severity,
                            file=path,
                            line=lineno,
                            message=(
                                "F811 suppression — function redefinition is "
                                "silenced. Almost always means a duplicate def "
                                "should be deleted, not suppressed."
                            ),
                            replacement=meta.replacement,
                            replacement_url=meta.replacement_url,
                        )
                    )
        except OSError:
            continue

    # Per-file-ignores in pyproject.toml / ruff.toml
    for cfg in (project / "pyproject.toml", project / "ruff.toml", project / ".ruff.toml"):
        if not cfg.is_file():
            continue
        try:
            text = cfg.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for lineno, line in enumerate(text.splitlines(), start=1):
            # crude but works: any line that lists F811 in a per-file-ignore.
            if "F811" in line and "ignore" not in line.lower():
                # most ruff configs put F811 in a list under per-file-ignores
                # rather than the top-level `ignore = [...]`. Skip the latter
                # since that's a global blanket suppression with different
                # semantics.
                out.append(
                    Finding(
                        rule_id=RULE_ID,
                        category=meta.category,
                        severity=meta.severity,
                        file=cfg,
                        line=lineno,
                        message=(
                            "F811 in ruff per-file-ignores — silences function "
                            "redefinitions for a whole file. Delete the "
                            "duplicate def instead of suppressing."
                        ),
                        replacement=meta.replacement,
                        replacement_url=meta.replacement_url,
                    )
                )
    return out
