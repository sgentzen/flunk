"""rule_id → metadata mapping.

Single source of truth for severity, replacement library, and doc URL.
Kept separate from the YAML so we can lookup-and-enrich raw Semgrep
output without parsing YAML metadata fields.

Severity scale: `nitpick` < `medium` < `high`.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RuleMeta:
    category: str           # "oss-catalog" | "duplication" | "anti-pattern"
    severity: str           # "high" | "medium" | "nitpick"
    replacement: str
    replacement_url: str | None = None
    rationale: str | None = None   # one sentence: why the hand-rolled version is worse
    fix_hint: str | None = None    # short migration note, may be a before/after sketch


CATALOG: dict[str, RuleMeta] = {
    # 1
    "flunk.pydantic-settings": RuleMeta(
        category="oss-catalog", severity="high",
        replacement="pydantic-settings",
        replacement_url="https://docs.pydantic.dev/latest/concepts/pydantic_settings/",
        rationale=(
            "Hand-rolled os.environ access has no validation, no type coercion, and "
            "no single source of truth — a missing or malformed var surfaces as None "
            "deep in a call path instead of failing loudly at startup."
        ),
        fix_hint=(
            "Define a BaseSettings class and read typed attributes off one instance.\n"
            "  before: token = os.environ.get(\"API_TOKEN\")\n"
            "  after:  class Settings(BaseSettings): api_token: str\n"
            "          settings = Settings()  # raises at startup if unset"
        ),
    ),
    # 2
    "flunk.tenacity": RuleMeta(
        category="oss-catalog", severity="high",
        replacement="tenacity",
        replacement_url="https://tenacity.readthedocs.io/",
        rationale=(
            "A hand-written retry loop almost always lacks exponential backoff, "
            "jitter, a cap on attempts, and per-exception filtering — so it either "
            "hammers a struggling dependency or retries errors it never should."
        ),
        fix_hint=(
            "Decorate the call instead of looping.\n"
            "  @retry(wait=wait_exponential(max=30), stop=stop_after_attempt(5),\n"
            "         retry=retry_if_exception_type(httpx.TransportError))"
        ),
    ),
    # 3
    "flunk.uv-pip-compile": RuleMeta(
        category="oss-catalog", severity="medium",
        replacement="pyproject.toml + uv pip compile",
        replacement_url="https://docs.astral.sh/uv/concepts/projects/dependencies/",
        rationale=(
            "Unpinned or manually edited requirements drift between machines and CI; "
            "there's no lockfile, so 'works on my machine' bugs are inevitable."
        ),
        fix_hint=(
            "Declare deps in pyproject.toml and generate a locked file:\n"
            "  uv pip compile pyproject.toml -o requirements.txt"
        ),
    ),
    # 4
    "flunk.alembic": RuleMeta(
        category="oss-catalog", severity="medium",
        replacement="alembic",
        replacement_url="https://alembic.sqlalchemy.org/",
        rationale=(
            "Ad-hoc schema changes (raw ALTER, create_all on boot) have no versioning, "
            "no downgrade path, and no record of what ran against which database."
        ),
        fix_hint=(
            "Adopt migrations: `alembic init`, then `alembic revision --autogenerate` "
            "per schema change and `alembic upgrade head` to apply."
        ),
    ),
    # 5
    "flunk.sql-injection": RuleMeta(
        category="anti-pattern", severity="high",
        replacement="parameterized queries",
        replacement_url=None,
        rationale=(
            "String-interpolated SQL lets any value containing quotes alter the query "
            "— a textbook injection vector that also breaks on legitimate apostrophes."
        ),
        fix_hint=(
            "Pass values as bind parameters, never via f-string/%/+.\n"
            "  before: cur.execute(f\"SELECT * FROM t WHERE id = {uid}\")\n"
            "  after:  cur.execute(\"SELECT * FROM t WHERE id = ?\", (uid,))"
        ),
    ),
    # 6
    "flunk.async-client-in-fn": RuleMeta(
        category="anti-pattern", severity="high",
        replacement="module-level / lifespan-managed httpx client",
        replacement_url="https://www.python-httpx.org/async/#opening-and-closing-clients",
        rationale=(
            "Constructing httpx.AsyncClient inside a per-request function pays full "
            "TLS-handshake + pool setup every call and discards the pool — no "
            "keep-alive, no connection reuse, measurable latency under load."
        ),
        fix_hint=(
            "Hoist the client to module scope or a lifespan-managed singleton; reuse it.\n"
            "  before: async with httpx.AsyncClient(...) as c: await c.get(url)\n"
            "  after:  _client = httpx.AsyncClient(...)  # module scope\n"
            "          await _client.get(url)"
        ),
    ),
    # 7
    "flunk.duplicate-retry": RuleMeta(
        category="duplication", severity="high",
        replacement="extract shared retry / use tenacity",
        replacement_url="https://tenacity.readthedocs.io/",
        rationale=(
            "The same retry loop is copy-pasted across modules, so a fix or tuning "
            "change to one copy silently never reaches the others — and none of them "
            "have proper backoff."
        ),
        fix_hint=(
            "Replace every copy with one tenacity-decorated helper (see flunk.tenacity), "
            "or extract a single shared decorator if you must stay dependency-free."
        ),
    ),
    # 8
    "flunk.f811-suppression": RuleMeta(
        category="anti-pattern", severity="high",
        replacement="remove the duplicate def",
        replacement_url=None,
        rationale=(
            "Silencing F811 (redefinition) hides a real bug: two defs share a name, so "
            "the first is dead code and which one wins depends on import/eval order."
        ),
        fix_hint=(
            "Delete or rename the duplicate definition and drop the noqa — don't "
            "suppress the warning."
        ),
    ),
    # 9
    "flunk.bare-except-security": RuleMeta(
        category="anti-pattern", severity="medium",
        replacement="catch the specific exception class",
        replacement_url=None,
        rationale=(
            "A bare `except:` swallows KeyboardInterrupt, SystemExit, and unrelated "
            "bugs, turning a security or logic failure into a silent no-op."
        ),
        fix_hint=(
            "Catch the narrowest exception you actually handle.\n"
            "  before: except: pass\n"
            "  after:  except (httpx.HTTPError, ValueError) as e: log.warning(e)"
        ),
    ),
    # 10
    "flunk.inline-import": RuleMeta(
        category="anti-pattern", severity="nitpick",
        replacement="restructure to remove the cycle",
        replacement_url=None,
        rationale=(
            "A function-body import is usually a band-aid over a circular dependency; "
            "it hides the cycle, adds per-call import overhead, and confuses tooling."
        ),
        fix_hint=(
            "Move the import to module top-level; if that triggers a cycle, extract the "
            "shared symbol into a third module both can import."
        ),
    ),
    # 11
    "flunk.secure-headers": RuleMeta(
        category="oss-catalog", severity="nitpick",
        replacement="secure",
        replacement_url="https://github.com/TypeError/secure",
        rationale=(
            "Hand-setting a couple of security headers tends to miss several and drift "
            "out of date with current browser guidance."
        ),
        fix_hint=(
            "Apply a maintained header set via the `secure` library middleware instead "
            "of writing headers by hand."
        ),
    ),
    # 12
    "flunk.csrf-middleware": RuleMeta(
        category="oss-catalog", severity="medium",
        replacement="starlette-csrf / fastapi-csrf-protect",
        replacement_url="https://github.com/frankie567/starlette-csrf",
        rationale=(
            "A bespoke CSRF check usually gets the token-comparison or cookie flags "
            "subtly wrong — exactly the kind of bug that's invisible until exploited."
        ),
        fix_hint=(
            "Mount a vetted CSRF middleware (starlette-csrf / fastapi-csrf-protect) "
            "rather than rolling token generation and validation yourself."
        ),
    ),
    # 13
    "flunk.humanize": RuleMeta(
        category="oss-catalog", severity="nitpick",
        replacement="humanize",
        replacement_url="https://python-humanize.readthedocs.io/",
        rationale=(
            "Hand-rolled '3 minutes ago' / '1.2 MB' formatting is a pile of edge cases "
            "(pluralization, rounding, i18n) that a maintained library already handles."
        ),
        fix_hint=(
            "Use humanize helpers.\n"
            "  before: f\"{n} item{'s' if n != 1 else ''}\"\n"
            "  after:  humanize.naturalsize(b) / humanize.naturaltime(dt)"
        ),
    ),
    # 14
    "flunk.sqlite3-thread": RuleMeta(
        category="anti-pattern", severity="medium",
        replacement="SQLAlchemy or aiosqlite",
        replacement_url="https://docs.sqlalchemy.org/",
        rationale=(
            "Sharing one sqlite3 connection across threads (check_same_thread=False) "
            "without locking corrupts state under concurrency."
        ),
        fix_hint=(
            "Use a connection-per-thread pool via SQLAlchemy, or aiosqlite for async — "
            "don't disable the same-thread guard."
        ),
    ),
    # 15
    "flunk.module-singleton": RuleMeta(
        category="anti-pattern", severity="nitpick",
        replacement="add a lock or accept the inconsistency",
        replacement_url=None,
        rationale=(
            "A lazily-initialized module global mutated from multiple threads can "
            "double-initialize or read a half-built object — a classic race."
        ),
        fix_hint=(
            "Guard initialization with a lock (or threading.local), or document that "
            "the eventual-consistency is intentional."
        ),
    ),
    # jscpd general duplication
    "flunk.duplication": RuleMeta(
        category="duplication", severity="medium",
        replacement="extract a shared helper",
        replacement_url=None,
        rationale=(
            "A block duplicated across files means every future change has to be made "
            "in N places, and they will inevitably drift apart."
        ),
        fix_hint=(
            "Extract the shared block into one function/module and call it from each "
            "former copy."
        ),
    ),
}


# Rules whose severity the LLM judge may RAISE or re-explain, but never lower
# or skip — a confident-but-wrong model must not be able to bury a real
# security/correctness defect. Everything else is judgment-prone and fully
# judge-able (including a "skip" verdict).
SECURITY_RULES: frozenset[str] = frozenset({
    "flunk.sql-injection",
    "flunk.csrf-middleware",
    "flunk.f811-suppression",
    "flunk.bare-except-security",
})


def is_security_rule(rule_id: str) -> bool:
    return rule_id in SECURITY_RULES


def lookup(rule_id: str) -> RuleMeta:
    """Return metadata for a rule_id, with a safe fallback for unknown rules."""
    if rule_id in CATALOG:
        return CATALOG[rule_id]
    return RuleMeta(
        category="anti-pattern",
        severity="medium",
        replacement="(no replacement registered)",
        rationale="(no rationale registered for this rule)",
    )
