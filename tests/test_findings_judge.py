"""Finding carries judge enrichment fields and a skip severity sorts last."""

from __future__ import annotations

from pathlib import Path

from flunk.findings import SEVERITY_ORDER, Finding


def test_skip_sorts_after_nitpick() -> None:
    assert SEVERITY_ORDER["skip"] > SEVERITY_ORDER["nitpick"]


def test_with_judgment_sets_fields() -> None:
    f = Finding(
        rule_id="flunk.async-client-in-fn", category="anti-pattern",
        severity="high", file=Path("a.py"), line=1, message="m",
    )
    j = f.with_judgment(severity="medium", rationale="one-shot here", worth_doing=True)
    assert j.severity == "medium"
    assert j.rationale == "one-shot here"
    assert j.judged is True
    assert j.raw_severity == "high"
    assert f.judged is False  # original untouched (frozen)
