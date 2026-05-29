"""async-client severity is HIGH only when the client is built inside a loop."""

from __future__ import annotations

from pathlib import Path

from flunk.detectors.async_client_severity import refine
from flunk.findings import Finding


def _finding(file: Path, line: int) -> Finding:
    return Finding(
        rule_id="flunk.async-client-in-fn",
        category="anti-pattern",
        severity="high",
        file=file,
        line=line,
        message="httpx client instantiated inside a function body.",
    )


def test_oneshot_call_downgraded_to_medium(tmp_path: Path) -> None:
    src = tmp_path / "adapter.py"
    src.write_text(
        "import httpx\n"
        "async def fetch(url):\n"
        "    async with httpx.AsyncClient() as c:\n"
        "        return await c.get(url)\n",
        encoding="utf-8",
    )
    out = refine([_finding(src, 3)])
    assert out[0].severity == "medium"
    assert out[0].raw_severity == "high"
    assert "one-shot" in out[0].message.lower()


def test_client_inside_loop_stays_high(tmp_path: Path) -> None:
    src = tmp_path / "poller.py"
    src.write_text(
        "import httpx\n"
        "async def poll(urls):\n"
        "    for url in urls:\n"
        "        async with httpx.AsyncClient() as c:\n"
        "            await c.get(url)\n",
        encoding="utf-8",
    )
    out = refine([_finding(src, 4)])
    assert out[0].severity == "high"
    assert out[0].raw_severity is None


def test_client_inside_comprehension_stays_high(tmp_path: Path) -> None:
    src = tmp_path / "comp.py"
    src.write_text(
        "import httpx\n"
        "def make(urls):\n"
        "    return [httpx.Client() for u in urls]\n",
        encoding="utf-8",
    )
    out = refine([_finding(src, 3)])
    assert out[0].severity == "high"
    assert out[0].raw_severity is None


def test_non_async_client_findings_untouched(tmp_path: Path) -> None:
    src = tmp_path / "x.py"
    src.write_text("x = 1\n", encoding="utf-8")
    other = Finding(
        rule_id="flunk.alembic", category="oss-catalog", severity="medium",
        file=src, line=1, message="m",
    )
    assert refine([other]) == [other]


def test_unparseable_file_left_untouched(tmp_path: Path) -> None:
    src = tmp_path / "broken.py"
    src.write_text("def (:\n", encoding="utf-8")
    f = _finding(src, 1)
    assert refine([f]) == [f]
