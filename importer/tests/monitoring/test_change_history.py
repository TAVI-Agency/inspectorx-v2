"""Тесты истории изменений требования (Задача 41) — `change_history.py`.

Сценарии из уточнений контроллера:
- история из 2 `requirement_change_impacts` -> 2 записи хронологии
  (`requirement_revisions`);
- идемпотентность повторной сборки — второй вызов на том же требовании не
  плодит дублей;
- `date` = `event.effective_date`, если есть, иначе `event.created_at`;
- требование без единого impact'а -> пустой отчёт, не ошибка;
- `process_changes` (Impact-маппер, Задача 40) вызывает `build_change_history`
  автоматически для каждого затронутого требования после `save_impacts`.

Стор — `InMemoryMonitoringStore` (`importer/tests/monitoring/stores.py`), БД
не трогаем — тот же паттерн, что и `test_impact_mapper.py`.
"""
from __future__ import annotations

from importer.monitoring.change_history import build_change_history
from importer.monitoring.impact_mapper import process_changes
from importer.tests.monitoring.stores import InMemoryMonitoringStore

LEGALX_ACT_ID = "11111111-1111-1111-1111-111111111111"


def test_history_from_two_impacts_creates_two_revisions():
    store = InMemoryMonitoringStore()
    event1 = store.add_event(
        event_type="amended",
        effective_date="2027-01-01",
        summary="изменена ставка акциза",
        title="LegalX: amended act-1",
    )
    event2 = store.add_event(
        event_type="repealed",
        effective_date="2027-06-01",
        summary="норма отменена",
        title="LegalX: repealed act-1",
    )
    store.impacts.append(
        {"id": "impact-1", "change_event_id": event1, "requirement_id": "req-1", "status": "pending_review"}
    )
    store.impacts.append(
        {"id": "impact-2", "change_event_id": event2, "requirement_id": "req-1", "status": "pending_review"}
    )

    report = build_change_history(store, "req-1")

    assert report.revisions_added == 2
    assert report.revisions_skipped_existing == 0
    assert len(store.revisions) == 2

    revs_by_event = {rev["change_event_id"]: rev for rev in store.revisions}
    assert revs_by_event[event1]["requirement_id"] == "req-1"
    assert revs_by_event[event1]["created_at"] == "2027-01-01"
    assert revs_by_event[event1]["change_note"] == "изменена ставка акциза"
    assert revs_by_event[event2]["created_at"] == "2027-06-01"

    # revision_no — последовательные, уникальные для требования
    assert {rev["revision_no"] for rev in store.revisions} == {1, 2}

    # snapshot — непустой jsonb (NOT NULL колонка), см. докстринг модуля
    assert revs_by_event[event1]["snapshot"]["event_type"] == "amended"


def test_build_change_history_is_idempotent_on_repeated_call():
    store = InMemoryMonitoringStore()
    event1 = store.add_event(event_type="amended", effective_date="2027-01-01")
    store.impacts.append(
        {"id": "impact-1", "change_event_id": event1, "requirement_id": "req-1", "status": "pending_review"}
    )

    first = build_change_history(store, "req-1")
    second = build_change_history(store, "req-1")

    assert first.revisions_added == 1
    assert second.revisions_added == 0
    assert second.revisions_skipped_existing == 1
    assert len(store.revisions) == 1


def test_new_event_after_first_build_adds_only_one_more_revision():
    """Повторный вызов ПОСЛЕ появления нового impact'а добавляет только
    ревизию нового события — старая не переписывается заново."""
    store = InMemoryMonitoringStore()
    event1 = store.add_event(event_type="amended", effective_date="2027-01-01")
    store.impacts.append(
        {"id": "impact-1", "change_event_id": event1, "requirement_id": "req-1", "status": "pending_review"}
    )
    build_change_history(store, "req-1")

    event2 = store.add_event(event_type="repealed", effective_date="2027-06-01")
    store.impacts.append(
        {"id": "impact-2", "change_event_id": event2, "requirement_id": "req-1", "status": "pending_review"}
    )
    second = build_change_history(store, "req-1")

    assert second.revisions_added == 1
    assert second.revisions_skipped_existing == 1
    assert len(store.revisions) == 2
    assert {rev["revision_no"] for rev in store.revisions} == {1, 2}


def test_requirement_without_impacts_yields_empty_report():
    store = InMemoryMonitoringStore()

    report = build_change_history(store, "req-without-events")

    assert report.revisions_added == 0
    assert report.revisions_skipped_existing == 0
    assert store.revisions == []


def test_date_falls_back_to_event_created_at_when_no_effective_date():
    store = InMemoryMonitoringStore()
    event1 = store.add_event(
        event_type="new", effective_date=None, created_at="2027-03-15T10:00:00+00:00",
    )
    store.impacts.append(
        {"id": "impact-1", "change_event_id": event1, "requirement_id": "req-1", "status": "pending_review"}
    )

    build_change_history(store, "req-1")

    assert store.revisions[0]["created_at"] == "2027-03-15T10:00:00+00:00"


def test_process_changes_calls_build_change_history_for_flagged_requirements():
    """Интеграция с Impact-маппером (Задача 40): `process_changes` сам
    строит историю для каждого затронутого требования, без отдельного
    ручного `monitor build-history`."""
    store = InMemoryMonitoringStore()
    store.add_citation(LEGALX_ACT_ID, "req-1")
    event_id = store.add_event(
        event_type="amended", jurisdiction="UZ", effective_date="2027-01-01",
        summary="изменение", payload={"act_id": LEGALX_ACT_ID},
    )

    report = process_changes(store)

    assert report.revisions_recorded == 1
    assert len(store.revisions) == 1
    assert store.revisions[0]["requirement_id"] == "req-1"
    assert store.revisions[0]["change_event_id"] == event_id

    # повторный прогон (то же событие уже processed_at) не плодит ревизий
    report2 = process_changes(store)
    assert report2.revisions_recorded == 0
    assert len(store.revisions) == 1
