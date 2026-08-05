"""`SupabaseBuildStore.save_requirement_draft` (гейт живого прогона,
`docs/LAUNCH_CHECKLIST.md`, пункт 1: транзакционность).

Раньше замена дочерних строк требования (`requirement_contents`/
`requirement_details`/`requirement_applicability`/`requirement_rules`) шла
4×(delete+insert) отдельными PostgREST-вызовами — сбой посередине мог
оставить `published`-требование без контента. Теперь — ОДИН RPC-вызов
`replace_requirement_children` (миграция
`20260804130000_replace_requirement_children.sql`), атомарный на стороне
Postgres.

Эти тесты — БЕЗ реальной БД (`FakeClient`/`FakeTable`/`FakeRPC` из
`importer/tests/fakes.py`, тот же паттерн, что и `test_loader.py`/
`test_dedup.py`): проверяем, ЧТО вызывается (одна RPC вместо четырёх пар
delete/insert) и с КАКИМ payload'ом — формат построчных dict'ов внутри
`p_contents`/`p_details`/`p_applicability`/`p_rules` совпадает с тем, что
раньше собирался для прямого `.insert(...)` (см. `test_steps_load.py:
make_card` — та же форма карточки, что тут).

`InMemoryStore` (стор тестов state machine, `importer/tests/build/stores.py`)
в этой задаче НЕ меняется — она и так атомарна (обычные Python-словари в
памяти, без сети), см. её докстринг."""
from __future__ import annotations

from importer.build.orchestrator import SupabaseBuildStore
from importer.tests.fakes import FakeClient

TABLES = (
    "requirements", "requirement_contents", "requirement_details",
    "requirement_applicability", "requirement_rules", "authorities",
)


