"""flunk should pass its own exam.

flunk's detector source necessarily describes the patterns it hunts for — a
`# noqa: F811` in a docstring, the strings "csrf-token" and "BaseHTTPMiddleware"
in a regex. A detector that greps raw text flags its own source. These tests
lock in that it doesn't (the "physician, heal thyself" regression guard)."""

from __future__ import annotations

from pathlib import Path

from flunk.detectors import csrf_middleware, f811_suppression

_OWN_SRC = Path(__file__).resolve().parents[1] / "src" / "flunk"


def test_f811_does_not_flag_own_source() -> None:
    hits = f811_suppression.run(_OWN_SRC)
    assert hits == [], [f"{h.file}:{h.line}" for h in hits]


def test_csrf_does_not_flag_own_source() -> None:
    hits = csrf_middleware.run(_OWN_SRC)
    assert hits == [], [f"{h.file}:{h.line}" for h in hits]
