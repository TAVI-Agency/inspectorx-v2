"""Живые LLM-раннеры Build-конвейера и мониторинга (Волна 2 + Задача «ночь
11.09.2026»): Claude API, любой OpenAI-совместимый бэкенд и маршрутизатор
между ними по имени модели.

Контракт — `Callable[[prompt, model], tuple[str, dict]]` для `RunnerAgentLLM`
(`llm_client.py`): tuple-форма несёт РЕАЛЬНЫЕ токены бэкенда, и `Tracer`
пишет в `pipeline.llm_calls` фактический расход, а не оценку len//4.

Модель приходит параметром из `models.yaml: tiers` — раннер моделей не выбирает.
Какой бэкенд обслуживает конкретную модель, решает `models.yaml: providers`
(модель -> имя провайдера) — см. `RoutingRunner`/`make_live_runner` ниже.
Без секции `providers` и без `LLM_PROVIDER_*` в окружении поведение не
меняется: всё идёт в Anthropic SDK, как в Волне 2.

Потолок вызовов на процесс: IMPORTER_LLM_MAX_CALLS (страховка от разгона цикла;
денежный контроль — `python -m importer build cost --run <id>` по трейсингу).
Потолок общий на процесс, а не на раннер — `CallBudget` делится между всеми
раннерами `RoutingRunner`, иначе суммарный расход мог бы превысить потолок
кратно числу подключённых провайдеров.

Ключ Anthropic: стандартный ANTHROPIC_API_KEY (SDK читает окружение сам).
Ключи прочих провайдеров — `LLM_PROVIDER_<NAME>_URL`/`LLM_PROVIDER_<NAME>_KEY`
(NAME — имя провайдера из `models.yaml: providers`, верхним регистром,
дефисы -> подчёркивания). `.env.importer` подхватывается тем же load_dotenv,
что и importer/db.py.
"""
from __future__ import annotations

import os
from typing import Callable

import httpx
from dotenv import load_dotenv

from importer.build.agents import ModelsConfig, load_models_config
from importer.build.llm_client import AgentLLMError

load_dotenv(".env.importer")

DEFAULT_MAX_TOKENS = 8192
DEFAULT_MAX_CALLS = 400

# Контракт раннера для `RunnerAgentLLM` (`llm_client.py`): (prompt, model) ->
# (текст ответа, реальные токены бэкенда).
LiveRunner = Callable[[str, str], tuple[str, dict]]


class CallBudget:
    """Общий потолок вызовов на процесс (IMPORTER_LLM_MAX_CALLS) — один объект
    делится между всеми раннерами RoutingRunner, чтобы суммарный расход не
    превышал потолок ни при каком составе провайдеров."""

    def __init__(self, max_calls: int) -> None:
        self.max_calls = max_calls
        self.calls = 0

    def take(self) -> None:
        if self.calls >= self.max_calls:
            raise AgentLLMError(
                f"потолок вызовов исчерпан: {self.calls}/{self.max_calls} (IMPORTER_LLM_MAX_CALLS)")
        self.calls += 1


def _budget_from_env(max_calls: int | None) -> CallBudget:
    if max_calls is None:
        raw = os.environ.get("IMPORTER_LLM_MAX_CALLS", "")
        max_calls = int(raw) if raw.isdigit() else DEFAULT_MAX_CALLS
    return CallBudget(max_calls)


