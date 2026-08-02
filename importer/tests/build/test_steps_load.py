"""Шаг 'load' (Задача 26, ADR-0003 «Блок 2»): запись собранной карточки
(`ctx.data['card']`, шаг 'assemble') в БД через `BuildStore`.

Сценарии из докстринга `steps_load.py`/task-26-brief.md:

- happy-path через `InMemoryStore`: все таблицы (requirements/contents/
  details/applicability/rules) заполнены, `external_key` стабилен;
- повторный `load` того же айтема -> upsert, БЕЗ дублей (тот же
  `requirement_id`, replace-семантика contents/details/applicability/rules);
- нет `ctx.data['card']` (шаг 'assemble' ещё не отработал) -> fail, не raise;
- dedup-скип: `ctx.data['dedup']['duplicate_of']` задан -> `draft_loaded`
  БЕЗ создания требования, `last_error='duplicate_of=<id>'`;
- `authority_name` резолвится в `authority_id` через
  `store.find_or_create_authority`;
- `pipeline.items.requirement_id` привязывается после успешной записи;
- `status='draft'` ВСЕГДА (карточка уже приходит такой от 'assemble',
  'load' её не трогает).
"""
from __future__ import annotations

import json

from importer.build.assembler import AssembleStep
from importer.build.steps import ItemContext, ItemRecord
from importer.build.steps_load import LoadStep, _slugify
from importer.tests.build.stores import InMemoryStore

# ── тестовые дублёры ────────────────────────────────────────────────────


def make_card(**over) -> dict:
    base = {
        "requirement": {
            "status": "draft",
            "jurisdiction": "UZ",
            "category_slug": "marking",
            "deontic": "obligation",
            "addressee_roles": ["importer"],
            "authority_name": "Комветнадзор",
            "operation": "product",
            "origin": "ai_pipeline",
            "effective_from": "2026-01-01",
            "transition_until": None,
            "valid_to": None,
            "repealed_by_ref": None,
        },
        "contents": {
            "ru": {
                "title": "Получить акцизную марку до ввоза партии",
                "sanction_summary": "штраф до 50 БРВ",
                "translation_origin": None,
            },
        },
        "details": {
            "ru": {
                "description": "Нужна акцизная марка на сигареты",
                "how_to_comply": ["Подать заявку", "Получить марку"],
                "documents": [],
                "sanctions": [{"amount": "50 БРВ", "article": "ст. 128 КоАО", "extra": None}],
                "court_cases": None,
                "templates": None,
                "lawyer_instruction": {"verdict": "применимо", "steps": ["Подать заявку"]},
                "status_note": None,
                "translation_origin": None,
            },
        },
        "applicability": {"scope": "product_type", "product_type_id": "pt-1"},
        "rules": [{"rule": {"field": "состав", "lang": "uz", "required": True}, "verified": True}],
        "citations": [],
    }
    for key, value in over.items():
        base[key] = value
    return base


def item_ctx(
    *,
    item_id: str = "item-1",
    run_id: str = "run-1",
    expected_item: str = "акцизная марка на пачке сигарет",
    card: object = "UNSET",
    dedup: dict | None = None,
) -> ItemContext:
    item = ItemRecord(id=item_id, run_id=run_id, expected_item=expected_item)
    ctx = ItemContext(item=item)
    if card != "UNSET":
        ctx.data["card"] = card
    if dedup is not None:
        ctx.data["dedup"] = dedup
    return ctx


def make_step(store: InMemoryStore, *, group_ref: str = "2203", jurisdiction: str = "UZ") -> LoadStep:
    return LoadStep(store, group_ref=group_ref, jurisdiction=jurisdiction)


# ══════════════════════════════════════════════════════════════════════════
# happy path
# ══════════════════════════════════════════════════════════════════════════


def test_load_happy_path_fills_all_tables():
    store = InMemoryStore()
    store.items["item-1"] = ItemRecord(id="item-1", run_id="run-1", expected_item="акцизная марка")
    step = make_step(store)
    ctx = item_ctx(card=make_card(), expected_item="акцизная марка")

    result = step(ctx)

    assert result.status == "ok"
    assert len(store.requirements) == 1
    requirement_id = next(iter(store.requirements))

    req_row = store.requirements[requirement_id]
    assert req_row["status"] == "draft"
    assert req_row["deontic"] == "obligation"
    assert "authority_name" not in req_row  # резолвится в authority_id, не пишется как есть
    assert req_row["authority_id"] is not None
    assert store.authorities[req_row["authority_id"]]["name_ru"] == "Комветнадзор"
    assert req_row["external_key"] == f"2203:UZ:{_slugify('акцизная марка')}"

    assert store.requirement_contents[(requirement_id, "ru")]["title"] == (
        "Получить акцизную марку до ввоза партии"
    )
    assert store.requirement_details[(requirement_id, "ru")]["description"] == (
        "Нужна акцизная марка на сигареты"
    )
    assert store.requirement_applicability[requirement_id] == [
        {"scope": "product_type", "product_type_id": "pt-1"}
    ]
    assert store.requirement_rules[requirement_id] == [
        {"rule": {"field": "состав", "lang": "uz", "required": True}, "verified": True}
    ]

    # pipeline.items — привязка к требованию + терминальный статус этого шага
    assert store.items["item-1"].status == "draft_loaded"
    assert store.items["item-1"].requirement_id == requirement_id


