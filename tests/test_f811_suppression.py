"""f811-suppression detector: a real `# noqa: F811` directive fires; a comment
or string that merely *quotes* one (like flunk's own detector source) does not."""

from __future__ import annotations

from pathlib import Path

from flunk.detectors import f811_suppression


def _project(tmp_path: Path, name: str, body: str) -> Path:
    (tmp_path / name).write_text(body, encoding="utf-8")
    return tmp_path


def test_real_inline_noqa_fires(tmp_path: Path) -> None:
    body = (
        "def foo():\n"
        "    return 1\n"
        "\n"
        "def foo():  # noqa: F811\n"
        "    return 2\n"
    )
    hits = f811_suppression.run(_project(tmp_path, "dup.py", body))
    assert len(hits) == 1
    assert hits[0].line == 4


def test_comment_quoting_noqa_does_not_fire(tmp_path: Path) -> None:
    # Prose that describes a directive is not a suppression. This is the
    # exact false positive flunk produced on its own f811 detector source.
    body = "x = 1  # Inline `# noqa: F811` is what we look for\n"
    assert f811_suppression.run(_project(tmp_path, "doc.py", body)) == []


def test_noqa_in_string_literal_does_not_fire(tmp_path: Path) -> None:
    body = 'BANNER = "# noqa: F811"\n'
    assert f811_suppression.run(_project(tmp_path, "lit.py", body)) == []
