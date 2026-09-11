# Ночная сессия 11.09.2026 — фабрика к включению + витрина/операционка

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** к утру фабрика контента подключается к любому LLM-провайдеру и любому поисковому API одними переменными окружения, Cartographer умеет реально искать и читать источники, узбекский текст в обоих скриптах сравнивается корректно, а витрина получает Sentry/аналитику и юридические страницы за флагами — всё в ветке, без прода, без денег, без решений владельца.

**Architecture:** раннер LLM становится маршрутизатором «модель → провайдер» (Anthropic SDK или любой OpenAI-совместимый HTTP-эндпоинт через `httpx`); веб-поиск получает бэкенды Serper/Tavily с allowlist доменов; новый модуль `docfetch` скачивает и кэширует документы (HTML/PDF) в `pipeline.documents`; Cartographer в режиме `--research` строит карту по реальным источникам. Фронт: `observability.ts` (Sentry + аналитика за env), страницы `/legal/offer`, `/legal/privacy`, `/contacts` с флагом публикации, черновики текстов — в `docs/legal/`.

**Tech Stack:** Python 3.13 (`importer/`, `httpx`, `beautifulsoup4`, `pypdf` — новая зависимость), pytest (`httpx.MockTransport` для сетевых тестов); React 19 + TS + Vite, vitest, `@sentry/react` — новая зависимость; Supabase-миграции (только в ветке).

## Global Constraints

- Ветка `worktree-night-factory-2026-09-11`, worktree `.claude/worktrees/night-factory-2026-09-11`. **В `main` не мержить** (мёрж = автонакат миграций на прод). Прод-БД не трогать. Деньги не тратить: ни одного живого вызова LLM/поисковых API — все сетевые тесты на `httpx.MockTransport`/фейках.
- Деструктивные действия (rm вне scratchpad, drop, force-push, отзыв токенов) — запрещены.
- Python-тесты: `/Users/abduraxmonturdiyev/inspector-x-final/.venv-importer/bin/python -m pytest importer/tests -q` из корня worktree. Базовая линия: **583 passed, 67 skipped**. Новую зависимость ставить в этот же venv (`.../.venv-importer/bin/pip install pypdf`) и дописывать в `importer/requirements.txt`.
- Фронт: `npm test` (vitest), `npm run build` (tsc + vite), `npm run lint` (oxlint) — все три зелёные перед каждым коммитом фронта.
- Язык: комментарии, докстринги, строки UI, коммиты — русский (conventional commits по-русски: `feat(importer): …`, `feat(front): …`, `docs: …`); код и имена — английский. Все строки UI — только в `src/i18n/ru.ts`.
- Обратная совместимость: без новых env-переменных поведение конвейера НЕ меняется (дефолт — Anthropic, `WEBSEARCH_BACKEND=live`, Cartographer без research).
- Никаких `TODO`/заглушек в коде; каждая задача заканчивается зелёными тестами и коммитом.
- Коммиты подписаны текущим git-пользователем (TAVI-Agency). Один коммит — одна задача (или логичный шаг задачи).

## Карта файлов

| Файл | Ответственность |
|---|---|
| `importer/build/llm_live.py` | `AnthropicRunner` (есть), `OpenAICompatibleRunner`, `CallBudget`, `RoutingRunner`, `make_live_runner()` |
| `importer/build/agents.py` | `ModelsConfig` + `providers`, env-оверрайды тиров в `load_models_config` |
| `importer/build/models.yaml` | секция `providers` (пустая по умолчанию) |
| `importer/build/websearch.py` | `SerperWebSearcher`, `TavilyWebSearcher`, `WebSearchError`, фабрика по `WEBSEARCH_BACKEND` |
| `importer/build/docfetch.py` | `FetchedDoc`, `DocCache`, `InMemoryDocCache`, `SupabaseDocCache`, `DocumentFetcher` |
| `supabase/migrations/20260911100000_pipeline_documents.sql` | таблица кэша документов |
| `importer/build/research.py` | `ResearchSource`, `ResearchToolkit` (поиск → скачивание → выдержки) |
| `importer/build/cartographer.py` | режим research (план запросов → источники в промпте → `sources` в айтемах) |
| `importer/build/question_writer.py` | `MapItem.from_payload` (терпим к лишним ключам) |
| `importer/build/uzscript.py` | транслитерация uz латиница↔кириллица, `normalize_for_match`, `detect_script` |
| `importer/build/legalx_mock.py`, `importer/build/eval_golden.py`, `importer/build/agents.py` | точки применения нормализации |
| `importer/cli.py` | `build map --research`, `build eval-golden --llm live`, `build eval-models` |
| `.env.importer.example` | новые переменные |
| `src/lib/observability.ts`, `src/main.tsx`, `.env.example` | Sentry + аналитика за env |
| `src/legal/docs.ts`, `src/pages/c/CLegalPage.tsx`, `src/pages/c/CContactsPage.tsx`, `src/App.tsx`, `src/pages/c/CLayout.tsx`, `src/pages/landing-b/LandingB.tsx`, `src/i18n/ru.ts`, `src/config.ts` | юридические страницы за флагом |
| `docs/legal/offer-draft.md`, `docs/legal/privacy-draft.md` | черновики для юриста |
| `docs/adr/0006-llm-providers.md`, `docs/superpowers/plans/2026-08-06-photocontrol-wave3-people-and-vendors.md`, `docs/LAUNCH_CHECKLIST.md`, `docs/NIGHT_REPORT_2026-09-11.md` | документы |

---

### Task 1: OpenAI-совместимый раннер и маршрутизация по провайдерам

**Files:**
- Modify: `importer/build/llm_live.py`
- Modify: `importer/build/agents.py:30-46` (`ModelsConfig`, `load_models_config`)
- Modify: `importer/build/models.yaml`
- Modify: `.env.importer.example`
- Test: `importer/tests/build/test_llm_live.py`, `importer/tests/build/test_agents.py` (только новые тесты на `load_models_config`)

**Interfaces:**
- Consumes: `RunnerAgentLLM(runner)` из `llm_client.py` — контракт `runner(prompt, model) -> tuple[str, dict]`; `AgentLLMError`.
- Produces:
  - `class CallBudget: __init__(self, max_calls: int); calls: int; take(self) -> None` (raise `AgentLLMError` при исчерпании).
  - `class OpenAICompatibleRunner: __init__(self, base_url: str, api_key: str, *, provider: str = "openai_compat", client: httpx.Client | None = None, max_tokens: int = 8192, budget: CallBudget | None = None, timeout: float = 120.0)`; `__call__(prompt, model) -> tuple[str, dict]`.
  - `class RoutingRunner: __init__(self, runners: dict[str, Callable], default: Callable, providers: dict[str, str])`; `__call__(prompt, model)`.
  - `AnthropicRunner.__init__` получает опциональный `budget: CallBudget | None` (старый `max_calls` остаётся).
  - `make_live_runner(config: ModelsConfig | None = None) -> Callable[[str, str], tuple[str, dict]]`.
  - `ModelsConfig.providers: dict[str, str]` (модель → имя провайдера; отсутствие = anthropic).
  - Env: `LLM_PROVIDER_<NAME>_URL`, `LLM_PROVIDER_<NAME>_KEY` (NAME — имя провайдера из `models.yaml`, верхним регистром, дефисы → подчёркивания); `IMPORTER_TIER_CHEAP` / `IMPORTER_TIER_MID` / `IMPORTER_TIER_EXPENSIVE` — оверрайды тиров.

- [ ] **Step 1: Тест на `CallBudget` и `OpenAICompatibleRunner` (падает)**

Добавить в `importer/tests/build/test_llm_live.py`:

```python
import json

import httpx

from importer.build.llm_live import CallBudget, OpenAICompatibleRunner, RoutingRunner


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
```

- [ ] **Step 2: Запустить — убедиться, что падает на ImportError**

Run: `/Users/abduraxmonturdiyev/inspector-x-final/.venv-importer/bin/python -m pytest importer/tests/build/test_llm_live.py -q`
Expected: FAIL — `ImportError: cannot import name 'CallBudget'`.

- [ ] **Step 3: Реализация в `llm_live.py`**

Обновить докстринг модуля (теперь «живые раннеры: Anthropic + любой OpenAI-совместимый + маршрутизатор») и добавить:

```python
import httpx


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
```

`AnthropicRunner.__init__` добавляет параметр `budget: CallBudget | None = None`: `self._budget = budget or _budget_from_env(max_calls)`; в `__call__` вместо ручного счётчика — `self._budget.take()`; свойство `calls` возвращает `self._budget.calls` (сохранить для обратной совместимости тестов).

```python
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

    def __init__(self, runners: dict[str, Callable[[str, str], tuple[str, dict]]],
                 default: Callable[[str, str], tuple[str, dict]],
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


def make_live_runner(config=None):
    """Собирает маршрутизатор из models.yaml + окружения. Без секции
    `providers` и без LLM_PROVIDER_* — ровно прежний AnthropicRunner."""
    from importer.build.agents import load_models_config
    config = config or load_models_config()
    budget = _budget_from_env(None)
    default = AnthropicRunner(budget=budget)
    runners = {}
    for name in sorted(set(config.providers.values())):
        if name == "anthropic":
            runners[name] = default
            continue
        url = os.environ.get(f"LLM_PROVIDER_{_env_name(name)}_URL")
        key = os.environ.get(f"LLM_PROVIDER_{_env_name(name)}_KEY")
        if url and key:
            runners[name] = OpenAICompatibleRunner(url, key, provider=name, budget=budget)
    if not config.providers:
        return default
    return RoutingRunner(runners=runners, default=default, providers=config.providers)
```

