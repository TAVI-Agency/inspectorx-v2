"""Живые раннеры: Claude, любой OpenAI-совместимый, маршрутизатор по
провайдерам — контракт (text, usage), общий потолок вызовов, ошибки ->
AgentLLMError."""
import json
from types import SimpleNamespace

import httpx
import pytest

from importer.build.agents import load_models_config
from importer.build.llm_client import AgentLLMError, RunnerAgentLLM
from importer.build.llm_live import (
    AnthropicRunner, CallBudget, OpenAICompatibleRunner, RoutingRunner, make_live_runner,
)


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


# ── OpenAI-совместимый раннер + общий бюджет + маршрутизатор по провайдерам ──

def _openai_transport(handler_calls, *, status=200, body=None):
    def handler(request: httpx.Request) -> httpx.Response:
        handler_calls.append(request)
        payload = body if body is not None else {
            "choices": [{"message": {"role": "assistant", "content": '{"ok": true}'}}],
            "usage": {"prompt_tokens": 55, "completion_tokens": 7},
        }
        return httpx.Response(status, json=payload)
    return httpx.MockTransport(handler)


def test_openai_compat_runner_posts_chat_completions_and_returns_usage():
    calls = []
    client = httpx.Client(transport=_openai_transport(calls))
    runner = OpenAICompatibleRunner("https://zro.moonmath.ai/v1", "sk-test", client=client)
    text, usage = runner("вопрос", "glm-5.3-flash")
    assert text == '{"ok": true}'
    assert usage == {"input_tokens": 55, "output_tokens": 7}
    req = calls[0]
    assert str(req.url) == "https://zro.moonmath.ai/v1/chat/completions"
    assert req.headers["authorization"] == "Bearer sk-test"
    sent = json.loads(req.content)
    assert sent["model"] == "glm-5.3-flash"
    assert sent["messages"] == [{"role": "user", "content": "вопрос"}]


def test_openai_compat_http_error_is_agent_llm_error():
    client = httpx.Client(transport=_openai_transport([], status=429, body={"error": "rate"}))
    runner = OpenAICompatibleRunner("https://x/v1", "k", client=client, provider="openrouter")
    with pytest.raises(AgentLLMError, match="openrouter API 429"):
        runner("q", "m")


def test_openai_compat_missing_usage_is_zero_not_crash():
    body = {"choices": [{"message": {"content": "ответ"}}]}
    client = httpx.Client(transport=_openai_transport([], body=body))
    text, usage = OpenAICompatibleRunner("https://x/v1", "k", client=client)("q", "m")
    assert text == "ответ"
    assert usage == {"input_tokens": 0, "output_tokens": 0}


def test_shared_budget_counts_across_runners():
    budget = CallBudget(max_calls=2)
    client = httpx.Client(transport=_openai_transport([]))
    a = OpenAICompatibleRunner("https://a/v1", "k", client=client, budget=budget)
    b = AnthropicRunner(client=_FakeAnthropic(), budget=budget)
    a("1", "m")
    b("2", "claude-haiku-4-5")
    with pytest.raises(AgentLLMError, match="потолок"):
        a("3", "m")


def test_routing_runner_picks_provider_by_model_and_falls_back_to_default():
    seen = []
    def r_default(prompt, model): seen.append(("default", model)); return "d", {}
    def r_gemini(prompt, model): seen.append(("gemini", model)); return "g", {}
    router = RoutingRunner(
        runners={"gemini": r_gemini}, default=r_default,
        providers={"gemini-3.1-flash-lite": "gemini"},
    )
    assert router("q", "gemini-3.1-flash-lite")[0] == "g"
    assert router("q", "claude-sonnet-5")[0] == "d"
    assert seen == [("gemini", "gemini-3.1-flash-lite"), ("default", "claude-sonnet-5")]


def test_routing_runner_unknown_provider_is_clear_error():
    router = RoutingRunner(runners={}, default=lambda p, m: ("d", {}), providers={"m": "nowhere"})
    with pytest.raises(AgentLLMError, match="nowhere"):
        router("q", "m")


# ── make_live_runner: проводка models.yaml + LLM_PROVIDER_* -> раннеры ──

def _models_yaml(tmp_path, providers_block: str = ""):
    p = tmp_path / "models.yaml"
    p.write_text("tiers:\n  cheap: a\n  mid: b\n  expensive: c\n" + providers_block,
                 encoding="utf-8")
    return load_models_config(p, env={})


def test_make_live_runner_builds_provider_runner_from_env(tmp_path, monkeypatch):
    """Модель с провайдером в models.yaml + LLM_PROVIDER_<NAME>_URL/KEY в
    окружении -> вызов уходит в OpenAI-совместимый раннер этого провайдера,
    а не в Anthropic."""
    monkeypatch.setenv("LLM_PROVIDER_GEMINI_URL", "https://g/v1")
    monkeypatch.setenv("LLM_PROVIDER_GEMINI_KEY", "k-test")
    config = _models_yaml(tmp_path, "providers:\n  gemini-x: gemini\n")

    router = make_live_runner(config)

    assert isinstance(router, RoutingRunner)
    runner = router._runners["gemini"]
    assert isinstance(runner, OpenAICompatibleRunner)
    assert runner._base_url == "https://g/v1"

    calls = []
    runner._client = httpx.Client(transport=_openai_transport(calls))
    text, usage = router("вопрос", "gemini-x")
    assert text == '{"ok": true}' and usage == {"input_tokens": 55, "output_tokens": 7}
    assert str(calls[0].url) == "https://g/v1/chat/completions"
    assert calls[0].headers["authorization"] == "Bearer k-test"


def test_make_live_runner_without_providers_is_plain_anthropic(tmp_path):
    """Без секции `providers` поведение ровно как в Волне 2 — один AnthropicRunner."""
    assert isinstance(make_live_runner(_models_yaml(tmp_path)), AnthropicRunner)


def test_make_live_runner_shares_one_budget_across_providers(tmp_path, monkeypatch):
    """Потолок IMPORTER_LLM_MAX_CALLS — общий на процесс, а не на раннер."""
    monkeypatch.setenv("LLM_PROVIDER_GEMINI_URL", "https://g/v1")
    monkeypatch.setenv("LLM_PROVIDER_GEMINI_KEY", "k-test")
    monkeypatch.setenv("IMPORTER_LLM_MAX_CALLS", "1")
    router = make_live_runner(_models_yaml(tmp_path, "providers:\n  gemini-x: gemini\n"))
    runner = router._runners["gemini"]
    runner._client = httpx.Client(transport=_openai_transport([]))
    router("раз", "gemini-x")
    with pytest.raises(AgentLLMError, match="потолок"):
        router("два", "gemini-x")