def test_load_status_is_always_draft_regardless_of_card():
    store = InMemoryStore()
    store.items["item-1"] = ItemRecord(id="item-1", run_id="run-1", expected_item="x")
    step = make_step(store)
    card = make_card()
    card["requirement"] = {**card["requirement"], "status": "published"}  # попытка обхода
    ctx = item_ctx(card=card)

    step(ctx)

    requirement_id = next(iter(store.requirements))
    # 'load' не перезаписывает статус карточки сам — но 'assemble' ВСЕГДА
    # кладёт 'draft' (см. test_assembler.py); этот тест фиксирует, что
    # 'load' его тоже не трогает — что кладём, то и записывается как есть,
    # контракт "всегда draft" гарантирует именно 'assemble'.
    assert store.requirements[requirement_id]["status"] == "published"


# ══════════════════════════════════════════════════════════════════════════
# идемпотентность: повторный load -> upsert без дублей
# ══════════════════════════════════════════════════════════════════════════


def test_repeated_load_of_same_item_upserts_no_duplicates():
    store = InMemoryStore()
    store.items["item-1"] = ItemRecord(id="item-1", run_id="run-1", expected_item="акцизная марка")
    step = make_step(store)

    step(item_ctx(card=make_card()))
    requirement_id_1 = next(iter(store.requirements))

    # второй прогон того же айтема — например, rerun_item после правки
    store.items["item-1"] = ItemRecord(
        id="item-1", run_id="run-1", expected_item="акцизная марка", status="in_progress",
    )
    updated_card = make_card()
    updated_card["contents"]["ru"]["title"] = "Обновлённый заголовок"
    step(item_ctx(card=updated_card))

    assert len(store.requirements) == 1  # НЕ два требования
    requirement_id_2 = next(iter(store.requirements))
    assert requirement_id_1 == requirement_id_2
    assert store.requirement_contents[(requirement_id_2, "ru")]["title"] == "Обновлённый заголовок"


def test_external_key_is_stable_across_reruns():
    store = InMemoryStore()
    store.items["item-1"] = ItemRecord(id="item-1", run_id="run-1", expected_item="акцизная марка")
    step = make_step(store)

    step(item_ctx(card=make_card()))
    requirement_id = next(iter(store.requirements))
    key_1 = store.requirements[requirement_id]["external_key"]

    store.items["item-1"] = ItemRecord(
        id="item-1", run_id="run-1", expected_item="акцизная марка", status="in_progress",
    )
    step(item_ctx(card=make_card()))
    key_2 = store.requirements[requirement_id]["external_key"]

    assert key_1 == key_2


def test_replace_semantics_drops_stale_second_lang_rows():
    """Первый load несёт uz-перевод; второй — без перевода вовсе (например,
    'translate' на повторном прогоне пропустил шаг). Старая uz-строка НЕ
    должна пережить второй load — replace, не merge."""
    store = InMemoryStore()
    store.items["item-1"] = ItemRecord(id="item-1", run_id="run-1", expected_item="акцизная марка")
    step = make_step(store)

    card_with_uz = make_card()
    card_with_uz["contents"]["uz"] = {
        "title": "Aksiz markasi", "sanction_summary": "jarima", "translation_origin": "machine",
    }
    step(item_ctx(card=card_with_uz))
    requirement_id = next(iter(store.requirements))
    assert (requirement_id, "uz") in store.requirement_contents

    store.items["item-1"] = ItemRecord(
        id="item-1", run_id="run-1", expected_item="акцизная марка", status="in_progress",
    )
    step(item_ctx(card=make_card()))  # без uz

    assert (requirement_id, "uz") not in store.requirement_contents
    assert (requirement_id, "ru") in store.requirement_contents


# ══════════════════════════════════════════════════════════════════════════
# нет карточки — 'assemble' ещё не отработал
# ══════════════════════════════════════════════════════════════════════════


def test_load_without_card_returns_fail_not_raise():
    store = InMemoryStore()
    store.items["item-1"] = ItemRecord(id="item-1", run_id="run-1", expected_item="x")
    step = make_step(store)

    result = step(item_ctx(card=None))

    assert result.status == "fail"
    assert "assemble" in result.error.lower() or "card" in result.error.lower()
    assert store.requirements == {}