Импорт `Callable` — из `typing`. Ленивый импорт `load_models_config` внутри функции — чтобы не создать цикл `agents ↔ llm_live` (проверить: `agents.py` `llm_live` не импортирует; если цикла нет — можно импортировать сверху).

- [ ] **Step 4: `ModelsConfig.providers` + env-оверрайды тиров + тесты**

В `agents.py`:

```python
@dataclass(frozen=True)
class ModelsConfig:
    tiers: dict[str, str]
    pricing: dict[str, dict[str, float]]
    providers: dict[str, str] = field(default_factory=dict)


_TIER_ENV = {"cheap": "IMPORTER_TIER_CHEAP", "mid": "IMPORTER_TIER_MID",
             "expensive": "IMPORTER_TIER_EXPENSIVE"}


def load_models_config(path: Path = _MODELS_PATH, *, env: Mapping[str, str] | None = None) -> ModelsConfig:
    """`env` — оверрайды тиров (по умолчанию os.environ): IMPORTER_TIER_CHEAP=…
    подменяет модель тира на время процесса — для eval разных моделей без
    правки models.yaml. Модель-оверрайд без строки в `pricing` допустима:
    стоимость такого вызова в cost-отчёте считается по нулевому прайсу."""
    env = os.environ if env is None else env
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    tiers = dict(raw["tiers"])
    missing = [t for t in _TIERS if t not in tiers]
    if missing:
        raise ValueError(f"models.yaml: не хватает тиров {missing} (ожидались {_TIERS})")
    for tier, var in _TIER_ENV.items():
        if env.get(var):
            tiers[tier] = env[var]
    return ModelsConfig(tiers=tiers, pricing=raw.get("pricing", {}),
                        providers=dict(raw.get("providers") or {}))
```

Проверить `importer/build/trace.py: cost_report` — как он ведёт себя с моделью без прайса (KeyError?). Если падает — сделать «нулевой прайс + пометка `unpriced_models` в отчёте», с тестом в `test_trace.py`.

Тесты в `test_agents.py` (рядом с существующими тестами `load_models_config`, если есть; иначе новый блок):

```python
def test_tier_env_override(tmp_path):
    p = tmp_path / "models.yaml"
    p.write_text("tiers:\n  cheap: a\n  mid: b\n  expensive: c\n", encoding="utf-8")
    cfg = load_models_config(p, env={"IMPORTER_TIER_MID": "gemini-3.1-flash-lite"})
    assert cfg.tiers == {"cheap": "a", "mid": "gemini-3.1-flash-lite", "expensive": "c"}
    assert cfg.providers == {}


def test_providers_section_parsed(tmp_path):
    p = tmp_path / "models.yaml"
    p.write_text("tiers:\n  cheap: a\n  mid: b\n  expensive: c\nproviders:\n  a: gemini\n",
                 encoding="utf-8")
    assert load_models_config(p, env={}).providers == {"a": "gemini"}
```

`models.yaml` — добавить в конец (комментарий по-русски):

```yaml
# Провайдер модели (Задача «ночь 11.09.2026»): модель -> имя провайдера.
# Имя провайдера ищется в окружении как LLM_PROVIDER_<NAME>_URL / _KEY
# (OpenAI-совместимый /chat/completions). Модели без строки здесь идут в
# Anthropic SDK (ANTHROPIC_API_KEY, при необходимости ANTHROPIC_BASE_URL —
# так подключается и Anthropic-совместимый /v1/messages у Zro).
# Пример:
#   providers:
#     gemini-3.1-flash-lite: gemini
#     deepseek-v4.1-flash: openrouter
providers: {}
```

`.env.importer.example` — блок:

```
# Дополнительные LLM-провайдеры (OpenAI-совместимые). Имя после LLM_PROVIDER_ —
# то же, что в models.yaml: providers (верхним регистром). Примеры:
# LLM_PROVIDER_GEMINI_URL="https://generativelanguage.googleapis.com/v1beta/openai"
# LLM_PROVIDER_GEMINI_KEY="AIza..."
# LLM_PROVIDER_OPENROUTER_URL="https://openrouter.ai/api/v1"
# LLM_PROVIDER_OPENROUTER_KEY="sk-or-..."
# LLM_PROVIDER_ZRO_URL="https://zro.moonmath.ai/v1"
# LLM_PROVIDER_ZRO_KEY="..."
# Подмена модели тира на время процесса (eval разных моделей без правки yaml):
# IMPORTER_TIER_CHEAP="gemini-3.1-flash-lite"
# IMPORTER_TIER_MID="deepseek-v4.1-flash"
# IMPORTER_TIER_EXPENSIVE="claude-sonnet-5"
```

- [ ] **Step 5: Прогнать все тесты**

Run: `/Users/abduraxmonturdiyev/inspector-x-final/.venv-importer/bin/python -m pytest importer/tests -q`
Expected: все зелёные (583 старых + новые).

- [ ] **Step 6: Commit**

```bash
git add importer/build/llm_live.py importer/build/agents.py importer/build/models.yaml importer/build/trace.py .env.importer.example importer/tests/build/test_llm_live.py importer/tests/build/test_agents.py importer/tests/build/test_trace.py
git commit -m "feat(importer): OpenAI-совместимый раннер и маршрутизация моделей по провайдерам"
```

---

### Task 2: Бэкенды веб-поиска Serper и Tavily с allowlist доменов

**Files:**
- Modify: `importer/build/websearch.py`
- Modify: `.env.importer.example`
- Test: `importer/tests/build/test_websearch_backends.py` (новый)

**Interfaces:**
- Consumes: `SearchResult`, `WebSearcher` (есть).
- Produces:
  - `class WebSearchError(AgentLLMError)` — ошибка HTTP/сети поискового API (пустой результат — НЕ ошибка).
  - `class SerperWebSearcher: __init__(self, api_key: str, *, gl: str = "uz", hl: str = "ru", allowed_domains: tuple[str, ...] = (), num: int = 10, client: httpx.Client | None = None)`; `search(query) -> list[SearchResult]`.
  - `class TavilyWebSearcher: __init__(self, api_key: str, *, country: str | None = "uzbekistan", allowed_domains: tuple[str, ...] = (), max_results: int = 10, client: httpx.Client | None = None)`; `search(query)`.
  - `filter_allowed(results: list[SearchResult], allowed_domains: tuple[str, ...]) -> list[SearchResult]` — хост URL равен домену или заканчивается на `.` + домен.
  - `get_web_searcher()` понимает `WEBSEARCH_BACKEND=live|serper|tavily`, читает `SERPER_API_KEY`, `TAVILY_API_KEY`, `WEBSEARCH_ALLOWED_DOMAINS` (через запятую), `WEBSEARCH_GL`, `WEBSEARCH_HL`.

- [ ] **Step 1: Тесты (падают)**

```python
"""Бэкенды веб-поиска Serper/Tavily: тело запроса, маппинг ответа, allowlist,
ошибки HTTP -> WebSearchError, пусто = «не нашёл»."""
import json

import httpx
import pytest

from importer.build.websearch import (
    SerperWebSearcher, TavilyWebSearcher, WebSearchError, filter_allowed, get_web_searcher,
)


def _transport(calls, status=200, body=None):
    def handler(request):
        calls.append(request)
        return httpx.Response(status, json=body if body is not None else {})
    return httpx.MockTransport(handler)


def test_serper_maps_organic_and_sends_locale():
    calls = []
    body = {"organic": [
        {"title": "ПКМ-737", "link": "https://lex.uz/docs/5118476", "snippet": "маркировка"},
        {"title": "спам", "link": "https://example.com/x", "snippet": "…"},
    ]}
    s = SerperWebSearcher("key", allowed_domains=("lex.uz", "gov.uz"),
                          client=httpx.Client(transport=_transport(calls, body=body)))
    out = s.search("маркировка молока")
    assert out == [{"title": "ПКМ-737", "url": "https://lex.uz/docs/5118476", "snippet": "маркировка"}]
    req = calls[0]
    assert str(req.url) == "https://google.serper.dev/search"
    assert req.headers["x-api-key"] == "key"
    assert json.loads(req.content) == {"q": "маркировка молока", "gl": "uz", "hl": "ru", "num": 10}


def test_serper_http_error_raises():
    s = SerperWebSearcher("key", client=httpx.Client(transport=_transport([], status=403)))
    with pytest.raises(WebSearchError, match="serper.*403"):
        s.search("q")


def test_tavily_maps_results_and_include_domains():
    calls = []
    body = {"results": [{"title": "T", "url": "https://consumer.gov.uz/a", "content": "текст"}]}
    t = TavilyWebSearcher("tk", allowed_domains=("gov.uz",),
                          client=httpx.Client(transport=_transport(calls, body=body)))
    assert t.search("q") == [{"title": "T", "url": "https://consumer.gov.uz/a", "snippet": "текст"}]
    sent = json.loads(calls[0].content)
    assert sent["query"] == "q" and sent["include_domains"] == ["gov.uz"]
    assert sent["country"] == "uzbekistan"
    assert calls[0].headers["authorization"] == "Bearer tk"


def test_filter_allowed_matches_host_suffix_only():
    results = [
        {"title": "", "url": "https://lex.uz/docs/1", "snippet": ""},
        {"title": "", "url": "https://sub.lex.uz/x", "snippet": ""},
        {"title": "", "url": "https://notlex.uz/x", "snippet": ""},
    ]
    assert [r["url"] for r in filter_allowed(results, ("lex.uz",))] == [
        "https://lex.uz/docs/1", "https://sub.lex.uz/x"]
    assert filter_allowed(results, ()) == results


def test_factory_serper_requires_key(monkeypatch):
    monkeypatch.setenv("WEBSEARCH_BACKEND", "serper")
    monkeypatch.delenv("SERPER_API_KEY", raising=False)
    with pytest.raises(ValueError, match="SERPER_API_KEY"):
        get_web_searcher()


def test_factory_serper_reads_env(monkeypatch):
    monkeypatch.setenv("WEBSEARCH_BACKEND", "serper")
    monkeypatch.setenv("SERPER_API_KEY", "k")
    monkeypatch.setenv("WEBSEARCH_ALLOWED_DOMAINS", "lex.uz, gov.uz")
    monkeypatch.setenv("WEBSEARCH_HL", "uz")
    s = get_web_searcher()
    assert isinstance(s, SerperWebSearcher)
    assert s.allowed_domains == ("lex.uz", "gov.uz") and s.hl == "uz"
```

