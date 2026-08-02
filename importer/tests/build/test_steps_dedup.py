"""Шаг 'dedup' (Задача 25, ADR-0003 «Блок 2»): эмбеддинги + Classifier на
спорных парах.

Сценарии из докстринга `steps_dedup.py`/task-25-brief.md:

- пара выше `DUP_THRESHOLD_HIGH` -> дубль сразу, без обращения к LLM
  (`ScriptedLLM` пуст — лишний вызов роняет тест);
- пара ниже `DUP_THRESHOLD_LOW` -> не дубль, LLM тоже не вызывается;
- пара МЕЖДУ порогами -> уходит в Classifier: `is_duplicate=true` -> дубль,
  `is_duplicate=false` -> не дубль;
- пустой реестр прогона (первый айтем) -> не дубль, без обращения к LLM;
- структура `ctx.data['dedup']` в обоих исходах;
- шаг всегда завершается `StepResult(status='ok')` — сама детекция дубля не
  повод ретраить айтем.

Косинусная близость управляется НАПРЯМУЮ через `ScriptedEmbedder` (текст ->
заранее заданный вектор) — тот же приём, что `ScriptedLLM` у остальных
шаговых тестов, но для эмбеддингов: детерминированный `hashing_embed` из
`embeddings.py` даёт слишком случайные по сравнению с порогами значения для
точечной проверки границ 0.9/0.75.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import pytest

from importer.build.embeddings import cosine_similarity
from importer.build.steps import ItemContext, ItemRecord
from importer.build.steps_dedup import DUP_THRESHOLD_HIGH, DUP_THRESHOLD_LOW, DedupStep
from importer.tests.build.stores import InMemoryStore

# ── тестовые дублёры ────────────────────────────────────────────────────


@dataclass
class ScriptedEmbedder:
    """Фейковый Embedder: текст -> заранее заданный вектор (словарь).
    Даёт точный контроль над косинусной близостью в тестах — вместо
    случайного bag-of-words хэша реальных текстов."""

    vectors: dict[str, list[float]]

    def embed(self, text: str) -> list[float]:
        try:
            return self.vectors[text]
        except KeyError as exc:
            raise AssertionError(f"ScriptedEmbedder: нет вектора для текста {text!r}") from exc


@dataclass
class ScriptedLLM:
    """Мок AgentLLMClient: отдаёт ответы по очереди, фиксирует все (prompt, model).
    Тот же паттерн, что и в остальных test_steps_*.py."""

    responses: list[str]
    calls: list[tuple[str, str]] = field(default_factory=list)

    def complete(self, prompt: str, model: str) -> str:
        self.calls.append((prompt, model))
        if not self.responses:
            raise AssertionError("ScriptedLLM: запросили ответ сверх скрипта — лишний вызов LLM")
        return self.responses.pop(0)


def is_duplicate_json(value: bool) -> str:
    import json

    return json.dumps({"is_duplicate": value}, ensure_ascii=False)


# Векторы: A и B_HIGH почти совпадают (cos ~1.0 >= 0.9); B_LOW ортогонален
# (cos = 0.0 < 0.75); B_MID даёт cos = 0.8 — строго между порогами.
VEC_A = [1.0, 0.0]
VEC_HIGH = [1.0, 0.0]  # cos(A, HIGH) = 1.0
VEC_LOW = [0.0, 1.0]  # cos(A, LOW) = 0.0
VEC_MID = [0.8, 0.6]  # |VEC_MID| = 1.0 -> cos(A, MID) = 0.8


def _assert_between_thresholds(score: float) -> None:
    assert DUP_THRESHOLD_LOW <= score < DUP_THRESHOLD_HIGH, (
        f"тестовый вектор должен давать спорную близость между порогами, получили {score}"
    )


def test_fixture_scores_land_where_expected():
    """Пин-тест самих фикстур: HIGH >= порога, LOW < низкого порога, MID — между."""
    assert cosine_similarity(VEC_A, VEC_HIGH) >= DUP_THRESHOLD_HIGH
    assert cosine_similarity(VEC_A, VEC_LOW) < DUP_THRESHOLD_LOW
    _assert_between_thresholds(cosine_similarity(VEC_A, VEC_MID))


def make_ctx(
    store: InMemoryStore,
    *,
    item_id: str = "item-current",
    run_id: str = "run-1",
    expected_item: str = "текущий айтем",
    summary: str | None = None,
) -> ItemContext:
    item = ItemRecord(id=item_id, run_id=run_id, expected_item=expected_item)
    store.items[item_id] = item
    ctx = ItemContext(item=item)
    if summary is not None:
        ctx.data["summary"] = summary
    return ctx


def add_processed_item(
    store: InMemoryStore, *, item_id: str, run_id: str = "run-1", text: str
) -> None:
    """Регистрирует УЖЕ обработанный айтем прогона в сторе (см. докстринг
    `steps_dedup.py`: dedup сравнивает текущий айтем только с теми, кто уже
    прошёл конвейер целиком)."""
    store.items[item_id] = ItemRecord(id=item_id, run_id=run_id, expected_item=text)


# ── выше HIGH -> дубль без LLM ───────────────────────────────────────────


def test_score_above_high_threshold_is_duplicate_without_llm():
    store = InMemoryStore()
    add_processed_item(store, item_id="item-prev", text="прошлый айтем")
    ctx = make_ctx(store, summary="текущий summary")

    embedder = ScriptedEmbedder({"текущий summary": VEC_A, "прошлый айтем": VEC_HIGH})
    llm = ScriptedLLM([])  # LLM вызываться не должна
    step = DedupStep(llm, store, embedder)

    result = step(ctx)

    assert result.status == "ok"
    assert ctx.data["dedup"]["duplicate_of"] == "item-prev"
    assert llm.calls == []


# ── ниже LOW -> не дубль без LLM ─────────────────────────────────────────


def test_score_below_low_threshold_is_not_duplicate_without_llm():
    store = InMemoryStore()
    add_processed_item(store, item_id="item-prev", text="прошлый айтем")
    ctx = make_ctx(store, summary="текущий summary")

    embedder = ScriptedEmbedder({"текущий summary": VEC_A, "прошлый айтем": VEC_LOW})
    llm = ScriptedLLM([])  # LLM вызываться не должна
    step = DedupStep(llm, store, embedder)

    result = step(ctx)

    assert result.status == "ok"
    assert ctx.data["dedup"]["duplicate_of"] is None
    assert llm.calls == []


# ── между порогами -> Classifier ─────────────────────────────────────────


def test_score_between_thresholds_classifier_true_is_duplicate():
    store = InMemoryStore()
    add_processed_item(store, item_id="item-prev", text="прошлый айтем")
    ctx = make_ctx(store, summary="текущий summary")

    embedder = ScriptedEmbedder({"текущий summary": VEC_A, "прошлый айтем": VEC_MID})
    llm = ScriptedLLM([is_duplicate_json(True)])
    step = DedupStep(llm, store, embedder)

    result = step(ctx)

    assert result.status == "ok"
    assert ctx.data["dedup"]["duplicate_of"] == "item-prev"
    assert len(llm.calls) == 1


def test_score_between_thresholds_classifier_false_is_not_duplicate():
    store = InMemoryStore()
    add_processed_item(store, item_id="item-prev", text="прошлый айтем")
    ctx = make_ctx(store, summary="текущий summary")

    embedder = ScriptedEmbedder({"текущий summary": VEC_A, "прошлый айтем": VEC_MID})
    llm = ScriptedLLM([is_duplicate_json(False)])
    step = DedupStep(llm, store, embedder)

    result = step(ctx)

    assert result.status == "ok"
    assert ctx.data["dedup"]["duplicate_of"] is None
    assert len(llm.calls) == 1


# ── пустой реестр (первый айтем прогона) -> не дубль ─────────────────────


def test_empty_run_registry_is_not_duplicate_without_llm():
    store = InMemoryStore()
    ctx = make_ctx(store, summary="первый айтем прогона")

    embedder = ScriptedEmbedder({"первый айтем прогона": VEC_A})
    llm = ScriptedLLM([])
    step = DedupStep(llm, store, embedder)

    result = step(ctx)

    assert result.status == "ok"
    assert ctx.data["dedup"] == {"duplicate_of": None}
    assert llm.calls == []


# ── текущий айтем не сравнивается сам с собой ────────────────────────────


def test_current_item_excluded_from_its_own_candidates():
    """Если store.list_run_item_texts вернул сам текущий item_id (например,
    он уже был создан в БД до старта dedup), шаг не должен сравнивать айтем
    сам с собой."""
    store = InMemoryStore()
    ctx = make_ctx(store, item_id="item-current", summary="текущий summary")
    # сам текущий item уже в store.items (make_ctx его туда положил)

    embedder = ScriptedEmbedder({"текущий summary": VEC_A})
    llm = ScriptedLLM([])
    step = DedupStep(llm, store, embedder)

    result = step(ctx)

    assert result.status == "ok"
    assert ctx.data["dedup"] == {"duplicate_of": None}
    assert llm.calls == []


# ── вход сравнения: summary, если есть, иначе expected_item ─────────────


def test_uses_summary_when_present_not_expected_item():
    store = InMemoryStore()
    add_processed_item(store, item_id="item-prev", text="прошлый айтем")
    ctx = make_ctx(
        store,
        expected_item="сырой ожидаемый текст из карты",
        summary="итоговый summary после шага summary",
    )

    embedder = ScriptedEmbedder(
        {"итоговый summary после шага summary": VEC_A, "прошлый айтем": VEC_HIGH}
    )
    llm = ScriptedLLM([])
    step = DedupStep(llm, store, embedder)

    result = step(ctx)

    assert result.status == "ok"
    assert ctx.data["dedup"]["duplicate_of"] == "item-prev"


def test_falls_back_to_expected_item_when_no_summary():
    store = InMemoryStore()
    add_processed_item(store, item_id="item-prev", text="прошлый айтем")
    ctx = make_ctx(store, expected_item="сырой ожидаемый текст из карты", summary=None)

    embedder = ScriptedEmbedder(
        {"сырой ожидаемый текст из карты": VEC_A, "прошлый айтем": VEC_HIGH}
    )
    llm = ScriptedLLM([])
    step = DedupStep(llm, store, embedder)

    result = step(ctx)

    assert result.status == "ok"
    assert ctx.data["dedup"]["duplicate_of"] == "item-prev"


# ── несколько кандидатов: первый найденный дубль побеждает ──────────────


def test_multiple_candidates_first_match_wins():
    store = InMemoryStore()
    add_processed_item(store, item_id="item-a", text="кандидат A")
    add_processed_item(store, item_id="item-b", text="кандидат B")
    ctx = make_ctx(store, summary="текущий summary")

    embedder = ScriptedEmbedder(
        {
            "текущий summary": VEC_A,
            "кандидат A": VEC_LOW,  # не дубль
            "кандидат B": VEC_HIGH,  # дубль
        }
    )
    llm = ScriptedLLM([])
    step = DedupStep(llm, store, embedder)

    result = step(ctx)

    assert result.status == "ok"
    assert ctx.data["dedup"]["duplicate_of"] == "item-b"


# ── структура ctx.data['dedup'] ──────────────────────────────────────────


def test_dedup_data_structure_when_duplicate_found():
    store = InMemoryStore()
    add_processed_item(store, item_id="item-prev", text="прошлый айтем")
    ctx = make_ctx(store, summary="текущий summary")

    embedder = ScriptedEmbedder({"текущий summary": VEC_A, "прошлый айтем": VEC_HIGH})
    llm = ScriptedLLM([])
    step = DedupStep(llm, store, embedder)

    step(ctx)

    dedup = ctx.data["dedup"]
    assert set(dedup.keys()) == {"duplicate_of", "score"}
    assert dedup["duplicate_of"] == "item-prev"
    assert isinstance(dedup["score"], float)
    assert math.isclose(dedup["score"], 1.0, rel_tol=1e-9)


def test_dedup_data_structure_when_no_duplicate():
    store = InMemoryStore()
    ctx = make_ctx(store, summary="первый айтем прогона")

    embedder = ScriptedEmbedder({"первый айтем прогона": VEC_A})
    llm = ScriptedLLM([])
    step = DedupStep(llm, store, embedder)

    step(ctx)

    assert ctx.data["dedup"] == {"duplicate_of": None}


# ── шаг никогда не возвращает fail из-за самой детекции ──────────────────


def test_step_always_returns_ok_status():
    """Сама детекция дубля/не-дубля — не повод ретраить/эскалировать айтем
    (см. докстринг `steps_dedup.py`)."""
    store = InMemoryStore()
    ctx = make_ctx(store, summary="текущий summary")

    embedder = ScriptedEmbedder({"текущий summary": VEC_A})
    llm = ScriptedLLM([])
    step = DedupStep(llm, store, embedder)

    result = step(ctx)

    assert result.status == "ok"
