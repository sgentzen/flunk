"""Common Finding schema shared across runners and the demote/rank pipeline."""

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

    def with_judgment(
        self, *, severity: str, rationale: str, worth_doing: bool
    ) -> Finding:
        return replace(
            self,
            severity=severity,
            raw_severity=self.raw_severity or self.severity,
            rationale=rationale,
            judged=True,
        )
