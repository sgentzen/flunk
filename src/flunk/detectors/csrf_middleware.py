"""Rule #12: Custom CSRF token validate/issue middleware.

Heuristic: a single Python file mentions BOTH "csrf" (in some token-y
context) and looks like middleware (defines a class with `dispatch`
or a function decorated with `@app.middleware`).

Expected fires: erate-filing-assistant
"""

from __future__ import annotations

import re
from pathlib import Path

from flunk.catalog.metadata import lookup
from flunk.detectors._source import code_lines
from flunk.detectors._walk import walk_py
from flunk.findings import Finding

RULE_ID = "flunk.csrf-middleware"
_CSRF_RE = re.compile(r"csrf[_-]?token", re.IGNORECASE)
_MIDDLEWARE_RE = re.compile(
    r"(\bdef\s+dispatch\b|@\w+\.middleware|BaseHTTPMiddleware)",
    re.IGNORECASE,
)


def run(project: Path) -> list[Finding]:
    meta = lookup(RULE_ID)
    out: list[Finding] = []
    for path in walk_py(project):
        try:
            source = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        # Match the code layer only: a comment mentioning csrf, or a regex
        # pattern string that contains "BaseHTTPMiddleware", is meta-text, not
        # a custom CSRF middleware. String literals are kept — a header/cookie
        # name like "X-CSRF-Token" is a real signal.
        code = code_lines(source)
        code_text = "\n".join(code)
        if not _CSRF_RE.search(code_text) or not _MIDDLEWARE_RE.search(code_text):
            continue
        # Find first csrf-token line (in code) for actionable lineno.
        lineno = 1
        for i, line in enumerate(code, start=1):
            if _CSRF_RE.search(line):
                lineno = i
                break
        out.append(
            Finding(
                rule_id=RULE_ID,
                category=meta.category,
                severity=meta.severity,
                file=path,
                line=lineno,
                message=(
                    "Custom CSRF middleware. Use `starlette-csrf` or "
                    "`fastapi-csrf-protect` — audited, double-submit / "
                    "synchronizer-token patterns done correctly."
                ),
                replacement=meta.replacement,
                replacement_url=meta.replacement_url,
            )
        )
    return out
