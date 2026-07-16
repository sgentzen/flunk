"""Common Finding schema, plus path rendering, shared across runners and the
demote/rank pipeline."""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any

SEVERITY_ORDER = {"high": 0, "medium": 1, "nitpick": 2, "skip": 3, "suppressed": 4}
CATEGORY_ORDER = {"oss-catalog": 0, "duplication": 1, "anti-pattern": 2}


@dataclass(frozen=True)
class Finding:
    rule_id: str
    category: str
    severity: str
    file: Path
    line: int
    message: str
    replacement: str | None = None
    replacement_url: str | None = None
    raw_severity: str | None = None
    demoted_by: str | None = None
    judged: bool = False
    rationale: str | None = None

    def to_json(self) -> dict[str, Any]:
        d = asdict(self)
        d["file"] = str(self.file)
        return d

    def with_demote(self, new_severity: str, marker: str) -> Finding:
        return replace(
            self,
            severity=new_severity,
            raw_severity=self.raw_severity or self.severity,
            demoted_by=marker,
        )

    def with_message(self, new_message: str) -> Finding:
        return replace(self, message=new_message)

    def with_judgment(self, *, severity: str, rationale: str) -> Finding:
        # A `skip` severity already encodes the judge's "not worth doing", so the
        # verdict's worth_doing flag is deliberately not stored separately.
        return replace(
            self,
            severity=severity,
            raw_severity=self.raw_severity or self.severity,
            rationale=rationale,
            judged=True,
        )


def display_path(file: Path, root: Path | None) -> str:
    """Render a finding's path for display: relative to `root`, forward-slashed.

    Separators are normalized so output is identical on Windows and POSIX.
    Falls back to the absolute path when `root` is None or `file` sits outside
    it (`relative_to` raises ValueError rather than walking up with `..`).
    """
    if root is not None:
        try:
            return str(file.relative_to(root)).replace("\\", "/")
        except ValueError:
            pass
    return str(file)
