"""Контракты LegalX/SudX для контура Build (ADR-0005).

Сигнатуры зафиксированы `docs/adr/0005-ecosystem-contracts.md` — расхождение
реализации с этим документом является багом реализации, а не вариантом
трактовки. LegalX хранит все юрисдикции в одной базе; `jurisdiction` в
`search_norms` — обязательный параметр без значения по умолчанию (см. ADR,
раздел «Топология данных контрактов»). `search_cases` — только УЗ, параметра
`jurisdiction` у него нет намеренно.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Protocol


@dataclass
class NormFragment:
    """Фрагмент нормы права — строка результата `search_norms` в LegalX."""

    fragment_id: str
    act_id: str
    act_title: str  # полное название акта
    article_ref: str  # номер статьи/пункта
    anchor: str  # якорь для deep-link на параграф
    content: str  # текст фрагмента (uz-оригинал + ru-перевод, если есть)
    act_status: str  # active | repealed | pending
    valid_from: date | None
    valid_to: date | None
    score: float


@dataclass
class CourtCase:
    """Судебное дело — строка результата `search_cases` в SudX (только УЗ)."""

    case_url: str
    case_title: str
    summary: str
    outcome: str
    amount: Decimal | None


class LegalXClient(Protocol):
    """Контракт клиента LegalX/SudX, который вызывает воркер InspectorX."""

    def search_norms(
        self,
        query: str,
        jurisdiction: str,
        domains: list[str] | None = None,
        limit: int = 10,
    ) -> list[NormFragment]:
        """Поиск норм в LegalX. Пустой результат = «поиск не нашёл» — это не
        ошибка, семантику «нормы нет в стране» определяет Retriever выше по
        стеку (см. ADR-0005)."""
        ...

    def search_cases(
        self,
        article: str,
        topic: str | None = None,
        limit: int = 5,
    ) -> list[CourtCase]:
        """Поиск судебной практики в SudX по статье санкции. Только УЗ."""
        ...


def get_client() -> LegalXClient:
    """Фабрика клиента LegalX/SudX, переключается через env `LEGALX_BACKEND`.

    - `mock` (или переменная не задана) -> `MockLegalX` на фикстурах
      `importer/build/fixtures/*.json` — пилотный прогон Build без живого
      LegalX.
    - `live` -> `NotImplementedError`: живой клиент добавляется Задачей 42
      (глобальное ограничение ④ — переключение mock->live только по
      готовности LegalX-зависимостей).
    - любое другое значение -> `ValueError`: опечатка в конфигурации лучше
      падает сразу, чем молча откатывается на мок.
    """
    backend = os.environ.get("LEGALX_BACKEND", "mock")
    if backend == "mock":
        from importer.build.legalx_mock import MockLegalX

        return MockLegalX()
    if backend == "live":
        raise NotImplementedError(
            "LEGALX_BACKEND=live: живой клиент LegalX ещё не реализован — "
            "добавляется Задачей 42 (глобальное ограничение ④, переключение "
            "mock->live по готовности LegalX-зависимостей)"
        )
    raise ValueError(
        f"Неизвестный LEGALX_BACKEND={backend!r}: ожидается 'mock' или 'live'"
    )
