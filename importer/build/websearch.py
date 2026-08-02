"""Контракт веб-поиска для Template hunter (шаг 'samples', Задача 23,
ADR-0003 «Блок 2»).

Тот же паттерн, что и `importer.build.legalx.get_client` (докстринг
`legalx.py`): `Protocol` описывает контракт, фабрика `get_web_searcher`
переключается через env, живая реализация — `NotImplementedError`-заглушка,
которая падает только при РЕАЛЬНОМ вызове, не при импорте/регистрации шага.
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
    """Живая реализация — подключается отдельной задачей (тот же принцип,
    что и `LEGALX_BACKEND=live` в `legalx.py`: переключение mock->live
    только по готовности зависимостей, глобальное ограничение ④)."""

    def search(self, query: str) -> list[SearchResult]:
        raise NotImplementedError(
            "Живой веб-поиск для шага 'samples' ещё не подключён — "
            "заработает после пилотного прогона Задачи 27 (см. "
            "importer/build/llm_client.py:RunnerAgentLLM — тот же паттерн "
            "отсрочки, что и у LLM-runner'а/LegalX-клиента)"
        )


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
