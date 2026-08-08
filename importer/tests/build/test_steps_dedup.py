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
from importer.build.orchestrator import MapRecord, Orchestrator
from importer.build.agents import Verdict
from importer.build.steps import STEP_ORDER, ItemContext, ItemRecord, StepResult
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
    store: InMemoryStore,
    *,
    item_id: str,
    run_id: str = "run-1",
    text: str,
    status: str = "published",
) -> None:
    """Регистрирует УЖЕ обработанный айтем прогона в сторе (см. докстринг
    `steps_dedup.py`: dedup сравнивает текущий айтем только с теми, кто уже
    прошёл конвейер целиком). `status='published'` по умолчанию — реальный
    "уже обработанный" статус (см. фикс-раунд ревью Задачи 25:
    `list_run_item_texts` отдаёт только `draft_loaded`/`published`,
    `pending`/`in_progress`/`needs_attention`/`no_norm` — не кандидаты)."""
    store.items[item_id] = ItemRecord(
        id=item_id, run_id=run_id, expected_item=text, status=status
    )


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


# ── пин-тест фикс-раунда: partial rerun_item без ctx.data['summary'] ─────
# должен использовать item.summary_text (сохранённый прошлым прогоном шага
# 'summary'), а не молча падать на expected_item — иначе сравнение
# асимметрично относительно list_run_item_texts, который уже фолбэкается
# на summary_text (см. докстринг BuildStore.list_run_item_texts).


def test_falls_back_to_item_summary_text_when_ctx_data_summary_absent():
    """Partial `rerun_item`, начатый ПОСЛЕ шага 'summary': шаг 'summary' в
    этом прогоне не выполняется (ctx.data['summary'] пуст), но
    `pipeline.items.summary_text` уже записан прошлым прогоном. Текст для
    эмбеддинга должен браться из item.summary_text, не из expected_item."""
    store = InMemoryStore()
    add_processed_item(store, item_id="item-prev", text="прошлый айтем")
    item = ItemRecord(
        id="item-current",
        run_id="run-1",
        expected_item="сырой ожидаемый текст из карты",
        summary_text="сохранённый summary из прошлого прогона",
    )
    store.items["item-current"] = item
    ctx = ItemContext(item=item)  # ctx.data пуст — 'summary' в этом rerun не выполнялся

    embedder = ScriptedEmbedder(
        {"сохранённый summary из прошлого прогона": VEC_A, "прошлый айтем": VEC_HIGH}
    )
    llm = ScriptedLLM([])
    step = DedupStep(llm, store, embedder)

    result = step(ctx)

    assert result.status == "ok"
    assert ctx.data["dedup"]["duplicate_of"] == "item-prev"