- [ ] **Step 2: Запустить — падает на ImportError**

Run: `… -m pytest importer/tests/build/test_websearch_backends.py -q` → FAIL.

- [ ] **Step 3: Реализация**

В `websearch.py` (обновить докстринг модуля: три бэкенда; `live` = Claude web_search как раньше):

```python
from urllib.parse import urlsplit

import httpx

from importer.build.llm_client import AgentLLMError


class WebSearchError(AgentLLMError):
    """HTTP/сетевая ошибка поискового API. Пустая выдача — не ошибка."""


def filter_allowed(results: list[SearchResult], allowed_domains: tuple[str, ...]) -> list[SearchResult]:
    if not allowed_domains:
        return results
    def ok(url: str) -> bool:
        host = (urlsplit(url).hostname or "").lower()
        return any(host == d or host.endswith("." + d) for d in allowed_domains)
    return [r for r in results if ok(r["url"])]


class SerperWebSearcher:
    """Google-выдача через serper.dev: gl=uz/hl=ru|uz — единственный из дешёвых
    SERP-API с узбекской локалью (ресёрч 10.09.2026)."""

    URL = "https://google.serper.dev/search"

    def __init__(self, api_key, *, gl="uz", hl="ru", allowed_domains=(), num=10, client=None):
        self._api_key = api_key
        self.gl, self.hl, self.allowed_domains, self._num = gl, hl, tuple(allowed_domains), num
        self._client = client

    def search(self, query: str) -> list[SearchResult]:
        client = self._client or httpx.Client(timeout=30.0)
        self._client = client
        try:
            resp = client.post(self.URL, headers={"X-API-KEY": self._api_key},
                               json={"q": query, "gl": self.gl, "hl": self.hl, "num": self._num})
        except httpx.HTTPError as exc:
            raise WebSearchError(f"serper недоступен: {exc}") from exc
        if resp.status_code >= 400:
            raise WebSearchError(f"serper API {resp.status_code}: {resp.text[:200]}")
        organic = resp.json().get("organic") or []
        results = [SearchResult(title=str(r.get("title", "")), url=str(r.get("link", "")),
                                snippet=str(r.get("snippet", "")))
                   for r in organic if r.get("link")]
        return filter_allowed(results, self.allowed_domains)
```

`TavilyWebSearcher` — по тому же образцу: `URL = "https://api.tavily.com/search"`, заголовок `Authorization: Bearer <key>`, тело `{"query", "search_depth": "basic", "max_results", "include_domains": list(allowed_domains) (если есть), "country": country (если задан)}`, маппинг `results[*].title/url/content→snippet`, затем `filter_allowed` (Tavily сам фильтрует, но повторный фильтр — страховка).

Фабрика:

```python
def get_web_searcher() -> WebSearcher:
    backend = os.environ.get("WEBSEARCH_BACKEND", "live")
    allowed = tuple(d.strip() for d in os.environ.get("WEBSEARCH_ALLOWED_DOMAINS", "").split(",") if d.strip())
    if backend == "live":
        return _LiveWebSearcher()
    if backend == "serper":
        key = os.environ.get("SERPER_API_KEY")
        if not key:
            raise ValueError("WEBSEARCH_BACKEND=serper требует SERPER_API_KEY в .env.importer")
        return SerperWebSearcher(key, gl=os.environ.get("WEBSEARCH_GL", "uz"),
                                 hl=os.environ.get("WEBSEARCH_HL", "ru"), allowed_domains=allowed)
    if backend == "tavily":
        key = os.environ.get("TAVILY_API_KEY")
        if not key:
            raise ValueError("WEBSEARCH_BACKEND=tavily требует TAVILY_API_KEY в .env.importer")
        return TavilyWebSearcher(key, allowed_domains=allowed)
    raise ValueError(f"Неизвестный WEBSEARCH_BACKEND={backend!r}: ожидается live | serper | tavily")
```

`.env.importer.example`:

```
# Веб-поиск (Template hunter, Cartographer --research): live = инструмент web_search Claude
# (как в Волне 2), serper = Google через serper.dev (gl=uz), tavily = Tavily.
WEBSEARCH_BACKEND="live"
# SERPER_API_KEY="..."
# TAVILY_API_KEY="tvly-..."
# Allowlist доменов через запятую (пусто = без ограничений). Рекомендуемый набор для УЗ:
# WEBSEARCH_ALLOWED_DOMAINS="lex.uz,gov.uz,customs.uz,standart.uz,eec.eaeunion.org,norma.uz"
# WEBSEARCH_GL="uz"
# WEBSEARCH_HL="ru"
```

- [ ] **Step 4: Все тесты зелёные** — `… -m pytest importer/tests -q`.

- [ ] **Step 5: Commit**

```bash
git add importer/build/websearch.py .env.importer.example importer/tests/build/test_websearch_backends.py
git commit -m "feat(importer): бэкенды веб-поиска Serper/Tavily с allowlist доменов и узбекской локалью"
```

---

### Task 3: Скачивание и кэш документов (`docfetch`)

**Files:**
- Create: `importer/build/docfetch.py`
- Create: `supabase/migrations/20260911100000_pipeline_documents.sql`
- Modify: `importer/requirements.txt` (+ `pypdf`), `supabase/config.toml` НЕ трогать (схема `pipeline` уже экспонирована)
- Test: `importer/tests/build/test_docfetch.py` (новый)

**Interfaces:**
- Produces:
  - `@dataclass(frozen=True) class FetchedDoc: url: str; final_url: str; content_type: str; sha256: str; text: str; fetched_at: datetime; from_cache: bool = False`
  - `class DocCache(Protocol): get(self, url: str) -> FetchedDoc | None; put(self, doc: FetchedDoc) -> None`
  - `class InMemoryDocCache`, `class SupabaseDocCache(client)` (таблица `pipeline.documents`).
  - `class DocFetchError(Exception)`.
  - `class DocumentFetcher: __init__(self, *, cache: DocCache | None = None, client: httpx.Client | None = None, host_delays: dict[str, float] | None = None, default_delay: float = 1.0, max_bytes: int = 5_000_000, timeout: float = 30.0, sleep: Callable[[float], None] = time.sleep, clock: Callable[[], float] = time.monotonic)`; `fetch(self, url: str) -> FetchedDoc`.
  - `extract_text_html(html: str) -> str`, `extract_text_pdf(data: bytes) -> str`.
  - Дефолт `host_delays = {"lex.uz": 20.0}` (robots lex.uz: `Crawl-delay: 20`).

- [ ] **Step 1: Установить `pypdf` в venv и дописать в requirements**

```bash
/Users/abduraxmonturdiyev/inspector-x-final/.venv-importer/bin/pip install pypdf
/Users/abduraxmonturdiyev/inspector-x-final/.venv-importer/bin/pip freeze | grep -i "^pypdf=="  # версию — в importer/requirements.txt по алфавиту
```

- [ ] **Step 2: Тесты (падают)**

