"""Тесты discovery-джоба (Задача 41) — `discovery.py`.

Сценарии из уточнений контроллера + фикс-раунда ревью (2 Important):
- новое ('new') событие БЕЗ impacts + approved-карта, чей вопрос даёт хит
  (найденный `NormFragment.act_id` совпадает с `act_id` события) -> кандидат
  `pipeline.items(status='pending')` создан;
- событие, у которого УЖЕ есть impacts (Impact-маппер его сопоставил) ->
  discovery его вообще не видит (скип);
- нет хита (найденные фрагменты — из другого акта либо пусто) -> 0 items;
- идемпотентность СО СТАТУС-ФИЛЬТРОМ (фикс Important №1): `no_norm`/
  `needs_attention` НЕ блокируют новый кандидат (главный сценарий брифа —
  новый акт закрывает пробел прежнего прогона), блокируют только
  `pending`/`in_progress`/`draft_loaded`/`published`;
- ошибка `search_norms` на одном айтеме не роняет весь прогон (фикс
  Important №2) — айтем считается no-hit, остальные айтемы/карты/события
  обрабатываются как обычно.

Стор — `InMemoryMonitoringStore`; LLM/LegalX — скриптованные фейки без сети,
тот же паттерн, что и `test_impact_mapper.py`.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field

from importer.build.legalx import NormFragment
from importer.monitoring.discovery import run_discovery
from importer.tests.monitoring.stores import InMemoryMonitoringStore

ACT_ID = "11111111-1111-1111-1111-111111111111"
OTHER_ACT_ID = "22222222-2222-2222-2222-222222222222"


@dataclass
class ScriptedLLM:
    """Тот же дублёр `AgentLLMClient`, что и `test_impact_mapper.py`."""

    responses: list[str]
    calls: list[tuple[str, str]] = field(default_factory=list)

    def complete(self, prompt: str, model: str) -> str:
        self.calls.append((prompt, model))
        if not self.responses:
            raise AssertionError("ScriptedLLM: запросили ответ сверх скрипта — лишний вызов LLM")
        return self.responses.pop(0)


@dataclass
class FakeLegalXClient:
    """Скриптованный `LegalXClient` — фикс-набор `NormFragment` на каждый
    вызов `search_norms`, независимо от текста вопроса (тексты вопросов
    генерирует LLM, тест их не контролирует). `calls` — для проверки
    идемпотентности (повторный прогон не должен искать снова).

    `fail_first_n_calls` (фикс-раунд ревью, Important №2) — первые N
    ВЫЗОВОВ (по порядку, сквозная нумерация по всему тесту, не по айтему)
    бросают исключение вместо возврата фрагментов — симулирует временную
    недоступность LegalX ровно на первом попавшемся поиске."""

    fragments: list[NormFragment] = field(default_factory=list)
    calls: list[tuple[str, str]] = field(default_factory=list)
    fail_first_n_calls: int = 0

    def search_norms(
        self, query: str, jurisdiction: str, domains: list[str] | None = None, limit: int = 10
    ) -> list[NormFragment]:
        self.calls.append((query, jurisdiction))
        if len(self.calls) <= self.fail_first_n_calls:
            raise ConnectionError(f"LegalX недоступен (вызов #{len(self.calls)})")
        return list(self.fragments)

    def search_cases(self, article: str, topic: str | None = None, limit: int = 5):
        raise NotImplementedError("discovery не использует search_cases")


def questions_response(count: int = 2) -> str:
    return json.dumps(
        [
            {"text": f"вопрос {i}", "expected_schema": {"type": "object"}}
            for i in range(count)
        ],
        ensure_ascii=False,
    )


def fragment(act_id: str = ACT_ID) -> NormFragment:
    return NormFragment(
        fragment_id="f1",
        act_id=act_id,
        act_title="Акт",
        article_ref="ст. 1",
        anchor="a1",
        content="текст фрагмента",
        act_status="active",
        valid_from=None,
        valid_to=None,
        score=1.0,
    )


MAP_ITEM_ENERGY_LABELING = {
    "expected_item": "маркировка энергетических напитков возрастным ограничением",
    "category_slug": "labeling",
    "rationale": "мировая практика ЕС/США",
    "benchmark_countries": ["DE", "US"],
}


# ── хит: кандидат создан ─────────────────────────────────────────────────


def test_new_event_without_impacts_and_map_with_hit_creates_pending_item():
    store = InMemoryMonitoringStore()
    store.add_event(
        event_type="new", jurisdiction="UZ", processed=True,
        payload={"act_id": ACT_ID},
    )
    map_id = store.add_approved_map(jurisdiction="UZ", payload=[MAP_ITEM_ENERGY_LABELING])
    llm = ScriptedLLM(responses=[questions_response(2)])
    legalx = FakeLegalXClient(fragments=[fragment(ACT_ID)])

    report = run_discovery(store, llm=llm, legalx=legalx)

    assert report.events_seen == 1
    assert report.candidates_created == 1
    assert len(store.pipeline_items) == 1
    item = store.pipeline_items[0]
    assert item["status"] == "pending"
    assert item["expected_item"] == MAP_ITEM_ENERGY_LABELING["expected_item"]
    assert item["category_slug"] == "labeling"
    # discovery-run отдельный, привязан к карте, чьи вопросы дали хит
    assert len(store.pipeline_runs) == 1
    run = store.pipeline_runs[0]
    assert run["map_id"] == map_id
    assert item["run_id"] == run["id"]


# ── событие с impacts — discovery его не видит ───────────────────────────


def test_event_with_impacts_is_never_seen_by_discovery():
    store = InMemoryMonitoringStore()
    event_id = store.add_event(
        event_type="new", jurisdiction="UZ", processed=True,
        payload={"act_id": ACT_ID},
    )
    store.impacts.append(
        {"id": "impact-1", "change_event_id": event_id, "requirement_id": "req-1", "status": "pending_review"}
    )
    store.add_approved_map(jurisdiction="UZ", payload=[MAP_ITEM_ENERGY_LABELING])
    llm = ScriptedLLM(responses=[])  # любой вызов -> AssertionError
    legalx = FakeLegalXClient(fragments=[fragment(ACT_ID)])

    report = run_discovery(store, llm=llm, legalx=legalx)

    assert report.events_seen == 0
    assert report.candidates_created == 0
    assert store.pipeline_items == []
    assert legalx.calls == []


# ── нет хита ──────────────────────────────────────────────────────────────


def test_no_hit_creates_zero_items():
    store = InMemoryMonitoringStore()
    store.add_event(
        event_type="new", jurisdiction="UZ", processed=True,
        payload={"act_id": ACT_ID},
    )
    store.add_approved_map(jurisdiction="UZ", payload=[MAP_ITEM_ENERGY_LABELING])
    llm = ScriptedLLM(responses=[questions_response(2)])
    # фрагмент найден, но из ДРУГОГО акта — не хит по act_id события
    legalx = FakeLegalXClient(fragments=[fragment(OTHER_ACT_ID)])

    report = run_discovery(store, llm=llm, legalx=legalx)

    assert report.candidates_created == 0
    assert store.pipeline_items == []
    assert report.items_checked == 1


def test_no_hit_when_search_returns_nothing():
    store = InMemoryMonitoringStore()
    store.add_event(
        event_type="new", jurisdiction="UZ", processed=True,
        payload={"act_id": ACT_ID},
    )
    store.add_approved_map(jurisdiction="UZ", payload=[MAP_ITEM_ENERGY_LABELING])
    llm = ScriptedLLM(responses=[questions_response(2)])
    legalx = FakeLegalXClient(fragments=[])

    report = run_discovery(store, llm=llm, legalx=legalx)

    assert report.candidates_created == 0
    assert store.pipeline_items == []


# ── идемпотентность СО СТАТУС-ФИЛЬТРОМ (фикс-раунд ревью, Important №1) ──


def test_repeated_run_does_not_duplicate_item_or_call_llm_again():
    """Повторный прогон, когда кандидат уже `pending` (из первого прогона),
    — блокирующий статус, скип ДО вызова LLM/поиска."""
    store = InMemoryMonitoringStore()
    store.add_event(
        event_type="new", jurisdiction="UZ", processed=True,
        payload={"act_id": ACT_ID},
    )
    store.add_approved_map(jurisdiction="UZ", payload=[MAP_ITEM_ENERGY_LABELING])
    # ОДИН ответ в скрипте: второй прогон не должен запросить ещё один
    llm = ScriptedLLM(responses=[questions_response(2)])
    legalx = FakeLegalXClient(fragments=[fragment(ACT_ID)])

    first = run_discovery(store, llm=llm, legalx=legalx)
    second = run_discovery(store, llm=llm, legalx=legalx)

    assert first.candidates_created == 1
    assert second.candidates_created == 0
    assert second.items_already_covered == 1
    assert len(store.pipeline_items) == 1
    # второй прогон не искал в LegalX повторно (нашёл покрытие раньше)
    assert len(legalx.calls) == 1


def test_map_with_no_norm_item_still_gets_a_new_candidate_on_hit():
    """ГЛАВНЫЙ сценарий брифа (фикс Important №1): карта уже прогонялась
    обычным Build (айтем застрял на `no_norm` — норма не нашлась ТОГДА),
    новый акт (webhook 'new') даёт хит по тому же `expected_item` -> старая
    версия (`find_existing_discovery_item`, блокировала ЛЮБОЙ статус) молча
    убивала бы этот сценарий навсегда; исправленная — заводит кандидата."""
    store = InMemoryMonitoringStore()
    store.add_event(
        event_type="new", jurisdiction="UZ", processed=True,
        payload={"act_id": ACT_ID},
    )
    map_id = store.add_approved_map(jurisdiction="UZ", payload=[MAP_ITEM_ENERGY_LABELING])
    store.add_pipeline_item_for_map(
        map_id, MAP_ITEM_ENERGY_LABELING["expected_item"], status="no_norm",
    )
    llm = ScriptedLLM(responses=[questions_response(2)])
    legalx = FakeLegalXClient(fragments=[fragment(ACT_ID)])

    report = run_discovery(store, llm=llm, legalx=legalx)

    assert report.candidates_created == 1
    assert report.items_already_covered == 0
    # старый no_norm-айтем остался, новый pending-кандидат добавился рядом
    statuses = sorted(item["status"] for item in store.pipeline_items)
    assert statuses == ["no_norm", "pending"]


def test_map_with_needs_attention_item_still_gets_a_new_candidate_on_hit():
    """Тот же сценарий, что и no_norm выше, но для `needs_attention` —
    оба статуса из брифового «прежний прогон не смог закрыть» НЕ блокируют."""
    store = InMemoryMonitoringStore()
    store.add_event(
        event_type="new", jurisdiction="UZ", processed=True,
        payload={"act_id": ACT_ID},
    )
    map_id = store.add_approved_map(jurisdiction="UZ", payload=[MAP_ITEM_ENERGY_LABELING])
    store.add_pipeline_item_for_map(
        map_id, MAP_ITEM_ENERGY_LABELING["expected_item"], status="needs_attention",
    )
    llm = ScriptedLLM(responses=[questions_response(2)])
    legalx = FakeLegalXClient(fragments=[fragment(ACT_ID)])

    report = run_discovery(store, llm=llm, legalx=legalx)

    assert report.candidates_created == 1
    assert report.items_already_covered == 0


def test_map_with_published_item_is_skipped_even_with_a_hit():
    """`published` — уже закрыт, discovery не должен заводить дубль-item
    даже если новый акт дал бы хит по тому же тексту айтема."""
    store = InMemoryMonitoringStore()
    store.add_event(
        event_type="new", jurisdiction="UZ", processed=True,
        payload={"act_id": ACT_ID},
    )
    map_id = store.add_approved_map(jurisdiction="UZ", payload=[MAP_ITEM_ENERGY_LABELING])
    store.add_pipeline_item_for_map(
        map_id, MAP_ITEM_ENERGY_LABELING["expected_item"], status="published",
    )
    llm = ScriptedLLM(responses=[])  # покрытие найдено ДО вызова LLM
    legalx = FakeLegalXClient(fragments=[fragment(ACT_ID)])

    report = run_discovery(store, llm=llm, legalx=legalx)

    assert report.candidates_created == 0
    assert report.items_already_covered == 1
    assert legalx.calls == []
    assert len(store.pipeline_items) == 1  # только исходный published, без дубля


# ── событие без act_id (ручное 'new'-событие) ────────────────────────────


def test_manual_new_event_without_act_id_is_skipped():
    store = InMemoryMonitoringStore()
    store.add_event(event_type="new", jurisdiction="UZ", processed=True, payload={})
    store.add_approved_map(jurisdiction="UZ", payload=[MAP_ITEM_ENERGY_LABELING])
    llm = ScriptedLLM(responses=[])
    legalx = FakeLegalXClient(fragments=[fragment(ACT_ID)])

    report = run_discovery(store, llm=llm, legalx=legalx)

    assert report.events_seen == 1
    assert report.events_skipped_no_act_id == 1
    assert report.candidates_created == 0
    assert legalx.calls == []


# ── несколько айтемов карты: хит только по одному ────────────────────────


def test_only_hitting_item_becomes_a_candidate_among_several():
    store = InMemoryMonitoringStore()
    store.add_event(
        event_type="new", jurisdiction="UZ", processed=True,
        payload={"act_id": ACT_ID},
    )
    other_item = {
        "expected_item": "лицензия на молочную продукцию",
        "category_slug": "licensing",
        "rationale": "...",
        "benchmark_countries": ["FR"],
    }
    store.add_approved_map(
        jurisdiction="UZ", payload=[MAP_ITEM_ENERGY_LABELING, other_item],
    )
    llm = ScriptedLLM(
        responses=[questions_response(2), questions_response(2)],
    )
    legalx = FakeLegalXClient(fragments=[fragment(ACT_ID)])

    report = run_discovery(store, llm=llm, legalx=legalx)

    assert report.items_checked == 2
    assert report.candidates_created == 2  # оба айтема "хитуют" (fragments общий на все вопросы)
    expected_items = {item["expected_item"] for item in store.pipeline_items}
    assert expected_items == {
        MAP_ITEM_ENERGY_LABELING["expected_item"], other_item["expected_item"],
    }


# ── question_writer падает — не роняет весь прогон ───────────────────────


def test_question_writer_failure_on_one_item_does_not_crash_discovery():
    store = InMemoryMonitoringStore()
    store.add_event(
        event_type="new", jurisdiction="UZ", processed=True,
        payload={"act_id": ACT_ID},
    )
    store.add_approved_map(jurisdiction="UZ", payload=[MAP_ITEM_ENERGY_LABELING])
    # дважды мусорный ответ -> write_questions поднимет ValueError (ретраи исчерпаны)
    llm = ScriptedLLM(responses=["не json вообще", "снова не json"])
    legalx = FakeLegalXClient(fragments=[fragment(ACT_ID)])

    report = run_discovery(store, llm=llm, legalx=legalx)

    assert report.candidates_created == 0
    assert store.pipeline_items == []
    assert legalx.calls == []


# ── search_norms падает — не роняет весь прогон (фикс Important №2) ──────


def test_search_norms_error_on_one_item_does_not_crash_discovery():
    """Первый вызов `search_norms` (первый вопрос первого айтема карты)
    бросает исключение — этот айтем считается no-hit, но ВТОРОЙ айтем той
    же карты (следующий по циклу) обрабатывается штатно, прогон не падает."""
    store = InMemoryMonitoringStore()
    store.add_event(
        event_type="new", jurisdiction="UZ", processed=True,
        payload={"act_id": ACT_ID},
    )
    other_item = {
        "expected_item": "лицензия на молочную продукцию",
        "category_slug": "licensing",
        "rationale": "...",
        "benchmark_countries": ["FR"],
    }
    store.add_approved_map(
        jurisdiction="UZ", payload=[MAP_ITEM_ENERGY_LABELING, other_item],
    )
    llm = ScriptedLLM(
        responses=[questions_response(2), questions_response(2)],
    )
    # только ПЕРВЫЙ вызов search_norms (первый вопрос первого айтема) падает
    legalx = FakeLegalXClient(fragments=[fragment(ACT_ID)], fail_first_n_calls=1)

    report = run_discovery(store, llm=llm, legalx=legalx)

    assert report.items_checked == 2
    assert report.search_errors == 1
    # первый айтем — no-hit (упал), второй — хит (нашёлся кандидат)
    assert report.candidates_created == 1
    assert len(store.pipeline_items) == 1
    assert store.pipeline_items[0]["expected_item"] == other_item["expected_item"]