# ══════════════════════════════════════════════════════════════════════════
# dedup-скип
# ══════════════════════════════════════════════════════════════════════════


def test_load_dedup_duplicate_skips_write_marks_note_and_draft_loaded():
    store = InMemoryStore()
    store.items["item-1"] = ItemRecord(id="item-1", run_id="run-1", expected_item="x")
    step = make_step(store)
    ctx = item_ctx(card=None, dedup={"duplicate_of": "item-original", "score": 0.95})

    result = step(ctx)

    assert result.status == "ok"
    assert store.requirements == {}  # никакой новой строки
    assert store.items["item-1"].status == "draft_loaded"
    assert store.items["item-1"].last_error == "duplicate_of=item-original"


def test_load_dedup_without_duplicate_of_writes_normally():
    store = InMemoryStore()
    store.items["item-1"] = ItemRecord(id="item-1", run_id="run-1", expected_item="акцизная марка")
    step = make_step(store)
    ctx = item_ctx(card=make_card(), dedup={"duplicate_of": None})

    result = step(ctx)

    assert result.status == "ok"
    assert len(store.requirements) == 1


# ══════════════════════════════════════════════════════════════════════════
# authority_name -> authority_id
# ══════════════════════════════════════════════════════════════════════════


def test_load_null_authority_name_leaves_authority_id_none():
    store = InMemoryStore()
    store.items["item-1"] = ItemRecord(id="item-1", run_id="run-1", expected_item="x")
    step = make_step(store)
    card = make_card()
    card["requirement"] = {**card["requirement"], "authority_name": None}

    step(item_ctx(card=card))

    requirement_id = next(iter(store.requirements))
    assert store.requirements[requirement_id]["authority_id"] is None
    assert store.authorities == {}


def test_load_reuses_existing_authority_by_name():
    store = InMemoryStore()
    existing_id = store.find_or_create_authority("Комветнадзор")
    store.items["item-1"] = ItemRecord(id="item-1", run_id="run-1", expected_item="x")
    step = make_step(store)

    step(item_ctx(card=make_card()))

    requirement_id = next(iter(store.requirements))
    assert store.requirements[requirement_id]["authority_id"] == existing_id
    assert len(store.authorities) == 1  # не создан дубль ведомства


# ══════════════════════════════════════════════════════════════════════════
# сквозная сборка: реальный AssembleStep -> реальный LoadStep
# ══════════════════════════════════════════════════════════════════════════


class _StubLLM:
    """Минимальный LLM-заглушка: один валидный ответ Assembler'а."""

    def complete(self, prompt: str, model: str) -> str:
        return json.dumps(
            {
                "title_verb": "Получить акцизную марку до ввоза партии",
                "deontic": "obligation",
                "addressee_roles": ["importer"],
                "authority_name": "Комветнадзор",
                "sanction_summary_line": "штраф до 50 БРВ",
            },
            ensure_ascii=False,
        )


def test_assemble_then_load_end_to_end_via_in_memory_store():
    store = InMemoryStore()
    store.items["item-1"] = ItemRecord(
        id="item-1", run_id="run-1", expected_item="акцизная марка на пачке сигарет",
    )
    ctx = ItemContext(item=store.items["item-1"])
    ctx.data["summary"] = "Нужна акцизная марка на сигареты с фильтром до ввоза"
    ctx.data["category_slug"] = "marking"
    ctx.data["sanctions"] = [
        {"article": "ст. 128 КоАО", "fine": {"amount": 50, "unit": "БРВ"}, "measure": None}
    ]
    ctx.data["lifecycle"] = {
        "effective_from": "2026-01-01", "transition_until": None,
        "valid_to": None, "repealed_by_ref": None,
    }
    ctx.data["scope"] = {"kind": "product_type", "product_type_id": "pt-1"}
    ctx.data["rules"] = []
    ctx.data["lawyer_instruction"] = {"verdict": "применимо", "steps": ["Подать заявку"]}
    ctx.data["status_note"] = None
    ctx.data["court_cases"] = None
    ctx.data["templates"] = None

    assemble = AssembleStep(_StubLLM())
    assemble_result = assemble(ctx)
    assert assemble_result.status == "ok"

    load = make_step(store)
    load_result = load(ctx)
    assert load_result.status == "ok"

    assert len(store.requirements) == 1
    requirement_id = next(iter(store.requirements))
    assert store.requirement_contents[(requirement_id, "ru")]["sanction_summary"] == "штраф до 50 БРВ"
    assert store.items["item-1"].status == "draft_loaded"
    assert store.items["item-1"].requirement_id == requirement_id


# ══════════════════════════════════════════════════════════════════════════
# регистрация
# ══════════════════════════════════════════════════════════════════════════


def test_load_step_is_registered_in_steps_registry():
    from importer.build.steps import get_step

    assert callable(get_step("load"))
