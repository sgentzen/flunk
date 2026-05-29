"""Drop pydantic-settings matches that are presence checks, not config reads.

`os.environ.get(...)` used directly as a boolean test (`if not os.environ.get(...)`,
`while os.environ.get(...)`, `assert os.environ.get(...)`) is a branch selector with a
working fallback — not a config value read into the program that surfaces as None deep
in a call path. Those are the false positives the rule's rationale doesn't apply to, so
we exclude them before the count-threshold aggregation.

A match is a CONFIG READ (kept) when its value flows somewhere: assigned, returned,
passed as an argument, stored in a dict/attr. It is a PRESENCE CHECK (dropped) when the
call is the test expression of an `if`/`while`/`assert` (or IfExp), or the direct operand
of `not`, or a comparison against a constant inside such a test.

Scope: only the `os.environ.get(...)` / `os.getenv(...)` call forms are considered.
The subscript form `os.environ["KEY"]` (which the YAML also matches) is intentionally
NOT filtered — a bare subscript in a boolean test raises KeyError on a missing key, so
it is never written as a presence check. Erring toward keeping a finding is the safe
direction for a false-positive correction.
"""

from __future__ import annotations

import ast
from pathlib import Path

from flunk.detectors._walk import build_parent_map
from flunk.findings import Finding

RULE_ID = "flunk.pydantic-settings"


def _is_env_call(node: ast.AST) -> bool:
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    # os.getenv(...)
    if (
        isinstance(func, ast.Attribute)
        and func.attr == "getenv"
        and isinstance(func.value, ast.Name)
        and func.value.id == "os"
    ):
        return True
    # os.environ.get(...)
    return (
        isinstance(func, ast.Attribute)
        and func.attr == "get"
        and isinstance(func.value, ast.Attribute)
        and func.value.attr == "environ"
        and isinstance(func.value.value, ast.Name)
        and func.value.value.id == "os"
    )


def _presence_check_lines(tree: ast.AST) -> set[int]:
    """Lines where an env call appears only as a branch/boolean test."""
    parents = build_parent_map(tree)

    def in_test_position(call: ast.AST) -> bool:
        # Walk up through not/bool-op/compare wrappers; the env call is a
        # presence check iff the first "structural" ancestor is the test of
        # an if/while/assert (or an IfExp test).
        node: ast.AST = call
        cur = parents.get(node)
        while isinstance(cur, (ast.UnaryOp, ast.BoolOp, ast.Compare)):
            node, cur = cur, parents.get(cur)
        if isinstance(cur, (ast.If, ast.While)):
            return cur.test is node
        if isinstance(cur, ast.IfExp):
            return cur.test is node
        if isinstance(cur, ast.Assert):
            return cur.test is node
        return False

    lines: set[int] = set()
    for node in ast.walk(tree):
        if _is_env_call(node) and in_test_position(node):
            lines.add(node.lineno)
    return lines


def drop_presence_checks(findings: list[Finding]) -> list[Finding]:
    """Remove pydantic-settings findings whose match is a presence check."""
    cache: dict[Path, set[int]] = {}
    out: list[Finding] = []
    for f in findings:
        if f.rule_id != RULE_ID:
            out.append(f)
            continue
        if f.file not in cache:
            try:
                cache[f.file] = _presence_check_lines(
                    ast.parse(f.file.read_text(encoding="utf-8", errors="replace"))
                )
            except (OSError, SyntaxError):
                cache[f.file] = set()
        if f.line not in cache[f.file]:
            out.append(f)
    return out
