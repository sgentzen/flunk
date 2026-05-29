"""Anthropic-backed JudgeClient. Requires the `judge` optional extra.

One forced-tool-use call per file: the model receives every finding in that
file (rule, catalog severity/rationale as a prior, code excerpt) and returns a
verdict per finding via a structured tool input. Parsing is index-keyed and
tolerant: a missing/garbled verdict falls back to the catalog severity/rationale
so a flaky response degrades to "no change", never to a dropped finding.
"""

from __future__ import annotations

from typing import Any

from flunk.judge import JudgeItem, Verdict

_TOOL = {
    "name": "report_verdicts",
    "description": "Report a judgment verdict for each located finding.",
    "input_schema": {
        "type": "object",
        "properties": {
            "verdicts": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "index": {"type": "integer", "description": "0-based finding index"},
                        "severity": {"type": "string", "enum": ["high", "medium", "nitpick", "skip"]},
                        "rationale": {"type": "string", "description": "1-2 sentences, specific to THIS code"},
                        "worth_doing": {"type": "boolean"},
                    },
                    "required": ["index", "severity", "rationale", "worth_doing"],
                },
            }
        },
        "required": ["verdicts"],
    },
}

_SYSTEM = (
    "You are a senior engineer triaging static-analysis findings on AI-built "
    "Python. For each finding you see the rule, a GENERIC catalog rationale "
    "(a prior, not gospel), and the surrounding code. Judge whether it actually "
    "matters HERE. Re-rate severity for this call site, and rewrite the rationale "
    "to reason about THIS code (not the template). Use 'skip' when the pattern is "
    "present but not worth fixing in context (e.g. a one-shot call, a deliberate "
    "local trade-off, a false-positive duplication of unrelated code). Be concrete."
)


def _build_user_text(rel_path: str, items: list[JudgeItem]) -> str:
    chunks = [f"File: {rel_path}\n"]
    for i, it in enumerate(items):
        sec = " [SECURITY: severity may be raised but NOT lowered or skipped]" if it.is_security else ""
        chunks.append(
            f"--- finding index {i} ---\n"
            f"rule: {it.rule_id} (catalog severity: {it.catalog_severity}){sec}\n"
            f"catalog rationale (generic prior): {it.catalog_rationale}\n"
            f"code:\n{it.excerpt}\n"
        )
    return "\n".join(chunks)


def _parse_tool_input(tool_input: dict[str, Any], items: list[JudgeItem]) -> list[Verdict]:
    """Map the model's verdicts back onto items by index; fill gaps from catalog."""
    by_index: dict[int, dict] = {}
    for v in tool_input.get("verdicts", []):
        if isinstance(v, dict) and isinstance(v.get("index"), int):
            by_index[v["index"]] = v
    out: list[Verdict] = []
    for i, it in enumerate(items):
        v = by_index.get(i)
        if v is None:
            out.append(Verdict(it.catalog_severity, it.catalog_rationale or "", True))
            continue
        out.append(Verdict(
            severity=str(v.get("severity") or it.catalog_severity),
            rationale=str(v.get("rationale") or it.catalog_rationale or ""),
            worth_doing=bool(v.get("worth_doing", True)),
        ))
    return out


class AnthropicJudgeClient:
    def __init__(self, *, model: str, sdk: Any | None = None) -> None:
        self.model = model
        # Injected sdk (tests) is used as-is. Otherwise resolve the real SDK now,
        # so a missing `flunk[judge]` extra (or an un-initializable client, e.g. no
        # ANTHROPIC_API_KEY) fails fast HERE — where the CLI reports it cleanly —
        # rather than later inside judge_findings' per-file error handling, which
        # would silently swallow it and leave everything unjudged.
        self._sdk = sdk if sdk is not None else self._new_sdk()

    @staticmethod
    def _new_sdk() -> Any:
        try:
            import anthropic
        except ImportError as e:
            raise RuntimeError(
                "--judge needs the anthropic SDK. Install it with: "
                "pip install 'flunk[judge]'"
            ) from e
        try:
            return anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from env
        except Exception as e:
            raise RuntimeError(f"could not initialize the Anthropic client: {e}") from e

    def judge_file(self, rel_path: str, items: list[JudgeItem]) -> list[Verdict]:
        resp = self._sdk.messages.create(
            model=self.model,
            max_tokens=1024,
            system=_SYSTEM,
            tools=[_TOOL],
            tool_choice={"type": "tool", "name": "report_verdicts"},
            messages=[{"role": "user", "content": _build_user_text(rel_path, items)}],
        )
        for block in resp.content:
            if getattr(block, "type", None) == "tool_use":
                return _parse_tool_input(block.input, items)
        return [Verdict(it.catalog_severity, it.catalog_rationale or "", True) for it in items]
