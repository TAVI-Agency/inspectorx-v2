"""Impact-маппер + In-house lawyer (мониторинг) + ре-ревью (Задача 40).

Сценарии из брифа/уточнений контроллера:

- событие с точным цитатным совпадением (путь а) → `requirement_change_
  impacts(status='pending_review')` + `review_flag='flagged_by_change'` +
  фан-аут `user_notifications(kind='change')` подписанным пользователям;
- дубль события (тот же `payload->>'act_id'`/`event_type`/`effective_date`,
  уже обработанный) → скип, `processed_at` проставлен, impacts не создаются;
- событие без кандидатов (ни цитат, ни опубликованных требований юрисдикции)
  → помечено обработанным, 0 impacts;
- нет точного совпадения → Classifier-кандидаты (путь б), ниже порога скора
  отфильтровываются;
- цитатное совпадение есть → Classifier вообще не вызывается (путь а
  приоритетнее, экономия LLM);
- In-house lawyer `needs_reimplementation=true` → `orchestrator.rerun_item`
  вызван с `item_id`/`from_step`; `needs=false` → rerun не вызывается;
- нет `pipeline.items` под требование → rerun не вызывается, даже если
  юрист сказал `needs=true`;
- идемпотентность фан-аута: повторный вызов на те же `impact_ids` не плодит
  вторую строку уведомления.

LLM — только инжектируемый скрипт ответов (тот же паттерн, что и
`test_steps_samples_lawyer.py`/`test_manager.py`: `ScriptedLLM`, сети нет).
Стор — `InMemoryMonitoringStore` (`importer/tests/monitoring/stores.py`),
БД не трогаем.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field

import pytest

from importer.build.agents import load_models_config
from importer.build.llm_client import AgentLLMError
from importer.build.steps import STEP_ORDER, ItemRecord, StepResult
from importer.monitoring.impact_mapper import (
    CANDIDATE_SCORE_THRESHOLD,
    InHouseLawyer,
    MapAwareRerunOrchestrator,
    process_changes,
)
from importer.tests.build.stores import InMemoryStore
from importer.tests.monitoring.stores import InMemoryMonitoringStore

# ── тестовые дублёры (тот же паттерн, что test_steps_samples_lawyer.py) ────


@dataclass
class ScriptedLLM:
    """Мок `AgentLLMClient`: отдаёт ответы по очереди, фиксирует все `(prompt, model)`."""

    responses: list[str]
    calls: list[tuple[str, str]] = field(default_factory=list)

    def complete(self, prompt: str, model: str) -> str:
        self.calls.append((prompt, model))
        if not self.responses:
            raise AssertionError("ScriptedLLM: запросили ответ сверх скрипта — лишний вызов LLM")
        return self.responses.pop(0)


@dataclass
class RecordingOrchestrator:
    """Фейковый `RerunOrchestratorLike`: фиксирует все вызовы `rerun_item`."""

    calls: list[tuple[str, str]] = field(default_factory=list)

    def rerun_item(self, item_id: str, from_step: str) -> None:
        self.calls.append((item_id, from_step))


def matches_response(matches: list[dict]) -> str:
    return json.dumps({"matches": matches}, ensure_ascii=False)


def lawyer_response(needs: bool, from_step: str | None = None, note: str = "обоснование") -> str:
    return json.dumps(
        {"needs_reimplementation": needs, "from_step": from_step, "note": note},
        ensure_ascii=False,
    )


LEGALX_ACT_ID = "11111111-1111-1111-1111-111111111111"


# ── путь (а): точное цитатное совпадение ────────────────────────────────


def test_exact_citation_match_creates_impact_flags_and_notifies():
    store = InMemoryMonitoringStore()
    store.add_citation(LEGALX_ACT_ID, "req-1")
    store.add_applicable_user("req-1", "user-1", product_id="prod-1")
    event_id = store.add_event(
        event_type="amended",
        jurisdiction="UZ",
        effective_date="2027-01-01",
        summary="изменена ставка акциза",
        payload={"act_id": LEGALX_ACT_ID, "jurisdiction": "UZ", "change_type": "amended",
                 "effective_date": "2027-01-01", "fragment_ids": ["f1"]},
    )

    report = process_changes(store)

    assert report.events_processed == 1
    assert report.impacts_created == 1
    assert len(store.impacts) == 1
    impact = store.impacts[0]
    assert impact["requirement_id"] == "req-1"
    assert impact["status"] == "pending_review"

    assert store.requirements["req-1"]["review_flag"] == "flagged_by_change"
    assert store.requirements["req-1"]["flagged_by_event_id"] == event_id
    assert store.requirements["req-1"]["flagged_at"] is not None

    assert len(store.notifications) == 1
    notification = store.notifications[0]
    assert notification["user_id"] == "user-1"
    assert notification["impact_id"] == impact["id"]
    assert notification["kind"] == "change"

    assert store.events[event_id]["processed_at"] is not None


def test_citation_match_skips_classifier_entirely():
    """Путь (а) приоритетнее — Classifier не вызывается, если цитаты уже
    нашли требование (экономия cheap-вызова LLM)."""
    store = InMemoryMonitoringStore()
    store.add_citation(LEGALX_ACT_ID, "req-1")
    store.add_published_requirement("UZ", "req-1", "Акцизная марка на сигареты")
    store.add_event(
        event_type="amended", jurisdiction="UZ",
        payload={"act_id": LEGALX_ACT_ID}, effective_date=None,
    )
    llm = ScriptedLLM(responses=[])  # пустой скрипт — любой вызов роняет AssertionError

    report = process_changes(store, classifier_llm=llm)

    assert report.impacts_created == 1
    assert llm.calls == []


# ── дедуп повторной доставки webhook'а ──────────────────────────────────


def test_duplicate_event_is_skipped_and_marked_processed():
    store = InMemoryMonitoringStore()
    store.add_citation(LEGALX_ACT_ID, "req-1")
    store.add_event(
        event_type="amended", effective_date="2027-01-01",
        payload={"act_id": LEGALX_ACT_ID}, processed=True,
    )
    dup_id = store.add_event(
        event_type="amended", effective_date="2027-01-01",
        payload={"act_id": LEGALX_ACT_ID},
    )

    report = process_changes(store)

    assert report.duplicates_skipped == 1
    assert report.events_processed == 0
    assert store.impacts == []
    assert store.events[dup_id]["processed_at"] is not None


def test_manual_events_without_act_id_are_never_deduped_against_each_other():
    """Событие без `act_id` (ручное, не из LegalX) не подлежит дедупу — два
    независимых ручных события в одну дату не должны схлопываться."""
    store = InMemoryMonitoringStore()
    store.add_event(
        event_type="amended", effective_date="2027-01-01", payload={}, processed=True,
    )
    second_id = store.add_event(
        event_type="amended", effective_date="2027-01-01", payload={},
    )

    report = process_changes(store)

    assert report.duplicates_skipped == 0
    assert store.events[second_id]["processed_at"] is not None
    assert report.events_no_candidates == 1  # обработано, кандидатов нет


# ── событие без кандидатов ──────────────────────────────────────────────


def test_event_without_candidates_is_processed_with_zero_impacts():
    store = InMemoryMonitoringStore()
    event_id = store.add_event(
        event_type="new", jurisdiction="UZ", payload={"act_id": "unknown-act"},
    )

    report = process_changes(store)

    assert report.events_processed == 0
    assert report.events_no_candidates == 1
    assert store.impacts == []
    assert store.events[event_id]["processed_at"] is not None


# ── путь (б): Classifier-кандидаты ──────────────────────────────────────


def test_classifier_candidates_used_when_no_citation_match():
    store = InMemoryMonitoringStore()
    store.add_published_requirement("UZ", "req-1", "Маркировка сигарет")
    store.add_published_requirement("UZ", "req-2", "Молоко пастеризованное")
    store.add_event(
        event_type="amended", jurisdiction="UZ",
        summary="изменены правила маркировки табачных изделий",
        payload={"act_id": "act-without-local-mapping"},
    )
    llm = ScriptedLLM(responses=[matches_response([{"requirement_id": "req-1", "score": 0.9}])])

    report = process_changes(store, classifier_llm=llm)

    assert report.impacts_created == 1
    assert store.impacts[0]["requirement_id"] == "req-1"
    assert len(llm.calls) == 1
    config = load_models_config()
    assert llm.calls[0][1] == config.tiers["cheap"]


def test_classifier_candidates_below_threshold_are_filtered():
    store = InMemoryMonitoringStore()
    store.add_published_requirement("UZ", "req-1", "Маркировка сигарет")
    store.add_published_requirement("UZ", "req-2", "Молоко пастеризованное")
    store.add_event(event_type="amended", jurisdiction="UZ", payload={})
    below = CANDIDATE_SCORE_THRESHOLD - 0.1
    llm = ScriptedLLM(responses=[matches_response([
        {"requirement_id": "req-1", "score": 0.9},
        {"requirement_id": "req-2", "score": below},
    ])])

    report = process_changes(store, classifier_llm=llm)

    assert report.impacts_created == 1
    assert store.impacts[0]["requirement_id"] == "req-1"


def test_no_published_requirements_in_jurisdiction_skips_classifier_call():
    store = InMemoryMonitoringStore()
    store.add_event(event_type="amended", jurisdiction="UZ", payload={})
    llm = ScriptedLLM(responses=[])

    report = process_changes(store, classifier_llm=llm)

    assert report.events_no_candidates == 1
    assert llm.calls == []


def test_classifier_garbage_response_yields_zero_candidates_not_a_crash():
    store = InMemoryMonitoringStore()
    store.add_published_requirement("UZ", "req-1", "Маркировка сигарет")
    store.add_event(event_type="amended", jurisdiction="UZ", payload={})
    llm = ScriptedLLM(responses=["не json вообще"])

    report = process_changes(store, classifier_llm=llm)

    assert report.events_no_candidates == 1
    assert store.impacts == []


# ── In-house lawyer + ре-ревью ───────────────────────────────────────────


def test_lawyer_needs_reimplementation_triggers_rerun_item():
    store = InMemoryMonitoringStore()
    store.add_citation(LEGALX_ACT_ID, "req-1")
    store.add_published_requirement("UZ", "req-1", "Акцизная марка на сигареты")
    store.add_pipeline_item("req-1", "item-1")
    store.add_event(event_type="amended", jurisdiction="UZ", payload={"act_id": LEGALX_ACT_ID})
    lawyer = InHouseLawyer(ScriptedLLM(responses=[lawyer_response(True, "norm")]))
    orchestrator = RecordingOrchestrator()

    report = process_changes(store, lawyer=lawyer, orchestrator=orchestrator)

    assert orchestrator.calls == [("item-1", "norm")]
    assert report.rereviews_enqueued == 1
    # флаг всё равно стоит независимо от решения юриста
    assert store.requirements["req-1"]["review_flag"] == "flagged_by_change"


def test_lawyer_no_reimplementation_does_not_call_rerun_item():
    store = InMemoryMonitoringStore()
    store.add_citation(LEGALX_ACT_ID, "req-1")
    store.add_published_requirement("UZ", "req-1", "Акцизная марка на сигареты")
    store.add_pipeline_item("req-1", "item-1")
    store.add_event(event_type="amended", jurisdiction="UZ", payload={"act_id": LEGALX_ACT_ID})
    lawyer = InHouseLawyer(ScriptedLLM(responses=[lawyer_response(False, None)]))
    orchestrator = RecordingOrchestrator()

    report = process_changes(store, lawyer=lawyer, orchestrator=orchestrator)

    assert orchestrator.calls == []
    assert report.rereviews_enqueued == 0
    assert store.requirements["req-1"]["review_flag"] == "flagged_by_change"


def test_rerun_skipped_when_no_pipeline_item_for_requirement():
    store = InMemoryMonitoringStore()
    store.add_citation(LEGALX_ACT_ID, "req-1")
    store.add_published_requirement("UZ", "req-1", "Акцизная марка на сигареты")
    # НЕ добавляем pipeline item — требование пришло из легаси import-report
    store.add_event(event_type="amended", jurisdiction="UZ", payload={"act_id": LEGALX_ACT_ID})
    lawyer = InHouseLawyer(ScriptedLLM(responses=[lawyer_response(True, "norm")]))
    orchestrator = RecordingOrchestrator()

    report = process_changes(store, lawyer=lawyer, orchestrator=orchestrator)

    assert orchestrator.calls == []
    assert report.rereviews_enqueued == 0


def test_rerun_skipped_without_orchestrator_even_if_lawyer_says_needs_true():
    store = InMemoryMonitoringStore()
    store.add_citation(LEGALX_ACT_ID, "req-1")
    store.add_published_requirement("UZ", "req-1", "Акцизная марка на сигареты")
    store.add_pipeline_item("req-1", "item-1")
    store.add_event(event_type="amended", jurisdiction="UZ", payload={"act_id": LEGALX_ACT_ID})
    lawyer = InHouseLawyer(ScriptedLLM(responses=[lawyer_response(True, "norm")]))

    report = process_changes(store, lawyer=lawyer, orchestrator=None)

    assert report.rereviews_enqueued == 0


# ── ревью Задачи 40 (Important): изоляция ошибок юриста в очереди ───────


def test_lawyer_error_on_one_requirement_does_not_lose_its_already_saved_impact_and_flag():
    """(б) исключение НЕ теряет уже сохранённые impacts/flag: `flag_requirement`
    и `save_impacts` для requirement_id выполняются ДО вызова юриста —
    падение `InHouseLawyer.decide` на этом requirement_id не откатывает их."""
    store = InMemoryMonitoringStore()
    store.add_citation(LEGALX_ACT_ID, "req-1")
    store.add_published_requirement("UZ", "req-1", "Требование под ударом")
    event_id = store.add_event(event_type="amended", jurisdiction="UZ", payload={"act_id": LEGALX_ACT_ID})
    invalid = json.dumps({"needs_reimplementation": True, "from_step": None, "note": "x"})
    lawyer = InHouseLawyer(ScriptedLLM(responses=[invalid, invalid]))  # дважды невалиден -> AgentLLMError

    report = process_changes(store, lawyer=lawyer, orchestrator=RecordingOrchestrator())

    assert any(imp["requirement_id"] == "req-1" for imp in store.impacts)
    assert store.requirements["req-1"]["review_flag"] == "flagged_by_change"
    assert store.requirements["req-1"]["flagged_by_event_id"] == event_id
    assert report.lawyer_errors == 1
    assert report.rereviews_enqueued == 0
    assert store.events[event_id]["processed_at"] is not None
    assert report.events_processed == 1


def test_lawyer_error_on_first_requirement_does_not_block_second_requirement_or_next_event():
    """(а) юрист бросает на 1-м требовании из 2 → второе требование
    обработано, событие processed, очередь идёт дальше (следующее событие
    обработано) — не head-of-line blocking «ядовитым» требованием/событием."""
    store = InMemoryMonitoringStore()
    # событие 1: два затронутых требования, юрист падает на первом
    store.add_citation(LEGALX_ACT_ID, "req-1")
    store.add_citation(LEGALX_ACT_ID, "req-2")
    store.add_published_requirement("UZ", "req-1", "Требование 1")
    store.add_published_requirement("UZ", "req-2", "Требование 2")
    store.add_pipeline_item("req-2", "item-2")
    event1_id = store.add_event(
        event_type="amended", jurisdiction="UZ", payload={"act_id": LEGALX_ACT_ID},
    )
    # событие 2: следующее в очереди, не должно застрять за событием 1
    other_act_id = "22222222-2222-2222-2222-222222222222"
    store.add_citation(other_act_id, "req-3")
    store.add_published_requirement("UZ", "req-3", "Требование 3")
    event2_id = store.add_event(event_type="new", jurisdiction="UZ", payload={"act_id": other_act_id})

    invalid = json.dumps({"needs_reimplementation": True, "from_step": None, "note": "x"})
    llm = ScriptedLLM(
        responses=[
            invalid, invalid,                       # req-1: дважды невалиден -> AgentLLMError
            lawyer_response(True, "norm"),           # req-2: валиден -> rerun_item
            lawyer_response(False, None),            # req-3 (событие 2): валиден, needs=false
        ]
    )
    lawyer = InHouseLawyer(llm)
    orchestrator = RecordingOrchestrator()

    report = process_changes(store, lawyer=lawyer, orchestrator=orchestrator)

    # req-1 — юрист упал, ре-ревью не поставлен, но flag/impact на месте
    assert report.lawyer_errors == 1
    assert store.requirements["req-1"]["review_flag"] == "flagged_by_change"
    # req-2 — то же событие, следующее требование ОБРАБОТАНО как обычно
    assert orchestrator.calls == [("item-2", "norm")]
    assert store.requirements["req-2"]["review_flag"] == "flagged_by_change"
    # событие 1 всё равно помечено processed (иначе очередь встала бы навсегда)
    assert store.events[event1_id]["processed_at"] is not None
    # событие 2 — очередь пошла дальше, а не застряла на «ядовитом» событии 1
    assert store.events[event2_id]["processed_at"] is not None
    assert any(imp["requirement_id"] == "req-3" for imp in store.impacts)
    assert report.events_processed == 2


# ── идемпотентность фан-аута ─────────────────────────────────────────────


def test_fanout_notifications_is_idempotent():
    store = InMemoryMonitoringStore()
    store.add_applicable_user("req-1", "user-1", product_id="prod-1")
    impacts = store.save_impacts("event-1", ["req-1"])
    impact_ids = [imp.id for imp in impacts]

    first = store.fanout_notifications(impact_ids)
    second = store.fanout_notifications(impact_ids)

    assert first == 1
    assert second == 0
    assert len(store.notifications) == 1


def test_save_impacts_is_idempotent_for_same_event_and_requirement():
    store = InMemoryMonitoringStore()
    first = store.save_impacts("event-1", ["req-1"])
    second = store.save_impacts("event-1", ["req-1"])

    assert first[0].id == second[0].id
    assert len(store.impacts) == 1


# ── InHouseLawyer напрямую (валидация ответа, ретрай) ────────────────────


def test_in_house_lawyer_happy_path_needs_true():
    lawyer = InHouseLawyer(ScriptedLLM(responses=[lawyer_response(True, "sanctions", "нужен пересчёт санкций")]))

    decision = lawyer.decide(
        _event(summary="увеличен штраф"), "Требование о маркировке",
    )

    assert decision.needs_reimplementation is True
    assert decision.from_step == "sanctions"
    assert decision.note == "нужен пересчёт санкций"


def test_in_house_lawyer_happy_path_needs_false_from_step_must_be_null():
    lawyer = InHouseLawyer(ScriptedLLM(responses=[lawyer_response(False, None, "чисто техническая правка")]))

    decision = lawyer.decide(_event(), "Требование о маркировке")

    assert decision.needs_reimplementation is False
    assert decision.from_step is None


def test_in_house_lawyer_uses_expensive_tier_model():
    llm = ScriptedLLM(responses=[lawyer_response(False, None)])
    lawyer = InHouseLawyer(llm)

    lawyer.decide(_event(), "Требование")

    config = load_models_config()
    assert llm.calls[0][1] == config.tiers["expensive"]


def test_in_house_lawyer_retries_once_on_invalid_response_then_succeeds():
    # первый ответ невалиден (from_step отсутствует, хотя needs=true)
    invalid = json.dumps({"needs_reimplementation": True, "from_step": None, "note": "x"})
    llm = ScriptedLLM(responses=[invalid, lawyer_response(True, "norm")])
    lawyer = InHouseLawyer(llm)

    decision = lawyer.decide(_event(), "Требование")

    assert decision.needs_reimplementation is True
    assert decision.from_step == "norm"
    assert len(llm.calls) == 2


def test_in_house_lawyer_raises_after_two_invalid_responses():
    invalid = json.dumps({"needs_reimplementation": True, "from_step": "not-a-real-step", "note": "x"})
    llm = ScriptedLLM(responses=[invalid, invalid])
    lawyer = InHouseLawyer(llm)

    with pytest.raises(AgentLLMError):
        lawyer.decide(_event(), "Требование")


def test_in_house_lawyer_rejects_from_step_outside_step_order():
    assert "not-a-real-step" not in STEP_ORDER  # sanity check фикстуры выше


def _event(summary: str | None = "изменение нормы", jurisdiction: str = "UZ"):
    from importer.monitoring.impact_mapper import ChangeEventRecord

    return ChangeEventRecord(
        id="event-1", event_type="amended", jurisdiction=jurisdiction,
        effective_date="2027-01-01", summary=summary, payload={"act_id": LEGALX_ACT_ID},
    )


# ══════════════════════════════════════════════════════════════════════════
# MapAwareRerunOrchestrator — гейт живого прогона, пункт 2 (LAUNCH_CHECKLIST.md)
# ══════════════════════════════════════════════════════════════════════════


def _noop_steps() -> dict:
    """Реестр шагов-заглушек: каждый шаг сразу `ok` — `Orchestrator.
    rerun_item` доходит до конца STEP_ORDER без реальных LLM/сети."""
    return {step: (lambda ctx: StepResult(status="ok")) for step in STEP_ORDER}


def make_fake_registry_factory(calls: list[dict]):
    """Фейковая замена `build_step_registry` — фиксирует `group_ref`/
    `jurisdiction`, с которыми её вызвали, вместо реальной сборки
    generic-агентов (задача просит именно «инспекцию registry» через
    фейк-фабрику)."""

    def factory(build_store, llm_runner, legalx, *, group_ref, jurisdiction, tracer=None):
        calls.append({"group_ref": group_ref, "jurisdiction": jurisdiction})
        return _noop_steps()

    return factory


def _seed_item(monitor_store: InMemoryMonitoringStore, build_store: InMemoryStore, *, map_id: str) -> str:
    """Заводит ОДИН и тот же `item_id` в обоих сторах — как в реальности
    `SupabaseMonitoringStore`/`SupabaseBuildStore` читают одну и ту же
    строку `pipeline.items`, просто разными Python-обёртками."""
    item_id = monitor_store.add_pipeline_item_for_map(map_id, "норма X")
    item = monitor_store.pipeline_items[-1]
    build_store.items[item_id] = ItemRecord(id=item_id, run_id=item["run_id"], expected_item="норма X")
    return item_id


def test_map_aware_rerun_orchestrator_builds_registry_with_real_map_params_not_stubs():
    """Пин-тест гейта живого прогона: ре-ревью айтема карты
    (group_ref='2204', jurisdiction='UZ') строит реестр шагов ИМЕННО с
    этими значениями, не с заглушками `_STUB_GROUP_REF=''`/
    `DEFAULT_JURISDICTION='UZ'` глобального реестра."""
    monitor_store = InMemoryMonitoringStore()
    build_store = InMemoryStore()
    map_id = monitor_store.add_approved_map(jurisdiction="UZ", payload=[], group_ref="2204")
    item_id = _seed_item(monitor_store, build_store, map_id=map_id)

    calls: list[dict] = []
    orchestrator = MapAwareRerunOrchestrator(
        build_store, monitor_store, lambda p, m: "", legalx=object(),
        registry_factory=make_fake_registry_factory(calls),
    )

    orchestrator.rerun_item(item_id, STEP_ORDER[0])

    assert calls == [{"group_ref": "2204", "jurisdiction": "UZ"}]
    assert build_store.items[item_id].status == "draft_loaded"


def test_map_aware_rerun_orchestrator_caches_registry_per_map_id():
    """Два айтема ОДНОЙ карты — реестр строится ОДИН раз (кэш по `map_id`),
    не на каждый `rerun_item`."""
    monitor_store = InMemoryMonitoringStore()
    build_store = InMemoryStore()
    map_id = monitor_store.add_approved_map(jurisdiction="UZ", payload=[], group_ref="2204")
    item_1 = _seed_item(monitor_store, build_store, map_id=map_id)
    item_2 = monitor_store.add_pipeline_item_for_map(map_id, "норма Y", run_id=monitor_store.pipeline_items[0]["run_id"])
    build_store.items[item_2] = ItemRecord(
        id=item_2, run_id=monitor_store.pipeline_items[0]["run_id"], expected_item="норма Y"
    )

    calls: list[dict] = []
    orchestrator = MapAwareRerunOrchestrator(
        build_store, monitor_store, lambda p, m: "", legalx=object(),
        registry_factory=make_fake_registry_factory(calls),
    )

    orchestrator.rerun_item(item_1, STEP_ORDER[0])
    orchestrator.rerun_item(item_2, STEP_ORDER[0])

    assert calls == [{"group_ref": "2204", "jurisdiction": "UZ"}]  # ОДИН раз
    assert build_store.items[item_1].status == "draft_loaded"
    assert build_store.items[item_2].status == "draft_loaded"


def test_map_aware_rerun_orchestrator_builds_separate_registries_for_different_maps():
    """Айтемы РАЗНЫХ карт — реестр строится под каждую карту отдельно, с её
    собственными group_ref/jurisdiction."""
    monitor_store = InMemoryMonitoringStore()
    build_store = InMemoryStore()
    map_2204 = monitor_store.add_approved_map(jurisdiction="UZ", payload=[], group_ref="2204")
    map_2402 = monitor_store.add_approved_map(jurisdiction="KZ", payload=[], group_ref="2402")
    item_1 = _seed_item(monitor_store, build_store, map_id=map_2204)
    item_2 = _seed_item(monitor_store, build_store, map_id=map_2402)

    calls: list[dict] = []
    orchestrator = MapAwareRerunOrchestrator(
        build_store, monitor_store, lambda p, m: "", legalx=object(),
        registry_factory=make_fake_registry_factory(calls),
    )

    orchestrator.rerun_item(item_1, STEP_ORDER[0])
    orchestrator.rerun_item(item_2, STEP_ORDER[0])

    assert calls == [
        {"group_ref": "2204", "jurisdiction": "UZ"},
        {"group_ref": "2402", "jurisdiction": "KZ"},
    ]


def test_map_aware_rerun_orchestrator_skips_unresolvable_item_with_warning(caplog):
    """Айтем без резолвящейся карты (не заведён ни в `pipeline_items`
    монитор-стора) — WARNING в лог, `rerun_item` НЕ падает и не строит
    реестр (нечего строить — group_ref/jurisdiction неизвестны)."""
    monitor_store = InMemoryMonitoringStore()
    build_store = InMemoryStore()

    calls: list[dict] = []
    orchestrator = MapAwareRerunOrchestrator(
        build_store, monitor_store, lambda p, m: "", legalx=object(),
        registry_factory=make_fake_registry_factory(calls),
    )

    with caplog.at_level("WARNING"):
        orchestrator.rerun_item("item-does-not-exist", "norm")

    assert calls == []
    assert any("item-does-not-exist" in rec.message for rec in caplog.records)


def test_map_aware_rerun_orchestrator_default_registry_factory_is_real_build_step_registry():
    """Без явного `registry_factory=` используется настоящий
    `build_step_registry` (`registry.py`) — фейк в остальных тестах этого
    блока не подменяет собой единственный путь конструирования."""
    from importer.build.registry import build_step_registry

    monitor_store = InMemoryMonitoringStore()
    build_store = InMemoryStore()
    orchestrator = MapAwareRerunOrchestrator(
        build_store, monitor_store, lambda p, m: "", legalx=object(),
    )
    assert orchestrator._registry_factory is build_step_registry
