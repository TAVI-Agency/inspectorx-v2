"""Cartographer (Задача 15, ADR-0003): двухуровневая карта группы (мир →
страна) + CLI-апрув владельца.

Сценарии из брифа Задачи 15:
- валидный ответ LLM → draft-карта сохраняется через `BuildStore.save_map`,
  все `category_slug` — валидные (проверены против `list_category_slugs()`);
- ответ с неизвестным `category_slug` → айтем НЕ попадает в payload карты,
  а откладывается в `CartographerReport.candidate_categories` («кандидат
  новой категории», решение грила №3 — таксономию расширяет только апрув
  владельца, не сама LLM);
- `set_map_status(..., 'approved', approved_by=...)` переводит
  `draft → approved` и заполняет `approved_at`/`approved_by` (это то, что
  дёргает CLI `build approve-map`); `'rejected'` — без этих полей;
- повторный `build_map` на ту же `(group_ref, jurisdiction)` — upsert:
  перезаписывает draft; поверх уже `approved` карты — `MapAlreadyApprovedError`;
- интеграционная связка build_map → approve-map → run_group на ОДНОМ
  сторе (`InMemoryStore` из `importer/tests/build/stores.py`, том же, что
  и `test_orchestrator.py`) — доказательство, что карта Cartographer'а
  реально прогоняется Orchestrator'ом (фикс-раунд ревью Задачи 15,
  Important: раздельные дублёры BuildStore не ловили это рассинхрон).

Сценарии из брифа Задачи 4 (`--research`):
- с `toolkit` — `_plan_queries` даёт LLM отдельный вызов за планом запросов,
  `toolkit.gather(...)` собирает источники, второй промпт несёт блок
  «Источники», айтемы карты несут `sources` (только известные URL, выдумки
  LLM молча отбрасываются), `CartographerReport.sources_used` — число
  собранных источников;
- без `toolkit` — поведение Волны 2 не меняется: один LLM-вызов, промпт без
  «Источники»;
- план запросов — не JSON/не список строк → откат на единственный запрос
  `f"{group_ref} требования {jurisdiction}"`, карта всё равно строится.

LLM — только инжектируемый скрипт ответов (тот же паттерн, что и
`test_agents.py:ScriptedLLM`), никакого сетевого мокинга.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from importer.build.agents import Verdict, load_models_config
from importer.build.cartographer import Cartographer, CartographerReport
from importer.build.docfetch import FetchedDoc
from importer.build.llm_client import AgentLLMError
from importer.build.orchestrator import MapAlreadyApprovedError, Orchestrator
from importer.build.research import ResearchToolkit
from importer.build.steps import STEP_ORDER, StepResult
from importer.tests.build.stores import InMemoryStore


# ── тестовые дублёры ────────────────────────────────────────────────────


class ScriptedLLM:
    """Мок AgentLLMClient: отдаёт ответы по очереди, фиксирует все (prompt, model)."""

    def __init__(self, responses: list[str]):
        self._responses = list(responses)
        self.calls: list[tuple[str, str]] = []

    def complete(self, prompt: str, model: str) -> str:
        self.calls.append((prompt, model))
        if not self._responses:
            raise AssertionError("ScriptedLLM: запросили ответ сверх скрипта — лишний вызов LLM")
        return self._responses.pop(0)


def map_item(**over) -> dict:
    base = dict(
        expected_item="акцизная марка на пачке сигарет",
        category_slug="marking",
        rationale="во всех бенчмарк-странах маркировка табака обязательна",
        benchmark_countries=["KZ", "AE", "DE"],
    )
    return {**base, **over}


def valid_response(*items: dict) -> str:
    return json.dumps(list(items) or [map_item()], ensure_ascii=False)


# ── build_map: валидный ответ → draft-карта ──────────────────────────────


def test_build_map_saves_draft_with_all_valid_items():
    store = InMemoryStore()
    llm = ScriptedLLM([valid_response(map_item(), map_item(expected_item="ставка НДС на импорт", category_slug="fiscal"))])
    report = Cartographer(store, llm).build_map("2402", "UZ")

    assert isinstance(report, CartographerReport)
    assert report.group_ref == "2402"
    assert report.jurisdiction == "UZ"
    assert report.items_count == 2
    assert report.candidate_categories == []

    saved = store.load_map(report.map_id)
    assert saved.status == "draft"
    assert saved.group_ref == "2402"
    assert saved.jurisdiction == "UZ"
    assert len(saved.payload) == 2
    assert {item["category_slug"] for item in saved.payload} == {"marking", "fiscal"}


def test_build_map_uses_expensive_tier_model():
    store = InMemoryStore()
    llm = ScriptedLLM([valid_response()])
    Cartographer(store, llm).build_map("2402", "UZ")

    config = load_models_config()
    assert len(llm.calls) == 1
    assert llm.calls[0][1] == config.tiers["expensive"]


def test_build_map_prompt_mentions_group_jurisdiction_and_benchmark_scope():
    store = InMemoryStore()
    llm = ScriptedLLM([valid_response()])
    Cartographer(store, llm).build_map("2402", "UZ")

    prompt = llm.calls[0][0]
    assert "2402" in prompt
    assert "UZ" in prompt
    assert "50" in prompt  # ~50 бенчмарк-стран — из брифа


# ── неизвестный category_slug → кандидат новой категории ─────────────────


def test_build_map_moves_unknown_slug_item_to_candidates_and_excludes_from_map():
    store = InMemoryStore()
    known_item = map_item()
    unknown_item = map_item(
        expected_item="эко-сбор за упаковку", category_slug="environmental",
    )
    llm = ScriptedLLM([valid_response(known_item, unknown_item)])
    report = Cartographer(store, llm).build_map("2402", "UZ")

    assert report.items_count == 1
    assert len(report.candidate_categories) == 1
    assert report.candidate_categories[0]["category_slug"] == "environmental"
    assert report.candidate_categories[0]["expected_item"] == "эко-сбор за упаковку"

    saved = store.load_map(report.map_id)
    assert saved.status == "draft"  # карта всё равно сохраняется, пусть и неполной
    assert len(saved.payload) == 1
    assert saved.payload[0]["category_slug"] == "marking"


def test_build_map_all_items_unknown_slug_saves_empty_draft_with_all_as_candidates():
    store = InMemoryStore()
    llm = ScriptedLLM([valid_response(map_item(category_slug="environmental"))])
    report = Cartographer(store, llm).build_map("2402", "UZ")

    assert report.items_count == 0
    assert len(report.candidate_categories) == 1
    saved = store.load_map(report.map_id)
    assert saved.status == "draft"
    assert saved.payload == []


# ── деградация LLM-ответа ────────────────────────────────────────────────


def test_build_map_garbage_llm_answer_raises():
    store = InMemoryStore()
    llm = ScriptedLLM(["это не JSON"])
    with pytest.raises(AgentLLMError):
        Cartographer(store, llm).build_map("2402", "UZ")


def test_build_map_non_list_json_raises():
    store = InMemoryStore()
    llm = ScriptedLLM([json.dumps({"expected_item": "x", "category_slug": "marking"})])
    with pytest.raises(AgentLLMError):
        Cartographer(store, llm).build_map("2402", "UZ")


def test_build_map_item_missing_required_field_raises():
    store = InMemoryStore()
    llm = ScriptedLLM([json.dumps([{"expected_item": "без категории"}])])
    with pytest.raises(AgentLLMError):
        Cartographer(store, llm).build_map("2402", "UZ")


# ── upsert: повторный build_map на ту же (group, jurisdiction) ──────────


def test_build_map_second_call_overwrites_existing_draft():
    store = InMemoryStore()
    llm = ScriptedLLM([
        valid_response(map_item(expected_item="первая версия")),
        valid_response(map_item(expected_item="вторая версия")),
    ])
    cartographer = Cartographer(store, llm)

    first = cartographer.build_map("2402", "UZ")
    second = cartographer.build_map("2402", "UZ")

    assert second.map_id == first.map_id  # тот же map_id — перезапись, не новая строка
    saved = store.load_map(second.map_id)
    assert saved.payload[0]["expected_item"] == "вторая версия"
    assert len(saved.payload) == 1


def test_build_map_raises_when_existing_map_already_approved():
    store = InMemoryStore()
    # второй ответ скриптован, т.к. build_map зовёт LLM ДО попытки сохранить —
    # узнать, что карта уже approved, можно только на save_map.
    llm = ScriptedLLM([valid_response(), valid_response()])
    cartographer = Cartographer(store, llm)
    first = cartographer.build_map("2402", "UZ")
    store.set_map_status(first.map_id, "approved", approved_by="owner")

    with pytest.raises(MapAlreadyApprovedError):
        cartographer.build_map("2402", "UZ")

    # апрувленная карта не тронута повторным вызовом
    saved = store.load_map(first.map_id)
    assert saved.status == "approved"
    assert len(saved.payload) == 1


# ── set_map_status: апрув/реджект (то, что дёргает CLI) ──────────────────


def test_set_map_status_approve_fills_approved_at_and_by():
    store = InMemoryStore()
    map_id = store.save_map("2402", "UZ", [map_item()])

    record = store.set_map_status(map_id, "approved", approved_by="owner")

    assert record.status == "approved"
    assert record.approved_by == "owner"
    assert record.approved_at is not None


def test_set_map_status_reject_does_not_fill_approved_fields():
    store = InMemoryStore()
    map_id = store.save_map("2402", "UZ", [map_item()])

    record = store.set_map_status(map_id, "rejected")

    assert record.status == "rejected"
    assert record.approved_by is None
    assert record.approved_at is None


# ── интеграция: build_map → approve-map → run_group на ОДНОМ сторе ──────


def test_cartographer_map_can_be_approved_and_run_by_orchestrator():
    """Связка, ради которой существует единый `InMemoryStore` (фикс-раунд
    ревью Задачи 15): Cartographer строит draft-карту → владелец её
    апрувит (`set_map_status`, то же, что дёргает CLI `build approve-map`)
    → `Orchestrator.run_group` реально проходит по её payload и публикует
    айтемы. Шаги конвейера — фейковые callable (без LLM), как и в
    `test_orchestrator.py`; сама Cartographer-часть — на скриптованном LLM."""
    store = InMemoryStore()
    llm = ScriptedLLM([valid_response(
        map_item(expected_item="акцизная марка на пачке сигарет", category_slug="marking"),
        map_item(expected_item="ставка НДС на импорт", category_slug="fiscal"),
    )])

    cart_report = Cartographer(store, llm).build_map("2402", "UZ")
    assert store.load_map(cart_report.map_id).status == "draft"

    # run_group отказывается работать по draft-карте — стоп-точка ①
    # (MapNotApprovedError) уже покрыта test_orchestrator.py; здесь важно
    # само прохождение после апрува.
    approved = store.set_map_status(cart_report.map_id, "approved", approved_by="owner")
    assert approved.status == "approved"
    assert approved.approved_by == "owner"
    assert approved.approved_at is not None

    # заглушка несёт pass-вердикт, как настоящий шаг: publish_ready больше
    # не публикует айтем без единого вердикта (план фотоконтроля §3)
    stub_verdict = Verdict(passed=True, reason="заглушка: подтверждено", model="stub")
    steps = {
        name: (lambda ctx: StepResult(status="ok", verdicts=[stub_verdict]))
        for name in STEP_ORDER
    }
    run_report = Orchestrator(store, steps=steps).run_group(cart_report.map_id)

    assert run_report.total_items == 2
    assert run_report.published == 2
    assert run_report.needs_attention == 0
    published_items = {item.expected_item for item in store.items.values() if item.status == "published"}
    assert published_items == {"акцизная марка на пачке сигарет", "ставка НДС на импорт"}


# ── режим `--research` (Задача 4): план запросов + реальные источники ────


class _Searcher:
    """Фейковый `WebSearcher` — таблица query -> список находок/исключение
    (тот же паттерн, что и `importer/tests/build/test_research.py`)."""

    def __init__(self, table):
        self.table = table
        self.queries = []

    def search(self, q):
        self.queries.append(q)
        if isinstance(self.table.get(q), Exception):
            raise self.table[q]
        return self.table.get(q, [])


class _Fetcher:
    """Фейковый `DocumentFetcher` — таблица url -> FetchedDoc/исключение."""

    def __init__(self, docs):
        self.docs = docs
        self.urls = []

    def fetch(self, url):
        self.urls.append(url)
        if isinstance(self.docs.get(url), Exception):
            raise self.docs[url]
        return self.docs[url]


def _doc(url, text):
    return FetchedDoc(url=url, final_url=url, content_type="text/html", sha256="0" * 64,
                       text=text, fetched_at=datetime(2026, 9, 11, tzinfo=timezone.utc))


def test_research_mode_plans_queries_and_cites_sources():
    # первый ответ LLM — план запросов, второй — карта с sources
    llm = ScriptedLLM([
        json.dumps(["маркировка молока Узбекистан", "sut mahsulotlari markirovka"], ensure_ascii=False),
        valid_response(map_item(
            sources=["https://lex.uz/1", "https://fake.example/999"],
        )),
    ])
    kit = ResearchToolkit(
        _Searcher({
            "маркировка молока Узбекистан": [
                {"title": "Постановление о маркировке", "url": "https://lex.uz/1", "snippet": ""},
            ],
            "sut mahsulotlari markirovka": [],
        }),
        _Fetcher({"https://lex.uz/1": _doc("https://lex.uz/1", "текст постановления" * 50)}),
    )
    store = InMemoryStore()

    report = Cartographer(store, llm, toolkit=kit).build_map("0401", "UZ")

    assert report.items_count == 1
    assert report.sources_used == 1

    saved = store.load_map(report.map_id)
    # выдуманный LLM url отброшен молча — sources только из реально
    # собранных источников
    assert saved.payload[0]["sources"] == ["https://lex.uz/1"]

    assert len(llm.calls) == 2
    map_prompt = llm.calls[1][0]
    assert "Источники" in map_prompt
    assert "https://lex.uz/1" in map_prompt


def test_without_toolkit_behavior_unchanged():
    # один LLM-вызов, никакого блока «Источники» — как в Волне 2
    store = InMemoryStore()
    llm = ScriptedLLM([valid_response(map_item())])

    report = Cartographer(store, llm).build_map("2402", "UZ")

    assert report.items_count == 1
    assert report.sources_used == 0
    assert len(llm.calls) == 1
    assert "Источники" not in llm.calls[0][0]

    saved = store.load_map(report.map_id)
    assert "sources" not in saved.payload[0]


def test_plan_queries_garbage_falls_back_to_group_ref():
    # план не JSON -> один запрос f"{group_ref} требования {jurisdiction}",
    # карта всё равно строится
    store = InMemoryStore()
    llm = ScriptedLLM(["это не план, а болтовня", valid_response(map_item())])
    searcher = _Searcher({"0401 требования UZ": [{"title": "T", "url": "https://lex.uz/9", "snippet": ""}]})
    kit = ResearchToolkit(searcher, _Fetcher({"https://lex.uz/9": _doc("https://lex.uz/9", "текст")}))

    report = Cartographer(store, llm, toolkit=kit).build_map("0401", "UZ")

    assert searcher.queries == ["0401 требования UZ"]
    assert report.items_count == 1
    assert report.sources_used == 1
