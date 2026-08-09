"""Контракт веб-поиска для Template hunter (шаг 'samples', Задача 23,
ADR-0003 «Блок 2»).

Тот же паттерн, что и `importer.build.legalx.get_client` (докстринг
`legalx.py`): `Protocol` описывает контракт, фабрика `get_web_searcher`
переключается через env. Живая реализация (Волна 2, Задача 9) — server-side
инструмент `web_search_20260209` Claude API; клиент лениво инициализируется
при первом реальном вызове `.search(...)`, не при импорте/регистрации шага.
В отличие от `LegalXClient` у веб-поиска нет мок-бэкенда на фикстурах — в
тестах `TemplateHunter` (`steps_samples_lawyer.py`) получает `WebSearcher`
напрямую инъекцией (`FakeWebSearcher`), реестр `_REGISTRY`/фикстуры здесь не
нужны."""
from __future__ import annotations

import os
from typing import Protocol, TypedDict, runtime_checkable


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


class _LiveWebSearcher:
    """Живой веб-поиск: server-side инструмент web_search Claude API.

    Модель просят вернуть СТРОГО JSON-массив находок — парсим текстовые блоки,
    а не внутренности tool_result (их формат — деталь провайдера). Мусорный
    ответ = пустой список: контракт WebSearcher трактует пусто как «не нашёл».
    """

    MODEL = "claude-sonnet-5"   # web_search_20260209 требует Sonnet 4.6+ / Opus 4.6+ (models.yaml: tiers.mid)
    MAX_RESUMES = 2             # server-side цикл может вернуть pause_turn

    def __init__(self, client=None, max_uses: int = 3) -> None:
        self._client = client
        self._max_uses = max_uses

    def _ensure_client(self):
        if self._client is None:
            from importer.build.llm_live import AnthropicRunner  # noqa: F401  (load_dotenv)
            import anthropic
            self._client = anthropic.Anthropic()
        return self._client

    def search(self, query: str) -> list[SearchResult]:
        import json

        client = self._ensure_client()
        prompt = (
            "Найди в интернете официальные шаблоны/образцы документов по запросу. "
            'Верни СТРОГО JSON-массив (до 5 элементов) объектов '
            '{"title": str, "url": str, "snippet": str} без пояснений и markdown.\n'
            f"Запрос: {query}")
        messages = [{"role": "user", "content": prompt}]
        tools = [{"type": "web_search_20260209", "name": "web_search",
                  "max_uses": self._max_uses}]
        resp = client.messages.create(
            model=self.MODEL, max_tokens=2048, tools=tools, messages=messages)
        for _ in range(self.MAX_RESUMES):
            if resp.stop_reason != "pause_turn":
                break
            messages = messages + [{"role": "assistant", "content": resp.content}]
            resp = client.messages.create(
                model=self.MODEL, max_tokens=2048, tools=tools, messages=messages)
        text = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")
        start, end = text.find("["), text.rfind("]")
        if start == -1 or end <= start:
            return []
        try:
            data = json.loads(text[start:end + 1])
        except json.JSONDecodeError:
            return []
        return [SearchResult(title=str(r.get("title", "")), url=str(r.get("url", "")),
                              snippet=str(r.get("snippet", "")))
                for r in data if isinstance(r, dict) and r.get("url")]


def get_web_searcher() -> WebSearcher:
    """Фабрика `WebSearcher`, переключается через env `WEBSEARCH_BACKEND`.

    - `live` (или переменная не задана) -> `_LiveWebSearcher`,
      `NotImplementedError` только при реальном вызове `.search(...)`.
    - любое другое значение -> `ValueError`: опечатка в конфигурации лучше
      падает сразу, чем молча откатывается на живую реализацию.
    """
    backend = os.environ.get("WEBSEARCH_BACKEND", "live")
    if backend == "live":
        return _LiveWebSearcher()
    raise ValueError(
        f"Неизвестный WEBSEARCH_BACKEND={backend!r}: ожидается 'live'"
    )