def test_ctx_data_summary_takes_priority_over_item_summary_text():
    """Если 'summary' ОТРАБОТАЛ в этом же прогоне (ctx.data['summary'] есть),
    он главнее устаревшего item.summary_text от предыдущего прогона."""
    store = InMemoryStore()
    add_processed_item(store, item_id="item-prev", text="прошлый айтем")
    item = ItemRecord(
        id="item-current",
        run_id="run-1",
        expected_item="сырой ожидаемый текст из карты",
        summary_text="устаревший summary из прошлого прогона",
    )
    store.items["item-current"] = item
    ctx = ItemContext(item=item, data={"summary": "свежий summary этого прогона"})

    embedder = ScriptedEmbedder(
        {"свежий summary этого прогона": VEC_A, "прошлый айтем": VEC_HIGH}
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


# ── фикс-раунд ревью Задачи 25 (Critical): store.list_run_item_texts ────
# фильтрует по статусу — pending/in_progress/needs_attention/no_norm НЕ
# кандидаты, только draft_loaded/published (черновик реально в БД). Без
# фильтра dedup первого айтема видел бы ещё не начатые айтемы прогона
# (create_items создаёт их все пачкой ДО цикла обработки).


def test_store_list_run_item_texts_filters_out_unprocessed_statuses():
    """Прямая проверка фильтра `InMemoryStore.list_run_item_texts`: только
    `draft_loaded`/`published` — кандидаты, остальные статусы (в т.ч. те,
    что есть в check-constraint `pipeline.items`) исключены."""
    store = InMemoryStore()
    add_processed_item(store, item_id="item-pending", text="pending", status="pending")
    add_processed_item(
        store, item_id="item-in-progress", text="in_progress", status="in_progress"
    )
    add_processed_item(
        store,
        item_id="item-needs-attention",
        text="needs_attention",
        status="needs_attention",
    )
    add_processed_item(store, item_id="item-no-norm", text="no_norm", status="no_norm")
    add_processed_item(
        store, item_id="item-draft-loaded", text="draft_loaded", status="draft_loaded"
    )
    add_processed_item(store, item_id="item-published", text="published", status="published")

    item_ids = {row["item_id"] for row in store.list_run_item_texts("run-1")}

    assert item_ids == {"item-draft-loaded", "item-published"}


def test_dedup_step_ignores_pending_candidate_even_if_returned_by_store():
    """Если store (гипотетически, в обход своего собственного фильтра)
    всё же вернул кандидата без статуса draft_loaded/published, шаг сам по
    себе никакого ВТОРОГО фильтра не делает — фильтрация статуса ЦЕЛИКОМ
    обязанность `list_run_item_texts` (см. докстринг `steps_dedup.py`). Этот
    тест фиксирует контракт: `DedupStep` доверяет тому, что вернул стор, и
    сравнивается со всем, что получил, за вычетом только своего item_id."""
    store = InMemoryStore()
    add_processed_item(store, item_id="item-prev", text="прошлый айтем", status="pending")
    ctx = make_ctx(store, summary="текущий summary")

    embedder = ScriptedEmbedder({"текущий summary": VEC_A, "прошлый айтем": VEC_HIGH})
    llm = ScriptedLLM([])
    step = DedupStep(llm, store, embedder)

    result = step(ctx)

    # item-prev в статусе 'pending' -> InMemoryStore.list_run_item_texts его
    # НЕ отдаёт (проверено предыдущим тестом) -> кандидатов у DedupStep нет.
    assert result.status == "ok"
    assert ctx.data["dedup"] == {"duplicate_of": None}


# ── ОБЯЗАТЕЛЬНЫЙ интеграционный тест: реальный Orchestrator.run_group ────


def _ok_step(ctx: ItemContext) -> StepResult:
    # pass-вердикт как у настоящего шага: publish_ready больше не публикует
    # айтем без единого вердикта (план фотоконтроля §3)
    return StepResult(
        status="ok",
        verdicts=[Verdict(passed=True, reason="заглушка: подтверждено", model="stub")],
    )


def test_integration_orchestrator_run_group_dedup_ignores_not_yet_processed_items():
    """Интеграционный тест на сам баг из Critical ревью: `Orchestrator.
    run_group` создаёт ВСЕ айтемы прогона одной пачкой (`create_items`) ДО
    цикла обработки — значит без фильтра по статусу dedup айтема 1 увидел
    бы ещё не начатые (pending) айтемы 2 и 3 у них тоже есть `expected_item`
    в pipeline.items с самого начала прогона.

    Сценарий с настоящим `DedupStep` в реестре шагов (остальные шаги —
    простые ok-фейки, `_ok_step`):
    - айтем 1 на своём 'dedup' видит ПУСТОЙ реестр кандидатов (2 и 3 ещё
      pending — их обработка не начиналась);
    - айтем 2 (дубликат айтема 1 по тексту) на своём 'dedup' видит уже
      ПОЛНОСТЬЮ обработанный (к этому моменту 'published' —
      `Orchestrator` идёт по айтемам строго последовательно, айтем 1
      закончен целиком раньше, чем стартует айтем 2) айтем 1 и схлопывается
      с ним;
    - айтем 3 (не похож ни на кого) не находит дубля, видя уже двух
      обработанных айтемов 1 и 2."""
    store = InMemoryStore()
    store.maps["map-1"] = MapRecord(
        id="map-1",
        group_ref="2203",
        jurisdiction="UZ",
        status="approved",
        payload=[
            {"expected_item": "требование первое"},
            {"expected_item": "требование первое дубль"},
            {"expected_item": "совсем другое требование"},
        ],
    )

    embedder = ScriptedEmbedder(
        {
            "требование первое": VEC_A,
            "требование первое дубль": VEC_HIGH,  # дубль относительно первого
            "совсем другое требование": VEC_LOW,  # не похоже ни на что
        }
    )
    llm = ScriptedLLM([])  # ни одна пара не спорная -> Classifier не нужен
    real_dedup = DedupStep(llm, store, embedder)

    seen_dedup_ctx: list[ItemContext] = []

    def tracking_dedup(ctx: ItemContext) -> StepResult:
        result = real_dedup(ctx)
        seen_dedup_ctx.append(ctx)
        return result

    steps = {name: _ok_step for name in STEP_ORDER}
    steps["dedup"] = tracking_dedup

    orchestrator = Orchestrator(store, steps=steps)
    report = orchestrator.run_group("map-1")

    assert report.total_items == 3
    assert report.published == 3  # все ok-фейки -> все дошли до published
    assert len(seen_dedup_ctx) == 3

    items_by_expected = {item.expected_item: item for item in store.items.values()}
    item1 = items_by_expected["требование первое"]
    item2 = items_by_expected["требование первое дубль"]
    item3 = items_by_expected["совсем другое требование"]

    ctx1, ctx2, ctx3 = seen_dedup_ctx

    assert ctx1.item.id == item1.id
    assert ctx1.data["dedup"] == {"duplicate_of": None}  # реестр пуст: 2 и 3 ещё pending

    assert ctx2.item.id == item2.id
    assert ctx2.data["dedup"]["duplicate_of"] == item1.id  # айтем 1 уже published

    assert ctx3.item.id == item3.id
    assert ctx3.data["dedup"]["duplicate_of"] is None  # не похож ни на 1, ни на 2

    # оба айтема 1 и 2 в итоге published (dedup не блокирует собственный
    # прогресс айтема — см. докстринг steps_dedup.py: "статус НЕ 'merged'")
    assert item1.status == "published"
    assert item2.status == "published"
    assert item3.status == "published"
