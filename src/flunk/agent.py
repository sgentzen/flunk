"""Render findings as an agent-actionable fix plan.

Unlike the rich table (human-skimmable) or `--json` (a flat list of
pointers), this emits a markdown brief grouped by rule: each rule gets one
section with the *why*, the replacement, a fix sketch, and the list of
locations with code excerpts. The intent is a document you can paste to a
coding agent and have it work top-to-bottom, one section per task.

Suppressed (justification-demoted) findings are dropped — they represent
choices the author already defended, not work to do.
"""

from __future__ import annotations

from pathlib import Path

from flunk.catalog import metadata
from flunk.findings import Finding

SEVERITY_EMOJI = {"high": "\U0001f534", "medium": "\U0001f7e1", "nitpick": "⚪"}


def _is_test_path(file: Path) -> bool:
    """True if the finding sits in test code (de-prioritized in the plan)."""
    parts = {p.lower() for p in file.parts}
    if "tests" in parts or "test" in parts:
        return True
    name = file.name
    return name.startswith("test_") or name.endswith("_test.py")


def _read_lines(file: Path) -> list[str] | None:
    try:
        text = file.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    return text.splitlines()


def _excerpt_block(file: Path, line: int, context: int = 3) -> str | None:
    """A gutter-numbered slice of `file` around `line`, hit line marked `>>`."""
    lines = _read_lines(file)
    if lines is None:
        return None
    idx = line - 1
    if idx < 0 or idx >= len(lines):
        return None
    lo = max(0, idx - context)
    hi = min(len(lines), idx + context + 1)
    width = len(str(hi))
    out = []
    for i in range(lo, hi):
        marker = ">>" if i == idx else "  "
        out.append(f"{marker} {str(i + 1).rjust(width)}  {lines[i]}")
    return "\n".join(out)


def _fence(lines: list[str]) -> str:
    """Pick a backtick fence longer than any run inside `lines`.

    CommonMark requires the fence to exceed any backtick run in the content;
    otherwise an excerpted line containing ``` would close the block early.
    """
    longest = 0
    for ln in lines:
        run = 0
        for ch in ln:
            run = run + 1 if ch == "`" else 0
            longest = max(longest, run)
    return "`" * max(3, longest + 1)


def _rel(file: Path, root: Path | None) -> str:
    if root is not None:
        try:
            return str(file.relative_to(root)).replace("\\", "/")
        except ValueError:
            pass
    return str(file)


def _group_by_rule(findings: list[Finding]) -> dict[str, list[Finding]]:
    """Group actionable findings by rule_id, preserving rank order.

    Findings arrive ranked (severity desc, then category, then path), so
    first-seen iteration yields rule groups in that same priority order.
    Suppressed findings are excluded.
    """
    groups: dict[str, list[Finding]] = {}
    for f in findings:
        if f.severity == "suppressed":
            continue
        groups.setdefault(f.rule_id, []).append(f)
    return groups


def build_plan(
    findings: list[Finding],
    *,
    project_root: Path | None = None,
    context: int = 3,
) -> str:
    """Return a grouped-by-rule markdown fix plan for `findings`."""
    groups = _group_by_rule(findings)
    actionable = sum(len(v) for v in groups.values())
    title = project_root.name if project_root is not None else "project"

    out: list[str] = [f"# flunk fix plan — {title}"]
    if not groups:
        out.append("")
        out.append("_No actionable findings._")
        return "\n".join(out) + "\n"

    rule_word = "rule" if len(groups) == 1 else "rules"
    finding_word = "finding" if actionable == 1 else "findings"
    out.append(
        f"{actionable} actionable {finding_word} across {len(groups)} {rule_word}. "
        "Work top-to-bottom; each section is one task."
    )
    out.append("")

    for rule_id, fs in groups.items():
        meta = metadata.lookup(rule_id)
        sev = fs[0].severity
        emoji = SEVERITY_EMOJI.get(sev, "")
        n = len(fs)
        occ = "occurrence" if n == 1 else "occurrences"

        out.append("---")
        prefix = f"{emoji} " if emoji else ""
        out.append(f"## {prefix}{sev.upper()} · {rule_id} · {n} {occ}")
        out.append("")
        if meta.rationale:
            out.append(f"**Why it's worse:** {meta.rationale}")
            out.append("")
        fix_line = f"**Fix:** {meta.replacement}"
        if meta.replacement_url:
            fix_line += f"  → {meta.replacement_url}"
        out.append(fix_line)
        out.append("")
        if meta.fix_hint:
            hint_lines = meta.fix_hint.splitlines()
            fence = _fence(hint_lines)
            out.append(fence)
            out.extend(hint_lines)
            out.append(fence)
            out.append("")

        out.append("Locations:")
        for f in fs:
            note = "  ← test code; likely lower priority" if _is_test_path(f.file) else ""
            out.append(f"- [ ] {_rel(f.file, project_root)}:{f.line}{note}")
            block = _excerpt_block(f.file, f.line, context)
            if block:
                block_lines = block.splitlines()
                fence = _fence(block_lines)
                out.append(f"  {fence}python")
                out.extend(f"  {bl}" for bl in block_lines)
                out.append(f"  {fence}")
        out.append("")

    return "\n".join(out).rstrip() + "\n"