```python
"""docfetch: HTML/PDF -> текст, sha256, кэш (память/Supabase), вежливость по хостам, ошибки."""
import io
from datetime import datetime, timezone

import httpx
import pytest
from pypdf import PdfWriter

from importer.build.docfetch import (
    DocFetchError, DocumentFetcher, FetchedDoc, InMemoryDocCache, SupabaseDocCache,
    extract_text_html, extract_text_pdf,
)

HTML = "<html><head><title>t</title><style>x{}</style></head><body><nav>меню</nav><h1>Постановление</h1><p>Пункт 1.</p><script>alert(1)</script></body></html>"


def _pdf_bytes() -> bytes:
    w = PdfWriter(); w.add_blank_page(width=200, height=200)
    buf = io.BytesIO(); w.write(buf); return buf.getvalue()


def _client(routes: dict[str, httpx.Response]):
    def handler(request):
        return routes.get(str(request.url), httpx.Response(404))
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_extract_text_html_drops_nav_script_style():
    text = extract_text_html(HTML)
    assert "Постановление" in text and "Пункт 1." in text
    assert "alert" not in text and "меню" not in text and "x{}" not in text


def test_extract_text_pdf_blank_page_is_empty_string():
    assert extract_text_pdf(_pdf_bytes()) == ""


def test_fetch_html_and_cache_hit():
    routes = {"https://lex.uz/docs/1": httpx.Response(200, text=HTML, headers={"content-type": "text/html; charset=utf-8"})}
    sleeps = []
    f = DocumentFetcher(cache=InMemoryDocCache(), client=_client(routes), sleep=sleeps.append, clock=lambda: 0.0)
    d1 = f.fetch("https://lex.uz/docs/1")
    assert d1.content_type == "text/html" and "Постановление" in d1.text and len(d1.sha256) == 64
    assert d1.from_cache is False
    d2 = f.fetch("https://lex.uz/docs/1")
    assert d2.from_cache is True and d2.sha256 == d1.sha256


def test_fetch_pdf_by_content_type():
    routes = {"https://gov.uz/a.pdf": httpx.Response(200, content=_pdf_bytes(), headers={"content-type": "application/pdf"})}
    d = DocumentFetcher(client=_client(routes), sleep=lambda s: None).fetch("https://gov.uz/a.pdf")
    assert d.content_type == "application/pdf" and d.text == ""


def test_politeness_delay_per_host():
    routes = {u: httpx.Response(200, text=HTML, headers={"content-type": "text/html"})
              for u in ("https://lex.uz/1", "https://lex.uz/2", "https://gov.uz/1")}
    sleeps, now = [], [100.0]
    f = DocumentFetcher(client=_client(routes), host_delays={"lex.uz": 20.0}, default_delay=1.0,
                        sleep=sleeps.append, clock=lambda: now[0])
    f.fetch("https://lex.uz/1")          # первый запрос к хосту — без ожидания
    f.fetch("https://lex.uz/2")          # тот же хост сразу -> ждать 20
    f.fetch("https://gov.uz/1")          # другой хост — без ожидания
    assert sleeps == [20.0]


def test_http_error_and_too_large_raise():
    routes = {"https://x/404": httpx.Response(404), "https://x/big": httpx.Response(200, content=b"a" * 11, headers={"content-type": "text/plain"})}
    f = DocumentFetcher(client=_client(routes), max_bytes=10, sleep=lambda s: None)
    with pytest.raises(DocFetchError, match="404"):
        f.fetch("https://x/404")
    with pytest.raises(DocFetchError, match="max_bytes"):
        f.fetch("https://x/big")


class _FakeTable:
    def __init__(self, rows): self.rows = rows; self.last = None
    def select(self, *_): return self
    def eq(self, col, val): self._eq = (col, val); return self
    def limit(self, n): return self
    def execute(self):
        from types import SimpleNamespace
        col, val = self._eq
        return SimpleNamespace(data=[r for r in self.rows if r[col] == val])
    def upsert(self, row): self.last = row; self.rows.append(row); return self


class _FakeClient:
    def __init__(self, rows): self.table_ = _FakeTable(rows); self.schema_name = None
    def schema(self, name): self.schema_name = name; return self
    def table(self, name): assert name == "documents"; return self.table_


def test_supabase_cache_roundtrip():
    client = _FakeClient([])
    cache = SupabaseDocCache(client)
    assert cache.get("https://lex.uz/1") is None
    doc = FetchedDoc(url="https://lex.uz/1", final_url="https://lex.uz/1", content_type="text/html",
                     sha256="ab" * 32, text="тело", fetched_at=datetime(2026, 9, 11, tzinfo=timezone.utc))
    cache.put(doc)
    assert client.schema_name == "pipeline"
    got = cache.get("https://lex.uz/1")
    assert got is not None and got.text == "тело" and got.sha256 == "ab" * 32
```

Если `upsert(...).execute()` в реальном клиенте требует `.execute()` — фейк должен это отражать: реализация вызывает `table.upsert(row).execute()`; поправить `_FakeTable.upsert` так, чтобы `execute()` после `upsert` возвращал `SimpleNamespace(data=[row])` (хранить флаг режима).

- [ ] **Step 3: Запустить — падает на ImportError.**

- [ ] **Step 4: Реализация `docfetch.py`**

```python
"""Скачивание и кэш документов для research-режима Cartographer (ADR-0003:
«Cartographer — разовый deep research»; ADR-0002: агентный ресёрч — Railway).

Кэш — `pipeline.documents` (миграция 20260911100000): один и тот же URL
второй раз не качается (вежливость к lex.uz/gov.uz и воспроизводимость:
карта строится по зафиксированному снимку источника, sha256 — в отчёте).
Вежливость: пауза между запросами к одному хосту (`host_delays`, lex.uz —
20 с по его robots.txt `Crawl-delay: 20`; остальные — `default_delay`).
Текст: HTML — BeautifulSoup без script/style/nav/header/footer; PDF — pypdf
(текстовый слой; сканы дают пустую строку — это честный «нет текста», не
ошибка); прочее — как текст."""
```

Ключевые куски:

```python
def extract_text_html(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "nav", "header", "footer", "aside"]):
        tag.decompose()
    lines = [ln.strip() for ln in soup.get_text("\n").splitlines()]
    return "\n".join(ln for ln in lines if ln)


def extract_text_pdf(data: bytes) -> str:
    reader = PdfReader(io.BytesIO(data))
    return "\n".join((page.extract_text() or "").strip() for page in reader.pages).strip()
```

`DocumentFetcher.fetch`: кэш → `dataclasses.replace(doc, from_cache=True)`; иначе `_wait_for_host(host)` (по `clock()` и `self._last_hit[host]`), `client.get(url, follow_redirects=True, headers={"User-Agent": "InspectorX-Research/1.0 (+https://inspectorx.uz)"})`; `httpx.HTTPError` → `DocFetchError`; `status >= 400` → `DocFetchError(f"{url}: HTTP {status}")`; `len(content) > max_bytes` → `DocFetchError(f"{url}: превышен max_bytes={max_bytes}")`; `content_type = resp.headers.get("content-type", "").split(";")[0].strip().lower()`; PDF если `content_type == "application/pdf"` или URL заканчивается на `.pdf`; HTML если `text/html`/`application/xhtml+xml`; иначе `resp.text`; `sha256 = hashlib.sha256(content).hexdigest()`; `fetched_at = datetime.now(timezone.utc)`; `cache.put(doc)`.

`SupabaseDocCache`: `get` → `client.schema("pipeline").table("documents").select("*").eq("url", url).limit(1).execute().data`; `put` → `upsert({...fetched_at.isoformat()}).execute()`.

Миграция `20260911100000_pipeline_documents.sql` — по образцу грантов/RLS `20260803170000_pipeline_schema.sql` (прочитать его и повторить политику: service_role пишет, anon/authenticated — нет):

```sql
-- Кэш скачанных документов research-режима Cartographer (importer/build/docfetch.py).
-- Ключ — URL; sha256 — для отчёта «по какому снимку построена карта».
create table pipeline.documents (
  url text primary key,
  final_url text not null,
  content_type text not null,
  sha256 text not null,
  text text not null,
  fetched_at timestamptz not null default now()
);
comment on table pipeline.documents is 'Кэш документов research-режима Cartographer: URL -> текст + sha256 снимка';
-- гранты/RLS — как у остальных таблиц pipeline (см. 20260803170000_pipeline_schema.sql)
```

- [ ] **Step 5: Все тесты зелёные.**

- [ ] **Step 6: Commit**

```bash
git add importer/build/docfetch.py importer/requirements.txt supabase/migrations/20260911100000_pipeline_documents.sql importer/tests/build/test_docfetch.py
git commit -m "feat(importer): docfetch — скачивание HTML/PDF, кэш pipeline.documents, вежливость по хостам"
```

---

### Task 4: Cartographer с реальными источниками (`--research`)

**Files:**
- Create: `importer/build/research.py`
- Modify: `importer/build/cartographer.py`
- Modify: `importer/build/question_writer.py:32-38` (`MapItem.from_payload`) + все места, где `MapItem(**entry)` строится из payload (grep `MapItem(` в `importer/build/` и `importer/monitoring/`)
- Modify: `importer/cli.py` (`build map --research`)
- Test: `importer/tests/build/test_research.py` (новый), `importer/tests/build/test_cartographer.py`, `importer/tests/build/test_question_writer.py`

**Interfaces:**
- Consumes: `WebSearcher.search`, `DocumentFetcher.fetch`, `DocFetchError`, `WebSearchError`.
- Produces:
  - `@dataclass(frozen=True) class ResearchSource: url: str; title: str; excerpt: str; sha256: str`
  - `class ResearchToolkit: __init__(self, searcher: WebSearcher, fetcher: DocumentFetcher, *, max_queries: int = 6, max_docs: int = 8, excerpt_chars: int = 3000)`; `gather(self, queries: list[str]) -> list[ResearchSource]` (дедуп по URL, ошибки скачивания/поиска пропускаются, собираются в `self.skipped: list[tuple[str, str]]`).
  - `Cartographer.__init__(..., toolkit: ResearchToolkit | None = None)`; `build_map` при toolkit: `_plan_queries(group_ref, jurisdiction, model) -> list[str]` (LLM-вызов: СТРОГО JSON-массив строк, до `max_queries`, запросы на русском и узбекском), `toolkit.gather(...)`, промпт с блоком «Источники», айтемы получают необязательное поле `sources: list[str]` (URL из блока). `CartographerReport.sources_used: int = 0`.
  - `MapItem.from_payload(entry: dict) -> MapItem` — берёт только известные поля (`expected_item, category_slug, rationale, benchmark_countries`), лишние (`sources`) игнорирует.

