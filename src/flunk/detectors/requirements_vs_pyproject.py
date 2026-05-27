"""Rule #3: pyproject.toml exists with no [project.dependencies] while
requirements.txt / *.in declares deps. Consolidate to pyproject + uv pip
compile lockfile.

Expected fires: erate-filing-assistant, erate-prospector
"""

from __future__ import annotations

import re
from pathlib import Path

from flunk.catalog.metadata import lookup
from flunk.findings import Finding

RULE_ID = "flunk.uv-pip-compile"
_DEPS_RE = re.compile(r"^\s*dependencies\s*=", re.MULTILINE)


def run(project: Path) -> list[Finding]:
    pyproject = project / "pyproject.toml"
    if not pyproject.is_file():
        return []
    requirements = [
        p for p in (
            project / "requirements.txt",
            project / "requirements.in",
            project / "requirements-dev.txt",
            project / "requirements-dev.in",
        )
        if p.is_file()
    ]
    if not requirements:
        return []
    try:
        content = pyproject.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    if _DEPS_RE.search(content):
        # pyproject already declares dependencies; not the smell.
        return []
    meta = lookup(RULE_ID)
    req_list = ", ".join(p.name for p in requirements)
    return [
        Finding(
            rule_id=RULE_ID,
            category=meta.category,
            severity=meta.severity,
            file=pyproject,
            line=1,
            message=(
                f"pyproject.toml has no [project] dependencies but "
                f"{req_list} declares deps. Consolidate to pyproject + "
                f"`uv pip compile` lockfile."
            ),
            replacement=meta.replacement,
            replacement_url=meta.replacement_url,
        )
    ]
