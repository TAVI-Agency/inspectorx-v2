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
  перезаписывает draft; поверх уже `approved` карты — `MapAlreadyApprovedError`.

LLM — только инжектируемый скрипт ответов (тот же паттерн, что и
`test_agents.py:ScriptedLLM`), никакого сетевого мокинга.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field, replace

import pytest

from importer.build.agents import load_models_config
from importer.build.cartographer import Cartographer, CartographerReport
from importer.build.llm_client import AgentLLMError
from importer.build.orchestrator import MapAlreadyApprovedError, MapRecord


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


CATEGORY_SLUGS = [
    "sps", "tbt", "marking", "licensing", "fiscal", "currency", "customs", "origin",
]


@dataclass
class FakeStore:
    """Фейковый BuildStore: только методы, которые реально использует
    Cartographer (`save_map`, `list_category_slugs`) и CLI approve/reject
    (`set_map_status`, `load_map`) — без сети и без БД."""

    category_slugs: list[str] = field(default_factory=lambda: list(CATEGORY_SLUGS))
    maps: dict[str, MapRecord] = field(default_factory=dict)
    _by_key: dict[tuple[str, str], str] = field(default_factory=dict)
    _next_id: int = 0

    def _gen_id(self) -> str:
        self._next_id += 1
        return f"map-{self._next_id}"

    def list_category_slugs(self) -> list[str]:
        return list(self.category_slugs)

    def load_map(self, map_id: str) -> MapRecord:
        return self.maps[map_id]

    def save_map(self, group_ref: str, jurisdiction: str, payload: list[dict]) -> str:
        key = (group_ref, jurisdiction)
        existing_id = self._by_key.get(key)
        if existing_id is not None:
            existing = self.maps[existing_id]
            if existing.status == "approved":
                raise MapAlreadyApprovedError(
                    f"карта {group_ref}/{jurisdiction} (id={existing_id}) уже approved — "
                    "повторный build_map запрещён"
                )
            self.maps[existing_id] = replace(existing, payload=payload, status="draft")
            return existing_id
        map_id = self._gen_id()
        self._by_key[key] = map_id
        self.maps[map_id] = MapRecord(
            id=map_id, group_ref=group_ref, jurisdiction=jurisdiction,
            status="draft", payload=payload,
        )
        return map_id

    def set_map_status(self, map_id: str, status: str, *, approved_by: str | None = None) -> MapRecord:
        record = self.maps[map_id]
        updated = replace(
            record,
            status=status,
            approved_by=approved_by if status == "approved" else record.approved_by,
            approved_at="2026-08-02T00:00:00+00:00" if status == "approved" else record.approved_at,
        )
        self.maps[map_id] = updated
        return updated


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
    store = FakeStore()
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
    store = FakeStore()
    llm = ScriptedLLM([valid_response()])
    Cartographer(store, llm).build_map("2402", "UZ")

    config = load_models_config()
    assert len(llm.calls) == 1
    assert llm.calls[0][1] == config.tiers["expensive"]


def test_build_map_prompt_mentions_group_jurisdiction_and_benchmark_scope():
    store = FakeStore()
    llm = ScriptedLLM([valid_response()])
    Cartographer(store, llm).build_map("2402", "UZ")

    prompt = llm.calls[0][0]
    assert "2402" in prompt
    assert "UZ" in prompt
    assert "50" in prompt  # ~50 бенчмарк-стран — из брифа


# ── неизвестный category_slug → кандидат новой категории ─────────────────


def test_build_map_moves_unknown_slug_item_to_candidates_and_excludes_from_map():
    store = FakeStore()
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
    store = FakeStore()
    llm = ScriptedLLM([valid_response(map_item(category_slug="environmental"))])
    report = Cartographer(store, llm).build_map("2402", "UZ")

    assert report.items_count == 0
    assert len(report.candidate_categories) == 1
    saved = store.load_map(report.map_id)
    assert saved.status == "draft"
    assert saved.payload == []


# ── деградация LLM-ответа ────────────────────────────────────────────────


def test_build_map_garbage_llm_answer_raises():
    store = FakeStore()
    llm = ScriptedLLM(["это не JSON"])
    with pytest.raises(AgentLLMError):
        Cartographer(store, llm).build_map("2402", "UZ")


def test_build_map_non_list_json_raises():
    store = FakeStore()
    llm = ScriptedLLM([json.dumps({"expected_item": "x", "category_slug": "marking"})])
    with pytest.raises(AgentLLMError):
        Cartographer(store, llm).build_map("2402", "UZ")


def test_build_map_item_missing_required_field_raises():
    store = FakeStore()
    llm = ScriptedLLM([json.dumps([{"expected_item": "без категории"}])])
    with pytest.raises(AgentLLMError):
        Cartographer(store, llm).build_map("2402", "UZ")


# ── upsert: повторный build_map на ту же (group, jurisdiction) ──────────


def test_build_map_second_call_overwrites_existing_draft():
    store = FakeStore()
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
    store = FakeStore()
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
    store = FakeStore()
    map_id = store.save_map("2402", "UZ", [map_item()])

    record = store.set_map_status(map_id, "approved", approved_by="owner")

    assert record.status == "approved"
    assert record.approved_by == "owner"
    assert record.approved_at is not None


def test_set_map_status_reject_does_not_fill_approved_fields():
    store = FakeStore()
    map_id = store.save_map("2402", "UZ", [map_item()])

    record = store.set_map_status(map_id, "rejected")

    assert record.status == "rejected"
    assert record.approved_by is None
    assert record.approved_at is None
