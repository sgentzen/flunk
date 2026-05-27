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
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if not _CSRF_RE.search(text) or not _MIDDLEWARE_RE.search(text):
            continue
        # Find first csrf-token line for actionable lineno.
        lineno = 1
        for i, line in enumerate(text.splitlines(), start=1):
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
