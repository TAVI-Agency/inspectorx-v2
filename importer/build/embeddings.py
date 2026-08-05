"""Эмбеддинги для шага 'dedup' (Задача 25, ADR-0003 «Блок 2»).

`Embedder` — тонкий Protocol `{embed(text) -> list[float]}`. Тот же паттерн
отсрочки live/mock, что и `AgentLLMClient` (`llm_client.py`): `LiveEmbedder`
падает `NotImplementedError` только при РЕАЛЬНОМ вызове, не при импорте/
регистрации шага (см. докстринг `steps_norm.py`/`steps_classify.py` — тот же
компромисс). Живая модель эмбеддингов (OpenAI/др. API) подключается позже,
вместе с остальным mock->live переключением Build (стоп-точка ④
`global-constraints.md`).

`hashing_embed`/`FakeEmbedder` — детерминированный bag-of-words эмбеддинг
ТОЛЬКО для тестов: без сети и внешних моделей, один и тот же текст всегда
даёт один и тот же вектор. Для точного контроля косинусной близости в тестах
`test_steps_dedup.py` используется свой `ScriptedEmbedder` (текст -> заранее
заданный вектор) — `FakeEmbedder` здесь нужен только как рабочий дефолт,
если кому-то потребуется детерминированный эмбеддер без ручной раскладки
векторов.

Косинусная близость — своя маленькая функция, чистый Python, без numpy
(конвенция задачи — не тянуть тяжёлую зависимость ради одной формулы).

## Почему не переиспользован `importer/dedup.py`

`importer/dedup.py` — дедуп конвейера ИМПОРТЁРА (другой слой, другая
структура данных): работает поверх уже ОПУБЛИКОВАННЫХ строк `requirements`
через прямой Supabase-клиент `ix` и `external_key = "lexuz:{doc_id}/{ref}"`
(точное совпадение акт+пункт, без эмбеддингов и косинуса вообще — сомнение
там уходит в ручной review, а не считается численно). Здесь дедуп — ДО
публикации, внутри одного прогона Build, по СЕМАНТИЧЕСКОЙ близости текста
(эмбеддинги + косинус), для айтемов, у которых `external_key` в этом смысле
попросту нет. Общего кода между слоями не нашлось — писать заново, не
копипастить, см. отчёт задачи.
"""
from __future__ import annotations

import hashlib
import math
from typing import Protocol, runtime_checkable


@runtime_checkable
class Embedder(Protocol):
    """Контракт эмбеддера для шага 'dedup'."""

    def embed(self, text: str) -> list[float]:
        ...


class LiveEmbedder:
    """Живой эмбеддер — не подключён в этой задаче (см. докстринг модуля).
    Заглушка падает только при РЕАЛЬНОМ вызове `embed`, не при импорте/
    регистрации шага 'dedup' по умолчанию."""

    def embed(self, text: str) -> list[float]:
        raise NotImplementedError(
            "Живой эмбеддер ещё не подключён — заработает после пилотного "
            "прогона Задачи 27 (тот же паттерн отсрочки, что и "
            "importer/build/llm_client.py:RunnerAgentLLM для LLM-вызовов)"
        )


_HASH_DIM = 64  # размерность фейкового bag-of-words эмбеддинга


def _tokenize(text: str) -> list[str]:
    return [tok for tok in text.lower().split() if tok]


def hashing_embed(text: str, dim: int = _HASH_DIM) -> list[float]:
    """Детерминированный bag-of-words эмбеддинг: каждое слово хэшируется в
    индекс вектора размерности `dim` (частоты), вектор L2-нормализуется.
    Одинаковый текст -> одинаковый вектор, никакой сети/внешних моделей —
    только для тестов и как рабочий дефолт `FakeEmbedder`."""
    vec = [0.0] * dim
    for tok in _tokenize(text):
        idx = int(hashlib.sha256(tok.encode("utf-8")).hexdigest(), 16) % dim
        vec[idx] += 1.0
    norm = math.sqrt(sum(v * v for v in vec))
    if norm == 0:
        return vec
    return [v / norm for v in vec]


class FakeEmbedder:
    """Детерминированный фейковый `Embedder` — bag-of-words хэш (см.
    `hashing_embed`), без сети и внешних моделей."""

    def __init__(self, dim: int = _HASH_DIM):
        self._dim = dim

    def embed(self, text: str) -> list[float]:
        return hashing_embed(text, self._dim)


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """Косинусная близость двух векторов — чистый Python, без numpy.
    Нулевой вектор (пустой текст/все токены не хэшировались) даёт близость
    0.0 вместо деления на ноль."""
    if len(a) != len(b):
        raise ValueError(
            f"cosine_similarity: разные размерности векторов ({len(a)} vs {len(b)})"
        )
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)
