"""Infer a project's deployment shape and down-weight rules that don't fit it.

flunk's wrapped tools can't tell a multi-tenant web service from a single-user
local app, so they flag the same heavyweight-production answer everywhere. For
a single-user local SQLite tool, rules like alembic / pydantic-settings / csrf
/ secure-headers describe defensible trade-offs, not cut corners. We infer the
shape conservatively and only down-weight on a confident `single-user-local`
signal — `unknown` changes nothing, so uncertainty never silently suppresses.
"""

from __future__ import annotations

from enum import Enum
from pathlib import Path

from flunk.demote import DEMOTE_TIER
from flunk.detectors._walk import walk_py
from flunk.findings import Finding

# Production multi-worker servers (a strong web-service signal). uvicorn is
# deliberately absent: it's the standard way to run a local single-user app too.
_WEB_SERVER_TOKENS = ("gunicorn", "uwsgi", "hypercorn", "daphne", "mod_wsgi")
# Client libraries for server-grade databases.
_HEAVY_DB_TOKENS = (
    "psycopg", "asyncpg", "pymysql", "mysqlclient", "mysql-connector",
    "pymongo", "redis", "cassandra",
)
_SQLITE_TOKENS = ("sqlite", "aiosqlite")
# Tight signals in *source* (not bare prose): the stdlib module, the async
# driver, or a SQLAlchemy/connection URL. Avoids matching "sqlite" in a comment.
_SQLITE_SOURCE_SIGNALS = ("sqlite3", "aiosqlite", "sqlite://")
_DEP_FILES = ("pyproject.toml", "requirements.txt", "requirements.in", "setup.cfg")

# Rules whose severity assumes a production web service. One tier softer for a
# single-user local app, where they're judgment calls rather than cut corners.
INFRA_RULES: frozenset[str] = frozenset({
    "flunk.alembic",
    "flunk.pydantic-settings",
    "flunk.csrf-middleware",
    "flunk.secure-headers",
})

_PROFILE_MARKER = "profile:single-user-local"


class Profile(Enum):
    SINGLE_USER_LOCAL = "single-user-local"
    WEB_SERVICE = "web-service"
    UNKNOWN = "unknown"


def _dep_text(project: Path) -> str:
    chunks: list[str] = []
    for name in _DEP_FILES:
        p = project / name
        if p.is_file():
            try:
                chunks.append(p.read_text(encoding="utf-8", errors="replace"))
            except OSError:
                continue
    return "\n".join(chunks).lower()


def _uses_sqlite(project: Path, dep_text: str) -> bool:
    if any(tok in dep_text for tok in _SQLITE_TOKENS):
        return True
    # sqlite3 is stdlib (won't be in deps); a SQLAlchemy project references the
    # backend only via a `sqlite:///` URL. Match those specific signals rather
    # than the bare word "sqlite" so prose ("migrated off sqlite") doesn't count.
    for path in walk_py(project):
        try:
            text = path.read_text(encoding="utf-8", errors="replace").lower()
        except OSError:
            continue
        if any(sig in text for sig in _SQLITE_SOURCE_SIGNALS):
            return True
    return False


def infer_profile(project: Path) -> Profile:
    text = _dep_text(project)
    web_signal = any(t in text for t in _WEB_SERVER_TOKENS) or any(
        t in text for t in _HEAVY_DB_TOKENS
    )
    if web_signal:
        return Profile.WEB_SERVICE
    if _uses_sqlite(project, text):
        return Profile.SINGLE_USER_LOCAL
    return Profile.UNKNOWN


def resolve_profile(project: Path, choice: str) -> Profile:
    """Map a CLI --profile choice to a Profile (``auto`` infers from the project)."""
    if choice == "auto":
        return infer_profile(project)
    try:
        return Profile(choice)
    except ValueError:
        valid = "auto, " + ", ".join(p.value for p in Profile)
        raise ValueError(f"unknown profile {choice!r}; choose one of: {valid}") from None


def apply_profile(findings: list[Finding], profile: Profile) -> list[Finding]:
    """Down-weight infra rules one tier for a single-user-local project."""
    if profile is not Profile.SINGLE_USER_LOCAL:
        return findings
    out: list[Finding] = []
    for f in findings:
        if f.rule_id in INFRA_RULES and f.severity in DEMOTE_TIER:
            out.append(f.with_demote(DEMOTE_TIER[f.severity], _PROFILE_MARKER))
        else:
            out.append(f)
    return out
