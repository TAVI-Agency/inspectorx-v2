"""Мок LegalX/SudX на фикстурах — контур Build до готовности живого поиска.

Данные — `importer/build/fixtures/*.json`:
- `norms_uz.json` — 10 реальных фрагментов ТР «О безопасности табачной
  продукции» (ПКМ-290), выписанных verbatim из уже опубликованного контента
  сигарет (`supabase/migrations/20260711130000_v1_content.sql`, таблица
  `act_paragraphs`). `fragment_id`/`act_id` — реальные UUID оттуда же.
- `norms_kz.json` — пустой массив: живого КЗ-контента в LegalX ещё нет,
  `search_norms(..., jurisdiction='KZ')` должен честно возвращать пусто, а не
  выдумывать данные.
- `cases_uz.json` — синтетические, но правдоподобные кейсы по статьям КоАО,
  уже встречающимся в моках требований сигарет (`ст. 204 КоАО` и похожие —
  см. `src/data/mock/fixtures.ts`). Судебная практика — только УЗ (ADR-0005).

Ранжирование `search_norms` — простое пересечение множеств слов запроса и
текста фрагмента (лоуэркейс, без стемминга и внешних зависимостей). Это
осознанно грубее живого гибридного поиска LegalX (pgvector + FTS) — контракт
(`legalx.py`) от качества ранжирования не зависит, задача мока — дать Build
содержательные фикстуры для пилотного прогона, а не имитировать релевантность.
"""
from __future__ import annotations

import json
import re
from datetime import date
from decimal import Decimal
from functools import lru_cache
from pathlib import Path

from importer.build.legalx import CourtCase, NormFragment

_FIXTURES_DIR = Path(__file__).parent / "fixtures"

# Только буквы/цифры/подчёркивание/апостроф — латиница и кириллица считаются
# «словом» одинаково (\w в Python 3 юникодный по умолчанию для str-паттернов).
_WORD_RE = re.compile(r"[\w']+", re.UNICODE)

# УЗ и КЗ — единственные юрисдикции с файлом фикстур на сейчас (ОАЭ по
# ADR-0002 в топологии есть, но контента для неё ещё нет — как и для КЗ).
_JURISDICTION_FILES = {"UZ": "norms_uz.json", "KZ": "norms_kz.json"}


def _words(text: str) -> set[str]:
    return set(_WORD_RE.findall(text.lower()))


def _parse_date(value: str | None) -> date | None:
    return date.fromisoformat(value) if value else None


@lru_cache(maxsize=None)
def _load_json(filename: str) -> list[dict]:
    path = _FIXTURES_DIR / filename
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def _load_norms(jurisdiction: str) -> list[dict]:
    filename = _JURISDICTION_FILES.get(jurisdiction)
    if filename is None:
        # Юрисдикция без фикстур (пока) — пустой результат, не ошибка:
        # семантику «нормы нет в стране» решает Retriever выше по стеку.
        return []
    return _load_json(filename)


def _load_cases() -> list[dict]:
    return _load_json("cases_uz.json")


class MockLegalX:
    """Мок `LegalXClient` (Protocol из `legalx.py`) на статичных фикстурах."""

    def search_norms(
        self,
        query: str,
        jurisdiction: str,
        domains: list[str] | None = None,
        limit: int = 10,
    ) -> list[NormFragment]:
        # domains пока не фильтрует — все УЗ-фикстуры и так узкие (сигареты),
        # доменный метафильтр появится вместе с живым LegalX (Задача 42).
        query_words = _words(query)
        scored: list[tuple[float, dict]] = []
        if query_words:
            for record in _load_norms(jurisdiction):
                overlap = query_words & _words(record["content"])
                if not overlap:
                    continue
                scored.append((len(overlap) / len(query_words), record))
        scored.sort(key=lambda pair: pair[0], reverse=True)
        return [
            NormFragment(
                fragment_id=record["fragment_id"],
                act_id=record["act_id"],
                act_title=record["act_title"],
                article_ref=record["article_ref"],
                anchor=record["anchor"],
                content=record["content"],
                act_status=record["act_status"],
                valid_from=_parse_date(record.get("valid_from")),
                valid_to=_parse_date(record.get("valid_to")),
                score=score,
            )
            for score, record in scored[:limit]
        ]

    def search_cases(
        self,
        article: str,
        topic: str | None = None,
        limit: int = 5,
    ) -> list[CourtCase]:
        article_key = article.strip().lower()
        topic_words = _words(topic) if topic else None
        matched = []
        for record in _load_cases():
            if record["article"].strip().lower() != article_key:
                continue
            if topic_words is not None:
                haystack = _words(record["case_title"] + " " + record["summary"])
                if not (topic_words & haystack):
                    continue
            matched.append(record)
        return [
            CourtCase(
                case_url=record["case_url"],
                case_title=record["case_title"],
                summary=record["summary"],
                outcome=record["outcome"],
                amount=(
                    Decimal(str(record["amount"]))
                    if record.get("amount") is not None
                    else None
                ),
            )
            for record in matched[:limit]
        ]