- [ ] **Step 1: Тесты `ResearchToolkit` (падают)**

```python
from importer.build.docfetch import DocFetchError, FetchedDoc
from importer.build.research import ResearchSource, ResearchToolkit
from importer.build.websearch import WebSearchError


class _Searcher:
    def __init__(self, table): self.table = table; self.queries = []
    def search(self, q):
        self.queries.append(q)
        if isinstance(self.table.get(q), Exception): raise self.table[q]
        return self.table.get(q, [])


class _Fetcher:
    def __init__(self, docs): self.docs = docs; self.urls = []
    def fetch(self, url):
        self.urls.append(url)
        if isinstance(self.docs.get(url), Exception): raise self.docs[url]
        return self.docs[url]


def _doc(url, text):
    from datetime import datetime, timezone
    return FetchedDoc(url=url, final_url=url, content_type="text/html", sha256="0" * 64,
                      text=text, fetched_at=datetime(2026, 9, 11, tzinfo=timezone.utc))


def test_gather_dedupes_urls_skips_failures_and_truncates():
    searcher = _Searcher({
        "q1": [{"title": "A", "url": "https://lex.uz/1", "snippet": ""},
               {"title": "B", "url": "https://gov.uz/2", "snippet": ""}],
        "q2": [{"title": "A2", "url": "https://lex.uz/1", "snippet": ""}],
        "q3": WebSearchError("serper API 500"),
    })
    fetcher = _Fetcher({"https://lex.uz/1": _doc("https://lex.uz/1", "x" * 5000),
                        "https://gov.uz/2": DocFetchError("HTTP 404")})
    kit = ResearchToolkit(searcher, fetcher, excerpt_chars=100)
    sources = kit.gather(["q1", "q2", "q3"])
    assert [s.url for s in sources] == ["https://lex.uz/1"]
    assert len(sources[0].excerpt) == 100 and sources[0].title == "A"
    assert fetcher.urls == ["https://lex.uz/1", "https://gov.uz/2"]
    assert ("https://gov.uz/2", "HTTP 404") in kit.skipped and ("q3", "serper API 500") in kit.skipped


def test_gather_respects_max_queries_and_max_docs():
    searcher = _Searcher({f"q{i}": [{"title": "", "url": f"https://lex.uz/{i}", "snippet": ""}] for i in range(10)})
    fetcher = _Fetcher({f"https://lex.uz/{i}": _doc(f"https://lex.uz/{i}", "t") for i in range(10)})
    kit = ResearchToolkit(searcher, fetcher, max_queries=3, max_docs=2)
    assert len(kit.gather([f"q{i}" for i in range(10)])) == 2
    assert searcher.queries == ["q0", "q1", "q2"]
```

Тесты Cartographer (в `test_cartographer.py`, рядом с существующими — посмотреть, как там сделан `ScriptedLLM`/store, и повторить их фейки):

```python
def test_research_mode_plans_queries_and_cites_sources():
    # первый ответ LLM — план запросов, второй — карта с sources
    llm = ScriptedLLM(['["маркировка молока Узбекистан", "sut mahsulotlari markirovka"]',
                       '[{"expected_item": "Маркировать на гос. языке", "category_slug": "marking", '
                       '"rationale": "…", "benchmark_countries": ["KZ"], "sources": ["https://lex.uz/1"]}]'])
    kit = ResearchToolkit(_Searcher({...}), _Fetcher({...}))
    store = FakeStore(category_slugs=["marking"])
    report = Cartographer(store, llm, toolkit=kit).build_map("0401", "UZ")
    assert report.items_count == 1 and report.sources_used == 1
    assert store.saved_payload[0]["sources"] == ["https://lex.uz/1"]
    assert "Источники" in llm.prompts[1] and "https://lex.uz/1" in llm.prompts[1]


def test_without_toolkit_behavior_unchanged():
    # один LLM-вызов, никакого блока «Источники» — как в Волне 2
    ...


def test_plan_queries_garbage_falls_back_to_group_ref():
    # план не JSON -> один запрос f"{group_ref} требования {jurisdiction}", карта всё равно строится
    ...
```

`MapItem.from_payload` тест: `MapItem.from_payload({"expected_item": "x", "category_slug": "c", "rationale": "r", "benchmark_countries": [], "sources": ["u"]})` → поля без `sources`; отсутствующее `benchmark_countries` → `[]`.

- [ ] **Step 2: Запустить — падают.**

- [ ] **Step 3: Реализация `research.py`**

```python
@dataclass(frozen=True)
class ResearchSource:
    url: str
    title: str
    excerpt: str
    sha256: str


class ResearchToolkit:
    """«Глаза и руки» Cartographer: поиск -> скачивание -> выдержки.
    Ошибки отдельных запросов/страниц не роняют разведку (deep research —
    best effort), но и не молчат: `skipped` идёт в отчёт владельцу."""

    def __init__(self, searcher, fetcher, *, max_queries=6, max_docs=8, excerpt_chars=3000):
        ...
        self.skipped: list[tuple[str, str]] = []

    def gather(self, queries: list[str]) -> list[ResearchSource]:
        self.skipped = []
        seen: dict[str, SearchResult] = {}
        for q in queries[: self._max_queries]:
            try:
                for r in self._searcher.search(q):
                    seen.setdefault(r["url"], r)
            except WebSearchError as exc:
                self.skipped.append((q, str(exc)))
        sources = []
        for url, r in seen.items():
            if len(sources) >= self._max_docs:
                break
            try:
                doc = self._fetcher.fetch(url)
            except DocFetchError as exc:
                self.skipped.append((url, str(exc)))
                continue
            sources.append(ResearchSource(url=url, title=r["title"],
                                          excerpt=doc.text[: self._excerpt_chars], sha256=doc.sha256))
        return sources
```

Cartographer: `_build_prompt` получает `sources: list[ResearchSource] = ()`; при непустом — после строки юрисдикции добавляется:

```
Источники (пронумерованы; опирайся на них, для каждого айтема укажи url источников в поле "sources"):
[1] {title} — {url}
{excerpt}
---
```

и в описании JSON добавляется `"sources": ["url", …]` как необязательное поле. `_plan_queries`:

```python
def _plan_queries(self, group_ref, jurisdiction, model) -> list[str]:
    prompt = (f"{_SYSTEM_PROMPT}\n\nГруппа: {group_ref}\nЮрисдикция: {jurisdiction}\n\n"
              "Составь до 6 поисковых запросов к официальным источникам (нормативные акты, "
              "регуляторы, техрегламенты) для разведки требований к этой группе: половина на "
              "русском, половина на узбекском (латиница). Ответь СТРОГО JSON-массивом строк.")
    answer = self._llm.complete(prompt, model)
    try:
        data = json.loads(answer)
    except json.JSONDecodeError:
        data = None
    if not isinstance(data, list) or not all(isinstance(q, str) and q.strip() for q in data):
        return [f"{group_ref} требования {jurisdiction}"]
    return [q.strip() for q in data][: self._toolkit.max_queries]
```

`build_map`: `sources = self._toolkit.gather(self._plan_queries(...)) if self._toolkit else []`; принятые айтемы сохраняют `sources` (только строки, только из известных URL — лишние отбрасывать); `CartographerReport(..., sources_used=len(sources))`.

`MapItem.from_payload` — classmethod; все `MapItem(**…)` из payload в `orchestrator.py`/`discovery.py`/`impact_mapper.py` перевести на него (grep обязателен; тесты существующие должны остаться зелёными).

CLI: `p_build_map.add_argument("--research", action="store_true", help="разведка по реальным источникам: веб-поиск (WEBSEARCH_BACKEND) + скачивание в pipeline.documents")`; при флаге: `toolkit = ResearchToolkit(get_web_searcher(), DocumentFetcher(cache=SupabaseDocCache(ix)))`; после `build_map` печатать `sources_used` и `toolkit.skipped`.

- [ ] **Step 4: Все тесты зелёные.**

- [ ] **Step 5: Commit**

```bash
git add importer/build/research.py importer/build/cartographer.py importer/build/question_writer.py importer/build/orchestrator.py importer/monitoring importer/cli.py importer/tests/build/test_research.py importer/tests/build/test_cartographer.py importer/tests/build/test_question_writer.py
git commit -m "feat(importer): Cartographer --research — план запросов, реальные источники, sources в айтемах карты"
```

---

### Task 5: Нормализация узбекского скрипта (латиница ↔ кириллица)

**Files:**
- Create: `importer/build/uzscript.py`
- Modify: `importer/build/legalx_mock.py:36-37` (`_words`), `importer/build/eval_golden.py:205-217` (`normalize_act`), `importer/build/agents.py:141-167` (`Retriever.run`)
- Test: `importer/tests/build/test_uzscript.py` (новый), `importer/tests/build/test_agents.py`, `importer/tests/build/test_legalx_mock.py`, `importer/tests/build/test_eval_golden.py`

