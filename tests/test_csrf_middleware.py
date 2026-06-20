"""csrf-middleware detector: real custom CSRF middleware fires; a file that only
*mentions* csrf/middleware in comments and string literals (like flunk's own
detector source) does not."""

from __future__ import annotations

from pathlib import Path

from flunk.detectors import csrf_middleware


def _project(tmp_path: Path, name: str, body: str) -> Path:
    (tmp_path / name).write_text(body, encoding="utf-8")
    return tmp_path


def test_real_csrf_middleware_fires(tmp_path: Path) -> None:
    body = (
        "from starlette.middleware.base import BaseHTTPMiddleware\n"
        "\n"
        "class CSRFMiddleware(BaseHTTPMiddleware):\n"
        "    async def dispatch(self, request, call_next):\n"
        "        csrf_token = request.headers.get('X-CSRF-Token')\n"
        "        return await call_next(request)\n"
    )
    hits = csrf_middleware.run(_project(tmp_path, "mw.py", body))
    assert len(hits) == 1
    # Reported line is real code, not a comment.
    assert hits[0].line == 5


def test_meta_text_only_does_not_fire(tmp_path: Path) -> None:
    # Mirrors flunk's own csrf detector: csrf appears only in a comment, and
    # the middleware tokens only inside a regex-pattern string literal.
    body = (
        "import re\n"
        "_MW = re.compile(r'BaseHTTPMiddleware|def dispatch')\n"
        "# find first csrf-token line for actionable lineno\n"
        "x = 1\n"
    )
    assert csrf_middleware.run(_project(tmp_path, "meta.py", body)) == []
