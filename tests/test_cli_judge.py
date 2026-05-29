"""--judge runs the judge pass; missing SDK gives a clean error."""

from __future__ import annotations

from typer.testing import CliRunner

from flunk.cli import app

runner = CliRunner()


def test_judge_flag_invokes_pass(tmp_path, monkeypatch):
    from flunk import cli as cli_mod
    from flunk.findings import Finding

    monkeypatch.setattr(cli_mod.semgrep_runner, "run", lambda p, **k: [
        Finding("flunk.humanize", "oss-catalog", "nitpick", tmp_path / "a.py", 1, "m")
    ])
    monkeypatch.setattr(cli_mod.detectors_mod, "run_all", lambda p: [])
    monkeypatch.setattr(cli_mod.jscpd_runner, "run", lambda p, **k: [])
    (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")

    captured = {}

    def fake_judge(findings, *, client, project_root=None):
        captured["called"] = True
        return findings

    monkeypatch.setattr(cli_mod.judge_mod, "judge_findings", fake_judge)
    monkeypatch.setattr(cli_mod, "_build_judge_client", lambda model: object())

    result = runner.invoke(app, [str(tmp_path), "--judge", "--json"])
    assert result.exit_code == 0
    assert captured.get("called") is True


def test_judge_missing_sdk_errors_cleanly(tmp_path, monkeypatch):
    from flunk import cli as cli_mod
    from flunk.findings import Finding

    monkeypatch.setattr(cli_mod.semgrep_runner, "run", lambda p, **k: [
        Finding("flunk.humanize", "oss-catalog", "nitpick", tmp_path / "a.py", 1, "m")
    ])
    monkeypatch.setattr(cli_mod.detectors_mod, "run_all", lambda p: [])
    monkeypatch.setattr(cli_mod.jscpd_runner, "run", lambda p, **k: [])
    (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")

    def boom(model):
        raise RuntimeError("--judge needs the anthropic SDK. Install it with: pip install 'flunk[judge]'")

    monkeypatch.setattr(cli_mod, "_build_judge_client", boom)
    result = runner.invoke(app, [str(tmp_path), "--judge"])
    assert result.exit_code == 2
    assert "flunk[judge]" in result.output