**Interfaces:**
- Produces:
  - `detect_script(text: str) -> Literal["latin", "cyrillic", "mixed", "none"]` — по буквам (латиница vs кириллица), `mixed` если обе ≥ 20 % от букв.
  - `latin_to_cyrillic(text: str) -> str`, `cyrillic_to_latin(text: str) -> str` — узбекский алфавит, регистр сохраняется.
  - `unify_apostrophes(text: str) -> str` — `‘ ’ ʻ ʼ ` ´` → `'`.
  - `normalize_for_match(text: str) -> str` — `unify_apostrophes` → если кириллица/mixed → `cyrillic_to_latin` → lower → схлопнуть пробелы.
  - `has_uzbek_markers(text: str) -> bool` — кириллица с `ў ғ қ ҳ` или латиница с `o' g'` (после унификации апострофов) — сигнал «это узбекский», не русский.
  - `alt_script(text: str) -> str | None` — другой скрипт того же текста, если `has_uzbek_markers`, иначе `None`.

- [ ] **Step 1: Тесты (падают)**

```python
import pytest

from importer.build.uzscript import (
    alt_script, cyrillic_to_latin, detect_script, has_uzbek_markers, latin_to_cyrillic,
    normalize_for_match, unify_apostrophes,
)


@pytest.mark.parametrize("latin,cyr", [
    ("Oʻzbekiston Respublikasi", "Ўзбекистон Республикаси"),
    ("Vazirlar Mahkamasi qarori", "Вазирлар Маҳкамаси қарори"),
    ("mahsulot", "маҳсулот"),
    ("qonun", "қонун"),
    ("gʻisht", "ғишт"),
    ("shartnoma", "шартнома"),
    ("choʻchqa", "чўчқа"),
    ("yangi", "янги"),
    ("Yoʻriqnoma", "Йўриқнома"),
])
def test_roundtrip_pairs(latin, cyr):
    assert latin_to_cyrillic(latin) == cyr
    assert cyrillic_to_latin(cyr) == latin


def test_unify_apostrophes():
    assert unify_apostrophes("o‘ g’ oʻ gʼ o`") == "o' g' o' g' o'"


def test_detect_script():
    assert detect_script("sut mahsulotlari") == "latin"
    assert detect_script("сут маҳсулотлари") == "cyrillic"
    assert detect_script("sut маҳсулот") == "mixed"
    assert detect_script("2026 №737") == "none"


def test_normalize_for_match_makes_scripts_equal():
    assert normalize_for_match("Ўзбекистон Республикаси Вазирлар Маҳкамаси") == \
           normalize_for_match("O‘zbekiston  Respublikasi Vazirlar Mahkamasi")


def test_has_uzbek_markers_and_alt_script():
    assert has_uzbek_markers("маҳсулот") and has_uzbek_markers("o'zbek")
    assert not has_uzbek_markers("постановление кабинета министров")
    assert alt_script("маҳсулот") == "mahsulot"
    assert alt_script("постановление") is None
```

- [ ] **Step 2: Запустить — падают.**

- [ ] **Step 3: Реализация**

Порядок замен латиница→кириллица: сначала диграфы с апострофом (`o'`→`ў`, `g'`→`ғ`), затем `sh`→`ш`, `ch`→`ч`, `yo`→`ё`, `yu`→`ю`, `ya`→`я`, `ts`→`ц`, затем одиночные (`a б d e f g h i j k l m n o p q r s t u v x y z` → `а б д е ф г ҳ и ж к л м н о п қ р с т у в х й з`), одиночный `'` (тутуқ белгиси) → `ъ`. Регистр: для каждой замены смотреть регистр первой буквы исходного фрагмента и применять `.upper()`/`.capitalize()` к результату. Кириллица→латиница: `ў`→`oʻ`, `ғ`→`gʻ`, `ш`→`sh`, `ч`→`ch`, `ё`→`yo`, `ю`→`yu`, `я`→`ya`, `ц`→`ts`, `ҳ`→`h`, `х`→`x`, `қ`→`q`, `ж`→`j`, `й`→`y`, `ъ`→`ʼ`, `э`→`e`, `ь`→``, `щ`→`sh`, `ы`→`i`, остальные — прямая таблица. Результат `cyrillic_to_latin` использует модификаторную букву `ʻ` (U+02BB) в `oʻ/gʻ` — как в parametrize выше. Реализовать через одну функцию `_translit(text, table)` с regex по ключам таблицы, отсортированным по длине убыв., флаг `re.IGNORECASE` + восстановление регистра.

Точки применения:
- `legalx_mock._words`: `_WORD_RE.findall(normalize_for_match(text))`.
- `eval_golden.normalize_act`: первой строкой `act = normalize_for_match(act)` (дальше как было). Проверить, что существующие тесты `test_eval_golden.py` на `source_acts_match` остаются зелёными (русские заголовки транслитерируются в латиницу одинаково с обеих сторон — равенство сохраняется).
- `Retriever.run`: после первого пустого `search_norms(current_query, …)` — если `alt = alt_script(current_query)` не `None`, один дополнительный `search_norms(alt, jurisdiction)` (в `queries_tried` добавить `alt`); найдено → `found`. Эта попытка не тратит `MAX_REFORMULATIONS`. Тест в `test_agents.py`: LegalX-фейк отвечает пусто на кириллицу и находит на латиницу → `outcome == "found"`, LLM не вызывалась.

- [ ] **Step 4: Все тесты зелёные.**

- [ ] **Step 5: Commit**

```bash
git add importer/build/uzscript.py importer/build/legalx_mock.py importer/build/eval_golden.py importer/build/agents.py importer/tests/build/test_uzscript.py importer/tests/build/test_agents.py importer/tests/build/test_legalx_mock.py importer/tests/build/test_eval_golden.py
git commit -m "feat(importer): нормализация узбекского скрипта — латиница/кириллица в поиске, eval и Retriever"
```

---

### Task 6: `eval-golden --llm live` и `eval-models` для сравнения моделей

**Files:**
- Modify: `importer/cli.py:115-130, 260-290`
- Create: `importer/build/eval_models.py`
- Test: `importer/tests/build/test_eval_models.py` (новый)

**Interfaces:**
- Consumes: `run_eval(items, *, legalx, llm, valid_category_slugs, jurisdiction, models, backend, baseline) -> EvalReport` (`report.to_json_dict()`, `report.markdown`); `RunnerAgentLLM`; `_shared_live_runner`; `load_models_config`.
- Produces:
  - `parse_tier_set(spec: str) -> dict[str, str]` — `"cheap=a,mid=b,expensive=c"` → dict; не хватает тира → `ValueError`.
  - `slug_for(tiers: dict[str, str]) -> str` — `cheap-a__mid-b__expensive-c` (недопустимые символы → `-`).
  - `compare_table(reports: dict[str, dict]) -> str` — markdown-таблица: строки — наборы, колонки `retrieval_hit_rate`, `verifier_pass_on_correct_rate`, `verifier_fail_on_gross_decoy_rate`, `verifier_fail_on_near_miss_decoy_rate`, `category_accuracy`, `lifecycle_date_field_accuracy`, `errors` (сумма `*_errors`).
  - `run_model_sets(items, *, sets: list[dict[str, str]], base_config: ModelsConfig, legalx, llm, valid_category_slugs, out_dir: Path, jurisdiction="UZ") -> dict[str, dict]` — для каждого набора: `ModelsConfig(tiers=set, pricing=base.pricing, providers=base.providers)` → `run_eval(..., models=cfg, backend=f"live:{slug}")` → JSON в `out_dir/<YYYYMMDD-HHMM>-<slug>.json`; возвращает `{slug: to_json_dict}`.
  - CLI: `build eval-golden --llm {mock,live}` (default `mock`); `build eval-models --set <spec>` (repeatable, ≥1) `[--limit N] [--out importer/golden/eval-reports]`.

- [ ] **Step 1: Тесты (падают)**

```python
from pathlib import Path

import pytest

from importer.build.agents import ModelsConfig
from importer.build.eval_models import compare_table, parse_tier_set, run_model_sets, slug_for


def test_parse_tier_set_ok_and_missing():
    assert parse_tier_set("cheap=a,mid=b,expensive=c") == {"cheap": "a", "mid": "b", "expensive": "c"}
    with pytest.raises(ValueError, match="expensive"):
        parse_tier_set("cheap=a,mid=b")


def test_slug_for_sanitizes():
    assert slug_for({"cheap": "gemini/3.1", "mid": "b", "expensive": "c"}) == "cheap-gemini-3.1__mid-b__expensive-c"


def test_compare_table_has_rows_and_columns():
    md = compare_table({"s1": {"retrieval_hit_rate": 0.5, "category_accuracy": 0.9, "retrieval_errors": 1,
                               "verifier_errors": 0, "category_errors": 0, "lifecycle_errors": 0}})
    assert "| s1 |" in md and "0.50" in md and "0.90" in md and "| 1 |" in md


def test_run_model_sets_writes_report_per_set(tmp_path, monkeypatch):
    calls = []
    def fake_run_eval(items, **kw):
        calls.append(kw["models"].tiers)
        class R:
            def to_json_dict(self): return {"retrieval_hit_rate": 1.0, "backend": kw["backend"]}
            markdown = ""
        return R()
    monkeypatch.setattr("importer.build.eval_models.run_eval", fake_run_eval)
    base = ModelsConfig(tiers={"cheap": "x", "mid": "y", "expensive": "z"}, pricing={})
    out = run_model_sets([], sets=[{"cheap": "a", "mid": "b", "expensive": "c"}], base_config=base,
                         legalx=object(), llm=object(), valid_category_slugs=[], out_dir=tmp_path)
    assert list(out) == ["cheap-a__mid-b__expensive-c"]
    assert calls == [{"cheap": "a", "mid": "b", "expensive": "c"}]
    assert len(list(Path(tmp_path).glob("*-cheap-a__mid-b__expensive-c.json"))) == 1
```

