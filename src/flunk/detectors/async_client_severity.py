"""Refine flunk.async-client-in-fn severity by call-site context.

The catalog rates this rule HIGH, assuming a hot path that rebuilds the
connection pool every call. That only bites when the same construction runs
repeatedly — i.e. inside a loop. A one-shot construction (a single request to
one host) pays one TLS handshake it would pay anyway, so HIGH overstates it.

We downgrade HIGH -> MEDIUM unless the httpx.AsyncClient(...) / httpx.Client(...)
construction is lexically inside a loop in its enclosing function. Lexical only:
cross-function "called in a loop" analysis is out of scope.
"""

from __future__ import annotations

import ast
from pathlib import Path

from flunk.detectors._walk import ancestors, build_parent_map
from flunk.findings import Finding

RULE_ID = "flunk.async-client-in-fn"
_LOOP_NODES = (
    ast.For, ast.AsyncFor, ast.While,
    ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp,
)
_CLIENT_ATTRS = frozenset({"AsyncClient", "Client"})

_ONESHOT_MSG = (
    "httpx client built inside a function body, but this is a one-shot "
    "construction (not in a loop) — connection pooling only helps when the "
    "same client is reused across repeated calls. Reuse a module-level / "
    "lifespan-managed client if these calls ever go on a hot path."
)


def _is_httpx_client_call(node: ast.AST) -> bool:
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr in _CLIENT_ATTRS
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "httpx"
    )


def _construction_in_loop(tree: ast.AST, line: int) -> bool:
    """True if an httpx client call on `line` has a loop among its ancestors."""
    parents = build_parent_map(tree)

    for node in ast.walk(tree):
        if getattr(node, "lineno", None) != line or not _is_httpx_client_call(node):
            continue
        for cur in ancestors(node, parents):
            if isinstance(cur, _LOOP_NODES):
                return True
            if isinstance(cur, (ast.FunctionDef, ast.AsyncFunctionDef)):
                # Stop at the enclosing function boundary: a loop further out
                # (e.g. wrapping the call site) is the cross-function case we
                # deliberately don't model.
                return False
    return False


def refine(findings: list[Finding]) -> list[Finding]:
    """Downgrade one-shot async-client findings HIGH -> MEDIUM."""
    out: list[Finding] = []
    for f in findings:
        if f.rule_id != RULE_ID or f.severity != "high":
            out.append(f)
            continue
        try:
            tree = ast.parse(
                f.file.read_text(encoding="utf-8", errors="replace")
            )
        except (OSError, SyntaxError):
            out.append(f)
            continue
        if _construction_in_loop(tree, f.line):
            out.append(f)
        else:
            demoted = f.with_demote("medium", "context: one-shot construction")
            out.append(demoted.with_message(_ONESHOT_MSG))
    return out
