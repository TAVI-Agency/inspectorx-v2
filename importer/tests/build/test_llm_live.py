"""Живой Claude-раннер: контракт (text, usage), потолок вызовов, ошибки -> AgentLLMError."""
from types import SimpleNamespace

import pytest

from importer.build.llm_client import AgentLLMError, RunnerAgentLLM
from importer.build.llm_live import AnthropicRunner


class _FakeAnthropic:
    def __init__(self):
        self.calls = []
        self.messages = SimpleNamespace(create=self._create)

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(
            content=[SimpleNamespace(type="text", text='{"ok": true}')],
            stop_reason="end_turn",
            usage=SimpleNamespace(input_tokens=120, output_tokens=8),
        )


def test_returns_text_and_real_usage():
    fake = _FakeAnthropic()
    runner = AnthropicRunner(client=fake)
    llm = RunnerAgentLLM(runner)
    assert llm.complete("вопрос", "claude-sonnet-5") == '{"ok": true}'
    assert llm.last_usage == {"input_tokens": 120, "output_tokens": 8, "estimated": False}
    assert fake.calls[0]["model"] == "claude-sonnet-5"


def test_call_cap_raises_agent_llm_error():
    runner = AnthropicRunner(client=_FakeAnthropic(), max_calls=1)
    runner("раз", "claude-haiku-4-5")
    with pytest.raises(AgentLLMError, match="потолок"):
        runner("два", "claude-haiku-4-5")


def test_missing_key_is_clear_error(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    runner = AnthropicRunner()  # клиент ленивый — конструктор без ключа не падает
    with pytest.raises(AgentLLMError, match="ANTHROPIC_API_KEY"):
        runner("вопрос", "claude-haiku-4-5")
