"""Opt-in LLM judge: rewrite rationale + re-rate severity per call site.

The judge takes findings that survived demote/profile/decisions and asks an
LLM whether each one actually matters *here*, with the surrounding code. It
returns enriched findings (code-specific rationale, re-rated severity, possibly
a `skip` verdict for "located but not worth doing").

All logic here is client-agnostic: a `JudgeClient` is injected. The Anthropic
implementation lives in `judge_anthropic.py`. A guardrail forbids downgrading or
skipping security/correctness rules (see metadata.SECURITY_RULES).
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from flunk.catalog import metadata
from flunk.findings import SEVERITY_ORDER, Finding

CONTEXT_LINES = 6
_JUDGE_SEVERITIES = frozenset({"high", "medium", "nitpick", "skip"})


@dataclass(frozen=True)
class JudgeItem:
    """One finding presented to the LLM."""
    rule_id: str
    line: int
    catalog_severity: str
    catalog_rationale: str | None
    excerpt: str
    is_security: bool


@dataclass(frozen=True)
class Verdict:
    severity: str
    rationale: str
    worth_doing: bool


class JudgeClient(Protocol):
    def judge_file(self, rel_path: str, items: list[JudgeItem]) -> list[Verdict]: ...


def _excerpt(file: Path, line: int, context: int = CONTEXT_LINES) -> str:
    try:
        lines = file.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return ""
    idx = line - 1
    lo, hi = max(0, idx - context), min(len(lines), idx + context + 1)
    out = []
    for i in range(lo, hi):
        marker = ">>" if i == idx else "  "
        out.append(f"{marker} {i + 1}  {lines[i]}")
    return "\n".join(out)


def _rel(file: Path, root: Path | None) -> str:
    if root is not None:
        try:
            return str(file.relative_to(root)).replace("\\", "/")
        except ValueError:
            pass
    return str(file)


def _clamp_security(verdict: Verdict, catalog_severity: str) -> Verdict:
    """Security rules: never lower severity, never skip; rationale may change.

    Lower severity = higher SEVERITY_ORDER int. If the judge's severity is
    *less* severe than the catalog's (a higher int) or a `skip`, revert to the
    catalog severity. A raise (lower int) is allowed through.
    """
    sev = verdict.severity
    if sev == "skip" or SEVERITY_ORDER.get(sev, 99) > SEVERITY_ORDER[catalog_severity]:
        sev = catalog_severity
    return Verdict(severity=sev, rationale=verdict.rationale, worth_doing=verdict.worth_doing)


def judge_findings(
    findings: list[Finding],
    *,
    client: JudgeClient,
    project_root: Path | None = None,
) -> list[Finding]:
    """Return findings enriched by the judge. Suppressed findings pass through."""
    judgeable = [f for f in findings if f.severity != "suppressed"]
    passthrough = {id(f): f for f in findings if f.severity == "suppressed"}

    by_file: dict[Path, list[Finding]] = defaultdict(list)
    for f in judgeable:
        by_file[f.file].append(f)

    enriched: dict[int, Finding] = {}
    for file, group in by_file.items():
        items = [
            JudgeItem(
                rule_id=f.rule_id,
                line=f.line,
                catalog_severity=f.severity,
                catalog_rationale=metadata.lookup(f.rule_id).rationale,
                excerpt=_excerpt(file, f.line),
                is_security=metadata.is_security_rule(f.rule_id),
            )
            for f in group
        ]
        verdicts = client.judge_file(str(file), items)
        for f, verdict in zip(group, verdicts, strict=True):
            sev = verdict.severity if verdict.severity in _JUDGE_SEVERITIES else f.severity
            v = Verdict(sev, verdict.rationale, verdict.worth_doing)
            if metadata.is_security_rule(f.rule_id):
                v = _clamp_security(v, f.severity)
            enriched[id(f)] = f.with_judgment(
                severity=v.severity, rationale=v.rationale, worth_doing=v.worth_doing
            )

    return [enriched.get(id(f)) or passthrough.get(id(f)) or f for f in findings]
