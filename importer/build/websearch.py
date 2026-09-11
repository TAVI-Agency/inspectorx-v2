"""Контракт веб-поиска для Template hunter (шаг 'samples', Задача 23,
ADR-0003 «Блок 2»).

Тот же паттерн, что и `importer.build.legalx.get_client` (докстринг
`legalx.py`): `Protocol` описывает контракт, фабрика `get_web_searcher`
переключается через env. Три бэкенда (Задача 2, «ночь 11.09.2026»):

- `live` (по умолчанию) — server-side инструмент `web_search_20260209`
  Claude API, как в Волне 2; клиент лениво инициализируется при первом
  реальном вызове `.search(...)`, не при импорте/регистрации шага;
- `serper` — Google-выдача через serper.dev (`SerperWebSearcher`), с
  узбекской локалью (`gl`/`hl`);
- `tavily` — Tavily Search API (`TavilyWebSearcher`).

`filter_allowed` — allowlist доменов поверх любого бэкенда: полезен, когда
конвейеру нужны только официальные источники (lex.uz, gov.uz…), а не весь
интернет. Тот же паттерн HTTP-раннера на `httpx`, что и
`OpenAICompatibleRunner` (`llm_live.py`): синхронный `httpx.Client`,
инъекция клиента в тестах через `httpx.MockTransport`, HTTP/сетевые ошибки —
в `WebSearchError` (наследник `AgentLLMError` — шаги конвейера уже умеют
превращать её в `fail` айтема).

В отличие от `LegalXClient` у веб-поиска нет мок-бэкенда на фикстурах — в
тестах `TemplateHunter` (`steps_samples_lawyer.py`) получает `WebSearcher`
напрямую инъекцией (`FakeWebSearcher`), реестр `_REGISTRY`/фикстуры здесь не
нужны."""
from __future__ import annotations

import json
import os
from typing import Protocol, TypedDict, runtime_checkable
from urllib.parse import urlsplit

import httpx

from importer.build.llm_client import AgentLLMError


class SearchResult(TypedDict):
    """Одна находка веб-поиска — вход для Hunter'а (Classifier), который
    выбирает из списка находок шаблон документа."""

    title: str
    url: str
    snippet: str


@runtime_checkable
class WebSearcher(Protocol):
    """Контракт веб-поиска, который вызывает Template hunter."""

    def search(self, query: str) -> list[SearchResult]:
        """Поиск в интернете. Пустой результат — «поиск не нашёл», не
        ошибка (та же семантика, что и `LegalXClient.search_norms`)."""
        ...


class WebSearchError(AgentLLMError):
    """HTTP/сетевая ошибка поискового API (или неразбираемый JSON в ответе).
    Пустая выдача (нет ключа `organic`/`results`) — не ошибка, а «не нашёл»
    (тот же контракт, что у `_LiveWebSearcher`)."""


def filter_allowed(results: list[SearchResult], allowed_domains: tuple[str, ...]) -> list[SearchResult]:
    """Allowlist доменов поверх находок бэкенда. Пустой allowlist — без
    ограничений (проходят все находки). Хост считается разрешённым, если он
    равен домену из списка или является его поддоменом (заканчивается на
    `.<домен>`) — так `sub.lex.uz` проходит по `lex.uz`, а `notlex.uz` нет."""
    if not allowed_domains:
        return results

    def ok(url: str) -> bool:
        host = (urlsplit(url).hostname or "").lower()
        return any(host == d or host.endswith("." + d) for d in allowed_domains)

    return [r for r in results if ok(r["url"])]