- [ ] **Step 2: Запустить — падают.**

- [ ] **Step 3: Реализация `eval_models.py` и CLI**

В CLI `eval-golden`: аргумент `--llm` (`choices=["mock", "live"]`, default `mock`); при `live` → `llm = RunnerAgentLLM(_shared_live_runner)`, `backend = "live"`, печать `tiers` из `load_models_config().tiers` (с учётом env-оверрайдов); при `mock` — как было. `eval-models`: парсит `--set` через `parse_tier_set`, `llm = RunnerAgentLLM(_shared_live_runner)`, `run_model_sets(...)`, печатает `compare_table` и пути JSON. В `--help` обеих команд по-русски напомнить: живой прогон стоит денег — сначала лимиты трат (Волна 3, А5).

- [ ] **Step 4: Все тесты зелёные.**

- [ ] **Step 5: Commit**

```bash
git add importer/cli.py importer/build/eval_models.py importer/tests/build/test_eval_models.py
git commit -m "feat(importer): eval-golden --llm live и eval-models — сравнение наборов моделей по golden set"
```

---

### Task 7: Sentry и аналитика за env-флагами (фронт)

**Files:**
- Create: `src/lib/observability.ts`
- Modify: `src/main.tsx`, `.env.example`, `package.json` (+ `@sentry/react`)
- Test: `src/lib/observability.test.ts`

**Interfaces:**
- Produces:
  - `type ObservabilityEnv = { VITE_SENTRY_DSN?: string; VITE_PLAUSIBLE_DOMAIN?: string; VITE_YM_ID?: string; MODE?: string }`
  - `analyticsScripts(env: ObservabilityEnv): Array<{ src?: string; inline?: string; attrs?: Record<string, string> }>` — чистая функция: Plausible → `{src: 'https://plausible.io/js/script.js', attrs: {defer: '', 'data-domain': domain}}`; Яндекс.Метрика → `{inline: <стандартный сниппет с ym(id, 'init', {...})>}`; пусто → `[]`.
  - `initObservability(env?: ObservabilityEnv): void` — `Sentry.init({dsn, environment: env.MODE, tracesSampleRate: 0.1})` только при DSN; инъекция скриптов аналитики в `document.head`.

- [ ] **Step 1: `npm i @sentry/react`** (точная версия попадёт в package-lock).

- [ ] **Step 2: Тест (падает)**

```ts
import { describe, expect, it } from 'vitest'

import { analyticsScripts } from './observability'

describe('analyticsScripts', () => {
  it('без переменных — пусто', () => {
    expect(analyticsScripts({})).toEqual([])
  })
  it('Plausible по домену', () => {
    const [s] = analyticsScripts({ VITE_PLAUSIBLE_DOMAIN: 'inspectorx.uz' })
    expect(s.src).toContain('plausible.io')
    expect(s.attrs?.['data-domain']).toBe('inspectorx.uz')
  })
  it('Метрика по id', () => {
    const [s] = analyticsScripts({ VITE_YM_ID: '12345' })
    expect(s.inline).toContain("ym(12345, 'init'")
  })
})
```

- [ ] **Step 3: Реализация + вызов `initObservability(import.meta.env)` первой строкой в `main.tsx`** (до `createRoot`). Комментарий по-русски: «включается только при заданных VITE_SENTRY_DSN / VITE_PLAUSIBLE_DOMAIN / VITE_YM_ID; без них — no-op». `.env.example` — три переменные с пояснением.

- [ ] **Step 4: `npm test && npm run build && npm run lint`** — зелёные.

- [ ] **Step 5: Commit**

```bash
git add src/lib/observability.ts src/lib/observability.test.ts src/main.tsx .env.example package.json package-lock.json
git commit -m "feat(front): Sentry и аналитика (Plausible/Метрика) за env-флагами"
```

---

### Task 8: Юридические страницы и контакты за флагом публикации

**Files:**
- Create: `src/legal/docs.ts`, `src/pages/c/CLegalPage.tsx`, `src/pages/c/CContactsPage.tsx`
- Modify: `src/App.tsx`, `src/pages/c/CLayout.tsx:77-88` (подвал), `src/pages/landing-b/LandingB.tsx:470-495` (подвал), `src/i18n/ru.ts` (`footer`, новый раздел `legal`), `src/config.ts`
- Test: `src/legal/docs.test.ts`, `src/i18n/ru.test.ts`

**Interfaces:**
- Produces:
  - `src/config.ts`: `export const COMPANY = { legalName: '', inn: '', address: '', email: 'hello@inspectorx.uz', telegram: '@inspectorx_uz' } as const` + `export const companyRequisitesFilled = () => Boolean(COMPANY.legalName && COMPANY.inn && COMPANY.address)`.
  - `src/legal/docs.ts`: `export type LegalDoc = { slug: 'offer' | 'privacy'; published: boolean; updatedAt: string; sections: Array<{ heading: string; paragraphs: string[] }> }`; `export const LEGAL_DOCS: Record<'offer' | 'privacy', LegalDoc>` — оба `published: false`, `sections: []`; `export const publishedLegalDocs = () => Object.values(LEGAL_DOCS).filter(d => d.published)`.
  - `ru.legal`: `{ offerTitle: 'Публичная оферта', privacyTitle: 'Политика конфиденциальности', contactsTitle: 'Контакты', requisites: 'Реквизиты', notPublished: 'Документ готовится и будет опубликован до начала приёма платежей.', backHome: 'На главную', writeUs: 'Напишите нам' }`.
  - Роуты под `CLayout`: `/legal/offer`, `/legal/privacy`, `/contacts`.
  - Подвалы: ссылки «Оферта» / «Политика конфиденциальности» рисуются только для `published` документов; строка `footer.legal` («— скоро») заменяется: если ни один документ не опубликован — строка не рендерится вовсе (заглушек «скоро» на витрине быть не должно, LAUNCH_CHECKLIST блок B); ссылка «Контакты» — всегда.
  - `/contacts`: email + Telegram всегда; блок «Реквизиты» — только при `companyRequisitesFilled()`.

- [ ] **Step 1: Тесты (падают)**

`src/legal/docs.test.ts`:

```ts
import { describe, expect, it } from 'vitest'

import { LEGAL_DOCS, publishedLegalDocs } from './docs'

describe('LEGAL_DOCS', () => {
  it('оба документа есть и до вычитки юристом не опубликованы', () => {
    expect(Object.keys(LEGAL_DOCS).sort()).toEqual(['offer', 'privacy'])
    expect(publishedLegalDocs()).toEqual([])
  })
})
```

В `ru.test.ts` — блок `describe('ru.legal', …)` с проверкой ключей `offerTitle, privacyTitle, contactsTitle, requisites, notPublished, backHome, writeUs`.

- [ ] **Step 2: Реализация страниц** — стиль как у `CHelpPage.tsx` (посмотреть её разметку и повторить контейнер/типографику). `CLegalPage` принимает `kind: 'offer' | 'privacy'`; если `!doc.published` — заголовок + `ru.legal.notPublished` + ссылка на `/contacts`; иначе секции. `CContactsPage` — заголовок, email (`mailto:`), Telegram (`https://t.me/…`), блок реквизитов по условию. Подвал `CLayout` и `LandingB` — по интерфейсу выше; удалить `footer.legal` из `ru.ts` только если нигде больше не используется (grep).

- [ ] **Step 3: `npm test && npm run build && npm run lint`** — зелёные. Быстрый визуальный чек: `node scripts/shot.mjs /contacts contacts` при запущенном dev-сервере необязателен ночью — пропустить, если dev-сервер не поднят; отметить в отчёте.

- [ ] **Step 4: Commit**

```bash
git add src/legal src/pages/c/CLegalPage.tsx src/pages/c/CContactsPage.tsx src/App.tsx src/pages/c/CLayout.tsx src/pages/landing-b/LandingB.tsx src/i18n/ru.ts src/i18n/ru.test.ts src/config.ts
git commit -m "feat(front): страницы оферты, политики и контактов за флагом публикации, подвал без заглушки «скоро»"
```

---

### Task 9: Черновики оферты и политики конфиденциальности (документы)

**Files:**
- Create: `docs/legal/README.md`, `docs/legal/offer-draft.md`, `docs/legal/privacy-draft.md`

Исполнитель: субагент с WebSearch/WebFetch (проверить действующие нормы РУз, сентябрь 2026). Не код — ревью по чек-листу ниже.

- [ ] **Step 1: Собрать нормативную базу** (в `README.md` — список с URL на lex.uz): ГК РУз ст. 367–369 (оферта, публичная оферта, акцепт), ЗРУ-547 «О персональных данных» (с поправками 2026 о трансграничной передаче), ЗРУ-445 «О защите прав потребителей», ЗРУ-792 «Об электронной коммерции», закон о рекламе (если применимо к рассылкам), правила ИИ (этические правила 17.06.2026 — «финальное решение за человеком»).

