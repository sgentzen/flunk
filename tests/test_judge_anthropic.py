"""AnthropicJudgeClient: prompt assembly + tool-input parsing, no network."""

from __future__ import annotations

from flunk.judge import JudgeItem
from flunk.judge_anthropic import AnthropicJudgeClient, _parse_tool_input


def _item(line: int) -> JudgeItem:
    return JudgeItem(
        rule_id="flunk.async-client-in-fn", line=line, catalog_severity="high",
        catalog_rationale="generic", excerpt=">> 3  httpx.AsyncClient()", is_security=False,
    )


def test_parse_tool_input_maps_by_index() -> None:
    items = [_item(3), _item(9)]
    tool_input = {"verdicts": [
        {"index": 0, "severity": "medium", "rationale": "one-shot", "worth_doing": True},
        {"index": 1, "severity": "skip", "rationale": "n/a", "worth_doing": False},
    ]}
    verdicts = _parse_tool_input(tool_input, items)
    assert verdicts[0].severity == "medium"
    assert verdicts[1].severity == "skip"


def test_parse_tool_input_fills_missing_with_catalog_severity() -> None:
    items = [_item(3), _item(9)]
    tool_input = {"verdicts": [
        {"index": 0, "severity": "medium", "rationale": "one-shot", "worth_doing": True},
    ]}
    verdicts = _parse_tool_input(tool_input, items)
    assert len(verdicts) == 2
    assert verdicts[1].severity == "high"
    assert verdicts[1].rationale == "generic"


class _FakeMessages:
    def __init__(self, payload): self._payload = payload
    def create(self, **kwargs):
        self.kwargs = kwargs
        class _Block:
            type = "tool_use"
            input = self._payload
        class _Resp:
            content = [_Block()]
        return _Resp()


class _FakeAnthropic:
    def __init__(self, payload): self.messages = _FakeMessages(payload)


def test_judge_file_calls_model_and_parses() -> None:
    payload = {"verdicts": [
        {"index": 0, "severity": "medium", "rationale": "one-shot", "worth_doing": True},
    ]}
    sdk = _FakeAnthropic(payload)
    client = AnthropicJudgeClient(model="claude-sonnet-4-6", sdk=sdk)
    verdicts = client.judge_file("a.py", [_item(3)])
    assert verdicts[0].rationale == "one-shot"
    assert sdk.messages.kwargs["model"] == "claude-sonnet-4-6"
    assert sdk.messages.kwargs["tool_choice"]["type"] == "tool"