class AnthropicRunner:
    """runner(prompt, model) -> (text, usage). Ленивая инициализация клиента:
    построение реестра шагов/агентов не требует ключа — падает только
    реальный вызов модели (тот же принцип, что у прежних заглушек)."""

    def __init__(self, client=None, *, max_tokens: int = DEFAULT_MAX_TOKENS,
                 max_calls: int | None = None, budget: CallBudget | None = None) -> None:
        self._client = client
        self._max_tokens = max_tokens
        self._budget = budget or _budget_from_env(max_calls)

    @property
    def calls(self) -> int:
        return self._budget.calls

    def _ensure_client(self):
        if self._client is None:
            if not (os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")):
                raise AgentLLMError(
                    "нет ANTHROPIC_API_KEY: задать в .env.importer (см. .env.importer.example)")
            import anthropic
            self._client = anthropic.Anthropic()
        return self._client

    def __call__(self, prompt: str, model: str) -> tuple[str, dict]:
        self._budget.take()
        client = self._ensure_client()
        import anthropic
        try:
            resp = client.messages.create(
                model=model, max_tokens=self._max_tokens,
                messages=[{"role": "user", "content": prompt}])
        except anthropic.APIStatusError as exc:
            raise AgentLLMError(f"Claude API {exc.status_code}: {exc.message}") from exc
        except anthropic.APIConnectionError as exc:
            raise AgentLLMError(f"Claude API недоступен: {exc}") from exc
        if resp.stop_reason == "refusal":
            raise AgentLLMError("Claude API: refusal — классификатор отклонил запрос")
        text = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")
        return text, {"input_tokens": resp.usage.input_tokens,
                      "output_tokens": resp.usage.output_tokens}


class OpenAICompatibleRunner:
    """runner(prompt, model) -> (text, usage) через POST {base_url}/chat/completions
    (OpenAI-совместимый контракт: Zro, OpenRouter, Gemini OpenAI-endpoint,
    DeepSeek, Z.ai, Together, Fireworks…). Без SDK — только httpx, чтобы не
    тащить зависимость ради одного эндпоинта."""

    def __init__(self, base_url: str, api_key: str, *, provider: str = "openai_compat",
                 client: httpx.Client | None = None, max_tokens: int = DEFAULT_MAX_TOKENS,
                 budget: CallBudget | None = None, timeout: float = 120.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._provider = provider
        self._client = client
        self._max_tokens = max_tokens
        self._budget = budget or _budget_from_env(None)
        self._timeout = timeout

    def _ensure_client(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(timeout=self._timeout)
        return self._client

    def __call__(self, prompt: str, model: str) -> tuple[str, dict]:
        self._budget.take()
        client = self._ensure_client()
        try:
            resp = client.post(
                f"{self._base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self._api_key}"},
                json={"model": model, "max_tokens": self._max_tokens,
                      "messages": [{"role": "user", "content": prompt}]},
            )
        except httpx.HTTPError as exc:
            raise AgentLLMError(f"{self._provider} API недоступен: {exc}") from exc
        if resp.status_code >= 400:
            raise AgentLLMError(f"{self._provider} API {resp.status_code}: {resp.text[:300]}")
        data = resp.json()
        try:
            text = data["choices"][0]["message"].get("content") or ""
        except (KeyError, IndexError, TypeError) as exc:
            raise AgentLLMError(f"{self._provider} API: неожиданный ответ {data!r}") from exc
        usage = data.get("usage") or {}
        return text, {"input_tokens": int(usage.get("prompt_tokens", 0) or 0),
                      "output_tokens": int(usage.get("completion_tokens", 0) or 0)}


class RoutingRunner:
    """Маршрутизирует вызов по имени модели: `providers` (models.yaml) говорит,
    у какого провайдера живёт модель; неизвестная модель идёт в `default`
    (Anthropic — обратная совместимость с Волной 2)."""

    def __init__(self, runners: dict[str, LiveRunner], default: LiveRunner,
                 providers: dict[str, str]) -> None:
        self._runners = runners
        self._default = default
        self._providers = providers

    def __call__(self, prompt: str, model: str) -> tuple[str, dict]:
        name = self._providers.get(model)
        if name is None:
            return self._default(prompt, model)
        runner = self._runners.get(name)
        if runner is None:
            raise AgentLLMError(
                f"модель {model!r} привязана к провайдеру {name!r}, но у него нет "
                f"LLM_PROVIDER_{_env_name(name)}_URL/KEY в окружении (.env.importer)")
        return runner(prompt, model)


def _env_name(provider: str) -> str:
    return provider.upper().replace("-", "_")


def make_live_runner(config: ModelsConfig | None = None) -> LiveRunner:
    """Собирает маршрутизатор из models.yaml + окружения. Без секции
    `providers` и без LLM_PROVIDER_* — ровно прежний AnthropicRunner.

    Бюджет вызовов создаётся ОДИН и передаётся во все раннеры: потолок
    IMPORTER_LLM_MAX_CALLS общий на процесс, а не на провайдера."""
    config = config or load_models_config()
    budget = _budget_from_env(None)
    default = AnthropicRunner(budget=budget)
    if not config.providers:
        return default
    runners: dict[str, LiveRunner] = {}
    for name in sorted(set(config.providers.values())):
        if name == "anthropic":
            runners[name] = default
            continue
        url = os.environ.get(f"LLM_PROVIDER_{_env_name(name)}_URL")
        key = os.environ.get(f"LLM_PROVIDER_{_env_name(name)}_KEY")
        if url and key:
            runners[name] = OpenAICompatibleRunner(url, key, provider=name, budget=budget)
    return RoutingRunner(runners=runners, default=default, providers=config.providers)