def make_card(**over) -> dict:
    # Та же форма карточки, что test_steps_load.py:make_card — держим payload
    # RPC сравнимым с тем, что раньше собирал прямой .insert(...).
    base = {
        "requirement": {
            "status": "draft",
            "jurisdiction": "UZ",
            "external_key": "2203:UZ:hash123",
            "category_slug": "marking",
            "deontic": "obligation",
            "addressee_roles": ["importer"],
            "authority_id": None,
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


def make_store() -> tuple[SupabaseBuildStore, FakeClient]:
    ix = FakeClient({t: [] for t in TABLES})
    return SupabaseBuildStore(ix), ix


def test_save_requirement_draft_calls_single_rpc_not_direct_table_writes():
    """Замена дочерних таблиц идёт ОДНИМ `.rpc('replace_requirement_children',
    ...)` — НЕ прямыми delete/insert на requirement_contents/_details/
    _applicability/_rules (раньше — 8 отдельных вызовов, теперь — 0: вся
    запись внутри SQL-функции, вызываемой в один HTTP round-trip)."""
    store, ix = make_store()

    requirement_id = store.save_requirement_draft(make_card(), item_id="item-1")

    assert requirement_id is not None
    # requirements — обычный insert (не меняется этой задачей)
    assert len(ix.store["requirements"]) == 1
    # дочерние таблицы НЕ тронуты напрямую через .table(...) — вся запись
    # ушла в RPC, фейковый .table() их не видел вовсе
    assert ix.store["requirement_contents"] == []
    assert ix.store["requirement_details"] == []
    assert ix.store["requirement_applicability"] == []
    assert ix.store["requirement_rules"] == []

    rpc_calls = ix.store.get("_rpc_calls", [])
    assert len(rpc_calls) == 1
    name, params = rpc_calls[0]
    assert name == "replace_requirement_children"
    assert params["p_requirement_id"] == requirement_id


def test_save_requirement_draft_rpc_payload_matches_previous_row_shapes():
    """Формат payload'а внутри RPC совпадает с тем, что раньше собирался для
    прямого `.insert(...)` — построчные dict'ы contents/details с 'lang' +
    'requirement_id', applicability одним объектом (не списком, старая
    семантика 0..1 строки), rules списком {'requirement_id','rule','verified'}."""
    store, ix = make_store()

    requirement_id = store.save_requirement_draft(make_card(), item_id="item-1")

    _, params = ix.store["_rpc_calls"][0]

    assert params["p_contents"] == [
        {
            "title": "Получить акцизную марку до ввоза партии",
            "sanction_summary": "штраф до 50 БРВ",
            "translation_origin": None,
            "requirement_id": requirement_id,
            "lang": "ru",
        }
    ]
    assert params["p_details"] == [
        {
            "description": "Нужна акцизная марка на сигареты",
            "how_to_comply": ["Подать заявку", "Получить марку"],
            "documents": [],
            "sanctions": [{"amount": "50 БРВ", "article": "ст. 128 КоАО", "extra": None}],
            "court_cases": None,
            "templates": None,
            "lawyer_instruction": {"verdict": "применимо", "steps": ["Подать заявку"]},
            "status_note": None,
            "translation_origin": None,
            "requirement_id": requirement_id,
            "lang": "ru",
        }
    ]
    assert params["p_applicability"] == {
        "scope": "product_type",
        "product_type_id": "pt-1",
        "requirement_id": requirement_id,
    }
    assert params["p_rules"] == [
        {
            "requirement_id": requirement_id,
            "rule": {"field": "состав", "lang": "uz", "required": True},
            "verified": True,
        }
    ]


def test_save_requirement_draft_without_applicability_or_rules_sends_empty_payload():
    """`applicability=None`/`rules=[]` — старая семантика: applicability
    вообще не вставлялась (`if applicability: insert`), rules — пустой
    insert(no-op). RPC получает `p_applicability=None`/`p_rules=[]` —
    SQL-функция сама трактует их как «ничего не вставлять» (см. миграцию)."""
    store, ix = make_store()

    card = make_card(applicability={}, rules=[])
    requirement_id = store.save_requirement_draft(card, item_id="item-1")

    _, params = ix.store["_rpc_calls"][0]
    assert params["p_applicability"] is None
    assert params["p_rules"] == []
    assert requirement_id is not None


def test_save_requirement_draft_reuses_rpc_on_repeated_load_same_external_key():
    """Повторный `load` того же `external_key` — апдейт `requirements`
    (не insert второй строки) и ОДИН новый RPC-вызов с тем же
    `p_requirement_id` (replace-семантика — актуальный набор строк, не merge
    со старым)."""
    store, ix = make_store()

    first_id = store.save_requirement_draft(make_card(), item_id="item-1")
    second_id = store.save_requirement_draft(
        make_card(contents={"ru": {
            "title": "Изменённый заголовок", "sanction_summary": None, "translation_origin": None,
        }}),
        item_id="item-1",
    )

    assert first_id == second_id
    assert len(ix.store["requirements"]) == 1  # апдейт, не второй insert
    rpc_calls = ix.store["_rpc_calls"]
    assert len(rpc_calls) == 2
    assert rpc_calls[1][1]["p_contents"][0]["title"] == "Изменённый заголовок"


def test_save_requirement_draft_existing_published_preserves_status_and_still_uses_rpc():
    """Апсерт в уже `published` строку — статус НЕ откатывается в 'draft'
    (докстринг `BuildStore.save_requirement_draft`), контент всё равно
    обновляется через тот же ОДИН RPC-вызов."""
    ix = FakeClient({t: [] for t in TABLES})
    ix.store["requirements"].append(
        {"id": "req-existing", "external_key": "2203:UZ:hash123", "status": "published"}
    )
    store = SupabaseBuildStore(ix)

    requirement_id = store.save_requirement_draft(make_card(), item_id="item-1")

    assert requirement_id == "req-existing"
    row = ix.store["requirements"][0]
    assert row["status"] == "published"
    rpc_calls = ix.store["_rpc_calls"]
    assert len(rpc_calls) == 1
    assert rpc_calls[0][1]["p_requirement_id"] == "req-existing"
