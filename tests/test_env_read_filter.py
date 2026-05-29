"""os.environ.get used purely as a presence check is not a config read."""

from __future__ import annotations

from pathlib import Path

from flunk.catalog.env_read_filter import drop_presence_checks
from flunk.findings import Finding


def _f(file: Path, line: int) -> Finding:
    return Finding(
        rule_id="flunk.pydantic-settings",
        category="oss-catalog",
        severity="high",
        file=file,
        line=line,
        message="hand-rolled env parsing",
    )


def test_branch_condition_dropped(tmp_path: Path) -> None:
    src = tmp_path / "__main__.py"
    src.write_text(
        "import os\n"
        "def pick():\n"
        "    if not os.environ.get('ANTHROPIC_API_KEY'):\n"
        "        return Fallback()\n",
        encoding="utf-8",
    )
    assert drop_presence_checks([_f(src, 3)]) == []


def test_config_read_kept(tmp_path: Path) -> None:
    src = tmp_path / "config.py"
    src.write_text(
        "import os\n"
        "TOKEN = os.environ.get('API_TOKEN')\n",
        encoding="utf-8",
    )
    out = drop_presence_checks([_f(src, 2)])
    assert len(out) == 1


def test_other_rules_untouched(tmp_path: Path) -> None:
    src = tmp_path / "x.py"
    src.write_text("x = 1\n", encoding="utf-8")
    other = Finding(
        rule_id="flunk.alembic", category="oss-catalog", severity="medium",
        file=src, line=1, message="m",
    )
    assert drop_presence_checks([other]) == [other]