- [ ] **Step 2: `offer-draft.md`** — шапка «ЧЕРНОВИК, требует вычитки юристом; не публиковать» и плейсхолдеры `⟨…⟩` для: наименование ИП/ООО, ИНН, адрес, банк, цена тарифа (в коде 490 000 сум — не утверждена), срок подписки. Разделы: термины; предмет (информационный сервис, не юридическая консультация — дословно дисклеймер из `ru.footer.disclaimer`); порядок акцепта (заявка → одобрение → оплата); тариф и оплата; срок и продление; фотоконтроль упаковки (отчёт — предварительный вердикт, ограничение ответственности, хранение оригиналов 30 дней / кропы бессрочно — из PHOTOCONTROL_DECISIONS.md №3, №7); интеллектуальная собственность; ответственность и её пределы; возврат; изменение условий; споры (Ташкент); реквизиты.

- [ ] **Step 3: `privacy-draft.md`** — те же шапка/плейсхолдеры. Разделы: оператор; какие данные (email, имя, телефон из заявки, Telegram-идентификатор при уведомлениях, фото/макеты упаковки, логи); цели; правовые основания (согласие + договор); трансграничная передача (Supabase — серверы вне РУз; Vercel; Sentry/аналитика при включении; провайдеры ИИ-моделей для обработки публичных нормативных текстов — без персональных данных клиента) с указанием, что требует ЗРУ-547 в редакции 2026; сроки хранения (заявки, аккаунт, фото 30 дней); права субъекта; cookies/аналитика; контакты; изменения.

- [ ] **Step 4: Самопроверка по чек-листу** (в конце `README.md`): каждый плейсхолдер перечислен; нет обещаний, которых нет в продукте (сверить с LAUNCH_CHECKLIST и PHOTOCONTROL_DECISIONS); нет упоминания «проверено юристом» (правило дека); формулировки на русском, нейтральные.

- [ ] **Step 5: Commit**

```bash
git add docs/legal
git commit -m "docs(legal): черновики публичной оферты и политики конфиденциальности для вычитки юристом"
```

---

### Task 10: Сверка плана Волны 3 и LAUNCH_CHECKLIST с фактом

**Files:**
- Modify: `docs/superpowers/plans/2026-08-06-photocontrol-wave3-people-and-vendors.md`, `docs/LAUNCH_CHECKLIST.md`

Исполнитель: субагент только с чтением репо (git log, docs, память не доступна — источники: `docs/LAUNCH_CHECKLIST.md`, `docs/INFRA_ACCOUNTS.md`, `docs/ACCESS_GATE_SETUP.md`, `git log --oneline main`, миграции, `api/`).

- [ ] **Step 1:** По каждому чекбоксу треков А–Д: если факт выполнения доказуем из репо (например, миграции `photo_*` в `main` = А6 выполнено; `api/vision/*` и `VISION_WORKER_URL` в коде = А3 частично; воркер задеплоен — из `docs/INFRA_ACCOUNTS.md`/`LAUNCH_CHECKLIST`) — отметить `- [x]` и дописать курсивом `_факт: <ссылка на файл/коммит>_`. Если не доказуемо из репо — оставить `- [ ]` и дописать `_не проверяемо из кода — подтвердить владельцу_`. Ничего не выдумывать.

- [ ] **Step 2:** В `LAUNCH_CHECKLIST.md` — новая ревизия «11.09.2026 (ночная сессия)»: блок D — «◐ черновики оферты и политики в `docs/legal/`, страницы `/legal/*` и `/contacts` в коде за флагом `published`»; блок E — «◐ Sentry и аналитика — код за `VITE_SENTRY_DSN`/`VITE_PLAUSIBLE_DOMAIN`/`VITE_YM_ID`, включаются вставкой env в Vercel»; «Гейт первого живого прогона» — добавить пункты 5–8: раннер провайдеров, поисковые бэкенды, docfetch/Cartographer research, uz-нормализация, `eval-models` — со ссылками на файлы; в «Что реально осталось» — обновить статусы.

- [ ] **Step 3: Commit** — `docs: сверка плана Волны 3 с фактом и ревизия LAUNCH_CHECKLIST 11.09.2026`.

---

### Task 11: ADR-0006 — LLM-провайдеры и поисковый слой контент-фабрики

**Files:**
- Create: `docs/adr/0006-llm-providers.md`

- [ ] **Step 1:** Написать ADR в стиле `docs/adr/0003-agent-flow.md` (шапка: статус **предложено — ждёт решения фаундера**, дата 11.09.2026, связь с ADR-0002/0003/0005). Разделы: Контекст (вопрос про Zro; факты ресёрча 10.09.2026 — кратко, с URL: Zro = MoonMath.ai, подписка $20 = $60 бюджета, EU-шлюз, нет SLA; бенчмарки узбекского: Uzbek Legal RAG arXiv 2608.29284, UzLiB; цены на объём 10M+1M токенов/мес; поисковые API с uz-локалью: Serper, Tavily; Brave — нет; lex.uz: RSS есть, API нет, Crawl-delay 20). Решение 1 — провайдер выбирается конфигурацией (`models.yaml: providers`, `LLM_PROVIDER_*`), а не кодом. Решение 2 — Verifier всегда другая модель, допускается другой провайдер. Решение 3 — выбор тиров только по `eval-models` на golden set, не по прайсу; рабочая гипотеза (Gemini 3.1 Flash-Lite / DeepSeek V4.1 Flash / Sonnet 5) записана как гипотеза. Решение 4 — линия приватности: публичные нормативные тексты — любой провайдер с no-training; данные пользователей/лиды/черновики юриста — только Anthropic/Google/OpenAI по договору. Решение 5 — поисковый слой: Serper (`gl=uz`) + Tavily, allowlist доменов, кэш документов, verbatim-цитата с URL обязательна. Открытые вопросы фаундеру (3 бинарных). Последствия.

- [ ] **Step 2: Commit** — `docs(adr): ADR-0006 — LLM-провайдеры и поисковый слой (предложено)`.

---

### Task 12: Финальная проверка, ночной отчёт, ветка и draft-PR

**Files:**
- Create: `docs/NIGHT_REPORT_2026-09-11.md`

- [ ] **Step 1: Полный прогон**

```bash
/Users/abduraxmonturdiyev/inspector-x-final/.venv-importer/bin/python -m pytest importer/tests -q
npm test && npm run build && npm run lint
```

Все зелёные; числа тестов — в отчёт.

- [ ] **Step 2: Отчёт** `docs/NIGHT_REPORT_2026-09-11.md`, разделы: «Что сделано» (по задачам, с коммитами); «Как включить утром» — пошагово для фаундера без технического бэкграунда: (1) какие env вставить в `.env.importer` (провайдер, ключи, `WEBSEARCH_BACKEND`, allowlist), (2) команда `python -m importer build eval-models --set … --set …` и как читать таблицу, (3) `build map --group <ref> --jurisdiction UZ --research`, (4) Vercel env для Sentry/аналитики; «Что НЕ сделано и почему» (golden set не расширен — Docker/локальная БД выключены; страницы не сняты скриншотами — dev-сервер не поднимался; юр-черновики требуют юриста); «Что смержить и в каком порядке» (чек-лист: миграция `pipeline.documents` накатится автоматически при мёрже — предупредить; `@sentry/react` в бандле без DSN — no-op); «Открытые вопросы фаундеру» (3 бинарных из ADR-0006 + цена + published-флаги).

- [ ] **Step 3: Запушить ветку и открыть draft-PR** (не мержить!)

```bash
git push -u origin worktree-night-factory-2026-09-11
gh pr create --draft --title "Ночь 11.09: фабрика к включению (провайдеры, поиск, research, uz-скрипт) + Sentry/аналитика + юр-страницы" --body-file docs/NIGHT_REPORT_2026-09-11.md
```

Если `gh` отвечает «Repository not found» — `gh auth switch --user TAVI-Agency` и повторить. Если push заблокирован — оставить ветку локальной и написать это в отчёте.

- [ ] **Step 4: Commit отчёта** — `docs: ночной отчёт 11.09.2026`.

---

## Self-review

- **Покрытие**: блок A — Task 1 (раннер), 2 (поиск), 3+4 (глаза/руки Cartographer), 5 (uz-скрипт), 6 (eval моделей); блок B — Task 7 (Sentry/аналитика), 8 (юр-страницы), 9 (черновики), 10 (сверка Волны 3 + LAUNCH_CHECKLIST), 11 (ADR-0006); Task 12 — сборка и отчёт. Расширение golden set до 30–50 актов сознательно исключено: нужна локальная БД (Docker выключен) — записать в отчёт как утреннюю задачу с Docker.
- **Плейсхолдеры**: в задачах 4 и 8 есть «…» внутри примеров тестов — исполнитель обязан заменить их реальными фейками по образцу существующих тестов того же файла (`test_cartographer.py`: как построен `ScriptedLLM`/store), это указано словами рядом.
- **Согласованность имён**: `CallBudget`, `OpenAICompatibleRunner`, `RoutingRunner`, `make_live_runner` (Task 1) ↔ `_shared_live_runner` в CLI (Task 6 использует без изменений); `WebSearchError`, `filter_allowed`, `get_web_searcher` (Task 2) ↔ Task 4; `FetchedDoc`, `DocFetchError`, `DocumentFetcher`, `SupabaseDocCache` (Task 3) ↔ Task 4; `normalize_for_match`, `alt_script` (Task 5); `parse_tier_set`, `slug_for`, `compare_table`, `run_model_sets` (Task 6); `analyticsScripts`, `initObservability` (Task 7); `LEGAL_DOCS`, `publishedLegalDocs`, `COMPANY`, `companyRequisitesFilled`, `ru.legal.*` (Task 8).
