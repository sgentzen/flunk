"""`.flunkignore`: a project's conscious 'won't do' decisions, per rule.

Some findings are real patterns the maintainer has deliberately decided not to
act on for this project (e.g. "alembic is overkill for a single-user local
app"). Rather than silently dropping them, a maintainer records the decision —
and ideally a reason — in a `.flunkignore` file at the project root. Matching
findings are suppressed but kept in the output with that reason attached, so
the audit still shows the choice was made on purpose.

Format (one decision per line)::

    # comments and blank lines are ignored
    flunk.alembic: single-user local app, additive migrations are deliberate
    flunk.csrf-middleware            # a reason is optional
"""

from __future__ import annotations

from pathlib import Path

from flunk.findings import Finding

FLUNKIGNORE = ".flunkignore"
_SUPPRESSED = "suppressed"


def load_decisions(project: Path) -> dict[str, str]:
    """Parse `<project>/.flunkignore` into {rule_id: reason}. {} if absent."""
    path = project / FLUNKIGNORE
    if not path.is_file():
        return {}
    decisions: dict[str, str] = {}
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return {}
    for raw in text.splitlines():
        # Strip inline (and full-line) `#` comments; a blank remainder is skipped.
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        rule_id, sep, reason = line.partition(":")
        decisions[rule_id.strip()] = reason.strip() if sep else ""
    return decisions


def apply_decisions(findings: list[Finding], decisions: dict[str, str]) -> list[Finding]:
    """Suppress findings whose rule is in `decisions`, tagging the reason."""
    if not decisions:
        return findings
    out: list[Finding] = []
    for f in findings:
        if f.rule_id in decisions:
            reason = decisions[f.rule_id] or "no reason given"
            out.append(f.with_demote(_SUPPRESSED, f"decision: {reason}"))
        else:
            out.append(f)
    return out
