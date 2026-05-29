"""Project-scale profile inference and severity adjustment.

Some catalog rules (alembic, pydantic-settings, csrf, secure-headers) describe
real problems for a multi-tenant web service but defensible trade-offs for a
single-user local app. We infer the project's shape and down-weight those
infra rules one tier for single-user-local projects — transparently, via the
same `demoted_by` marker the justification pass uses.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from flunk.findings import Finding
from flunk.profile import Profile, apply_profile, infer_profile, resolve_profile


def _mk(rule_id: str, sev: str) -> Finding:
    return Finding(
        rule_id=rule_id, category="oss-catalog", severity=sev,
        file=Path("x.py"), line=1, message="m", replacement="r",
    )


def test_infer_single_user_local_from_sqlite(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        "[project]\ndependencies = [\"aiosqlite\", \"uvicorn\", \"fastapi\"]\n"
    )
    assert infer_profile(tmp_path) is Profile.SINGLE_USER_LOCAL


def test_infer_single_user_local_from_sqlalchemy_url(tmp_path: Path) -> None:
    # SQLAlchemy projects declare `sqlalchemy`, not `sqlite`, and reference the
    # backend only via a `sqlite:///...` URL in source.
    (tmp_path / "pyproject.toml").write_text(
        "[project]\ndependencies = [\"sqlalchemy\", \"fastapi\", \"uvicorn\"]\n"
    )
    pkg = tmp_path / "app"
    pkg.mkdir()
    (pkg / "config.py").write_text('DB_URL = "sqlite:///data/app.sqlite"\n')
    assert infer_profile(tmp_path) is Profile.SINGLE_USER_LOCAL


def test_infer_web_service_from_postgres(tmp_path: Path) -> None:
    (tmp_path / "requirements.txt").write_text("psycopg2-binary==2.9\nfastapi\n")
    assert infer_profile(tmp_path) is Profile.WEB_SERVICE


def test_infer_web_service_from_gunicorn(tmp_path: Path) -> None:
    (tmp_path / "requirements.txt").write_text("gunicorn\nflask\naiosqlite\n")
    assert infer_profile(tmp_path) is Profile.WEB_SERVICE


def test_bare_word_sqlite_in_comment_does_not_imply_sqlite(tmp_path: Path) -> None:
    # The word "sqlite" in prose (e.g. "we migrated off sqlite") must not
    # classify a project as single-user-local — only a real import / URL does.
    (tmp_path / "pyproject.toml").write_text("[project]\ndependencies = [\"rich\"]\n")
    pkg = tmp_path / "app"
    pkg.mkdir()
    (pkg / "notes.py").write_text("# we deliberately migrated off sqlite years ago\n")
    assert infer_profile(tmp_path) is Profile.UNKNOWN


def test_web_service_with_sqlite_word_stays_web_service(tmp_path: Path) -> None:
    (tmp_path / "requirements.txt").write_text("psycopg2-binary\n")
    pkg = tmp_path / "app"
    pkg.mkdir()
    (pkg / "x.py").write_text("# legacy sqlite notes\n")
    assert infer_profile(tmp_path) is Profile.WEB_SERVICE


def test_infer_unknown_without_signals(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text("[project]\ndependencies = [\"rich\"]\n")
    assert infer_profile(tmp_path) is Profile.UNKNOWN


def test_apply_profile_downweights_infra_for_single_user_local() -> None:
    findings = [_mk("flunk.alembic", "medium"), _mk("flunk.pydantic-settings", "high")]
    out = apply_profile(findings, Profile.SINGLE_USER_LOCAL)
    by_rule = {f.rule_id: f for f in out}
    assert by_rule["flunk.alembic"].severity == "nitpick"
    assert by_rule["flunk.alembic"].demoted_by is not None
    assert by_rule["flunk.pydantic-settings"].severity == "medium"


def test_apply_profile_leaves_noninfra_untouched() -> None:
    findings = [_mk("flunk.async-client-in-fn", "high")]
    out = apply_profile(findings, Profile.SINGLE_USER_LOCAL)
    assert out[0].severity == "high"
    assert out[0].demoted_by is None


def test_apply_profile_noop_for_web_service_and_unknown() -> None:
    findings = [_mk("flunk.alembic", "medium")]
    assert apply_profile(findings, Profile.WEB_SERVICE)[0].severity == "medium"
    assert apply_profile(findings, Profile.UNKNOWN)[0].severity == "medium"


def test_resolve_profile_auto_infers(tmp_path: Path) -> None:
    (tmp_path / "requirements.txt").write_text("aiosqlite\n")
    assert resolve_profile(tmp_path, "auto") is Profile.SINGLE_USER_LOCAL


def test_resolve_profile_explicit_value(tmp_path: Path) -> None:
    assert resolve_profile(tmp_path, "web-service") is Profile.WEB_SERVICE


def test_resolve_profile_rejects_unknown_choice(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        resolve_profile(tmp_path, "bogus")