class SerperWebSearcher:
    """Google-выдача через serper.dev: gl=uz/hl=ru|uz — единственный из
    дешёвых SERP-API с узбекской локалью (ресёрч 10.09.2026)."""

    URL = "https://google.serper.dev/search"

    def __init__(self, api_key: str, *, gl: str = "uz", hl: str = "ru",
                 allowed_domains: tuple[str, ...] = (), num: int = 10,
                 client: httpx.Client | None = None) -> None:
        self._api_key = api_key
        self.gl = gl
        self.hl = hl
        self.allowed_domains = tuple(allowed_domains)
        self._num = num
        self._client = client

    def _ensure_client(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(timeout=30.0)
        return self._client

    def search(self, query: str) -> list[SearchResult]:
        client = self._ensure_client()
        try:
            resp = client.post(
                self.URL, headers={"X-API-KEY": self._api_key},
                json={"q": query, "gl": self.gl, "hl": self.hl, "num": self._num})
        except httpx.HTTPError as exc:
            raise WebSearchError(f"serper недоступен: {exc}") from exc
        if resp.status_code >= 400:
            raise WebSearchError(f"serper API {resp.status_code}: {resp.text[:200]}")
        try:
            organic = resp.json().get("organic") or []
        except json.JSONDecodeError as exc:
            raise WebSearchError(f"serper API: неразбираемый JSON: {exc}") from exc
        results = [SearchResult(title=str(r.get("title", "")), url=str(r.get("link", "")),
                                snippet=str(r.get("snippet", "")))
                   for r in organic if r.get("link")]
        return filter_allowed(results, self.allowed_domains)


class TavilyWebSearcher:
    """Tavily Search API — второй бэкенд веб-поиска (наряду с serper.dev),
    у Tavily свой обход (не Google) и собственный allowlist `include_domains`
    на стороне API; наш `filter_allowed` — повторная страховка на клиенте."""

    URL = "https://api.tavily.com/search"

    def __init__(self, api_key: str, *, country: str | None = "uzbekistan",
                 allowed_domains: tuple[str, ...] = (), max_results: int = 10,
                 client: httpx.Client | None = None) -> None:
        self._api_key = api_key
        self.country = country
        self.allowed_domains = tuple(allowed_domains)
        self._max_results = max_results
        self._client = client

    def _ensure_client(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(timeout=30.0)
        return self._client

    def search(self, query: str) -> list[SearchResult]:
        client = self._ensure_client()
        payload = {"query": query, "search_depth": "basic", "max_results": self._max_results}
        if self.allowed_domains:
            payload["include_domains"] = list(self.allowed_domains)
        if self.country:
            payload["country"] = self.country
        try:
            resp = client.post(
                self.URL, headers={"Authorization": f"Bearer {self._api_key}"}, json=payload)
        except httpx.HTTPError as exc:
            raise WebSearchError(f"tavily недоступен: {exc}") from exc
        if resp.status_code >= 400:
            raise WebSearchError(f"tavily API {resp.status_code}: {resp.text[:200]}")
        try:
            raw_results = resp.json().get("results") or []
        except json.JSONDecodeError as exc:
            raise WebSearchError(f"tavily API: неразбираемый JSON: {exc}") from exc
        results = [SearchResult(title=str(r.get("title", "")), url=str(r.get("url", "")),
                                snippet=str(r.get("content", "")))
                   for r in raw_results if r.get("url")]
        return filter_allowed(results, self.allowed_domains)


class _LiveWebSearcher:
    """Живой веб-поиск: server-side инструмент web_search Claude API.

    Модель просят вернуть СТРОГО JSON-массив находок — парсим текстовые блоки,
    а не внутренности tool_result (их формат — деталь провайдера). Мусорный
    ответ = пустой список: контракт WebSearcher трактует пусто как «не нашёл».

    Сбой клиента (`anthropic.APIStatusError`/`APIConnectionError` и любая
    другая ошибка SDK) — `WebSearchError`, как и у serper/tavily: её родителя
    `AgentLLMError` ловит `ResearchToolkit.gather`, иначе один неудачный
    запрос роняет всю разведку. `allowed_domains` — тот же клиентский
    allowlist, что у остальных бэкендов: без него `docfetch` пошёл бы качать
    любой URL, названный моделью.
    """

    MODEL = "claude-sonnet-5"   # web_search_20260209 требует Sonnet 4.6+ / Opus 4.6+ (models.yaml: tiers.mid)
    MAX_RESUMES = 2             # server-side цикл может вернуть pause_turn

    def __init__(self, client=None, max_uses: int = 3, *,
                 allowed_domains: tuple[str, ...] = ()) -> None:
        self._client = client
        self._max_uses = max_uses
        self.allowed_domains = tuple(allowed_domains)

    def _ensure_client(self):
        if self._client is None:
            from importer.build.llm_live import AnthropicRunner  # noqa: F401  (load_dotenv)
            import anthropic
            self._client = anthropic.Anthropic()
        return self._client

    def _create(self, client, messages, tools):
        """Вызов API с обёрткой любой ошибки клиента в `WebSearchError`
        (типы исключений SDK — деталь провайдера, ловим широко)."""
        try:
            return client.messages.create(
                model=self.MODEL, max_tokens=2048, tools=tools, messages=messages)
        except Exception as exc:
            raise WebSearchError(f"web_search недоступен: {exc}") from exc

    def search(self, query: str) -> list[SearchResult]:
        client = self._ensure_client()
        prompt = (
            "Найди в интернете официальные шаблоны/образцы документов по запросу. "
            'Верни СТРОГО JSON-массив (до 5 элементов) объектов '
            '{"title": str, "url": str, "snippet": str} без пояснений и markdown.\n'
            f"Запрос: {query}")
        messages = [{"role": "user", "content": prompt}]
        tools = [{"type": "web_search_20260209", "name": "web_search",
                  "max_uses": self._max_uses}]
        resp = self._create(client, messages, tools)
        for _ in range(self.MAX_RESUMES):
            if resp.stop_reason != "pause_turn":
                break
            messages = messages + [{"role": "assistant", "content": resp.content}]
            resp = self._create(client, messages, tools)
        text = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")
        start, end = text.find("["), text.rfind("]")
        if start == -1 or end <= start:
            return []
        try:
            data = json.loads(text[start:end + 1])
        except json.JSONDecodeError:
            return []
        results = [SearchResult(title=str(r.get("title", "")), url=str(r.get("url", "")),
                                snippet=str(r.get("snippet", "")))
                   for r in data if isinstance(r, dict) and r.get("url")]
        return filter_allowed(results, self.allowed_domains)


def get_web_searcher() -> WebSearcher:
    """Фабрика `WebSearcher`, переключается через env `WEBSEARCH_BACKEND`.

    - `live` (или переменная не задана) -> `_LiveWebSearcher`; ключ нужен
      только при реальном вызове `.search(...)`, не при сборке шага.
    - `serper` -> `SerperWebSearcher`, требует `SERPER_API_KEY`.
    - `tavily` -> `TavilyWebSearcher`, требует `TAVILY_API_KEY`.
    - любое другое значение -> `ValueError`: опечатка в конфигурации лучше
      падает сразу, чем молча откатывается на живую реализацию.

    `WEBSEARCH_ALLOWED_DOMAINS` (через запятую) — общий allowlist для ВСЕХ
    бэкендов, включая `live` (иначе `docfetch` качал бы любой URL, названный
    моделью); `WEBSEARCH_GL`/`WEBSEARCH_HL` — локаль serper.
    """
    backend = os.environ.get("WEBSEARCH_BACKEND", "live")
    allowed = tuple(d.strip() for d in os.environ.get("WEBSEARCH_ALLOWED_DOMAINS", "").split(",")
                     if d.strip())
    if backend == "live":
        return _LiveWebSearcher(allowed_domains=allowed)
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
    raise ValueError(
        f"Неизвестный WEBSEARCH_BACKEND={backend!r}: ожидается live | serper | tavily"
    )
