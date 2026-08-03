"""История изменений требования (Задача 41, Блок 6, финал контура C).

`build_change_history(store, requirement_id)` — скрипт БЕЗ агента (не LLM,
детерминированный код): по `requirement_change_impacts` требования собирает
хронологию связанных `change_events` и пишет их в `requirement_revisions` —
ЕДИНСТВЕННОЕ хранилище, которое реально читает фронт.

## Куда на самом деле смотрит фронт (сверка с брифом)

Бриф задачи говорит «в `requirement_details`», но это неверно: `requirement_
details` — уровень 1 (описание/шаги/санкции текущей редакции, платный
тизер-контент), а не журнал «было/стало». Фактический источник фронта —
`requirement_revisions` (`20260711120000_initial_schema.sql`, комментарий
«jsonb-снапшот всей карточки при каждой публикации... закрывает было/стало
уровня 2»): `src/data/real.ts:fetchRequirementCard` читает

    requirement_revisions
      .select('revision_no, change_note, created_at,
                change_events(title, was_text, now_text)')
      .eq('requirement_id', requirementId)
      .order('revision_no', {ascending: false})

и мапит в `HistoryEntry` (`src/data/types.ts`): `date = created_at`,
`title = change_events.title ?? change_note ?? 'Редакция обновлена'`,
`was/now = change_events.was_text/now_text`. Рендерит `CRequirementCard.
tsx:CLegalPanel` под заголовком «История изменений» (`src/i18n/ru.ts`). До
этой задачи `requirement_revisions` не писал НИКТО — секция истории на
проде пуста для всех требований; эта функция — первый писатель.

## Ограничение (до D4 — версионирование LegalX)

Полнота истории ограничена ЛОКАЛЬНЫМИ `change_events`, дошедшими через
webhook LegalX (Задача 39) и Impact-маппер (Задача 40, `requirement_change_
impacts`) — какие версии акт прошёл ДО того, как webhook начал слать
события, эта функция не знает: `change_events` не несёт ретроспективного
бэкафилла. Полная история версий акта (весь его путь до появления
InspectorX) — задача D4 (версионирование LegalX), вне контура этого
репозитория. Задокументировано по требованию брифа задачи.

## Что попадает в `HistoryEntry`

- `date` (`requirement_revisions.created_at`, ЯВНО переданный, не дефолт
  колонки `now()`): `event.effective_date`, если есть, иначе `event.
  created_at` (момент, когда сама строка `change_events` была создана);
- `title`/`was`/`now` фронт берёт через join на `change_events` — эта
  функция их НЕ дублирует в `requirement_revisions` напрямую (нет для этого
  колонок), только пишет `change_event_id`, чтобы join отработал;
- `change_note` — `event.summary` (фолбэк фронта, если `change_events.
  title` вдруг станет опциональным — сейчас `NOT NULL`, см. схему).

`was_text`/`now_text` заполнены ТОЛЬКО у ручных `change_events` (`source=
'manual'`) — Контракт 3 (`docs/adr/0005-ecosystem-contracts.md`) вебхука
LegalX (`ingest_change_event`, Задача 39) не несёт этих полей вовсе, так
что для webhook-событий `was`/`now` в истории честно будут пустыми — это не
баг этой функции, а состав входных данных.

## snapshot (`requirement_revisions.snapshot`, `NOT NULL`)

Комментарий схемы называет это «jsonb-снапшот ВСЕЙ карточки при каждой
публикации» — полноценная сборка (весь `requirement_details`/`requirement_
contents` на момент события) вне периметра этого скрипта: он работает
только от `change_events`/impacts, Build/Assembler не трогает. Пишем
МИНИМАЛЬНЫЙ снепшот СОБЫТИЯ (`{event_type, summary, effective_date}`) —
фронт его не читает (см. выше), это задел под полноценный снепшот карточки,
который ляжет сюда отдельной задачей, когда появится единая точка
«опубликовали новую редакцию» (сейчас Build публикует только ПЕРВУЮ
редакцию, ре-ревью Задачи 40 не создаёт новую версию карточки, только
чинит существующую).

## Идемпотентность

Один `change_event_id` -> одна строка `requirement_revisions` на
требование: `list_existing_revision_event_ids` отдаёт уже записанные
`change_event_id`, они пропускаются — повторный вызов `build_change_history`
для того же требования (в т.ч. из `process_changes` на следующем событии)
не плодит дублей, только добавляет ревизии для НОВЫХ событий.

## Вызов

- CLI `monitor build-history --requirement <id>` (`importer/cli.py`) —
  ручной прогон/бэкафилл для конкретного требования;
- `impact_mapper.py:process_changes` вызывает эту функцию АВТОМАТИЧЕСКИ для
  каждого затронутого требования сразу после `save_impacts`/
  `flag_requirement` — история появляется в том же цикле, что и impact/флаг,
  не отдельным cron'ом.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # только тип — избегаем цикла с impact_mapper.py на рантайме
    from importer.monitoring.impact_mapper import MonitoringStore


@dataclass
class HistoryBuildReport:
    """Итог `build_change_history` — сколько ревизий добавлено/пропущено
    (идемпотентность) для требования."""

    requirement_id: str
    revisions_added: int = 0
    revisions_skipped_existing: int = 0


def build_change_history(store: "MonitoringStore", requirement_id: str) -> HistoryBuildReport:
    """Собирает хронологию `change_events` требования (через `requirement_
    change_impacts`) и пишет НОВЫЕ (см. докстринг модуля, идемпотентность)
    строки `requirement_revisions`. Событий может не быть вовсе (требование
    ни разу не флагалось Impact-маппером) — тогда отчёт с нулями, это
    валидный исход, не ошибка."""
    report = HistoryBuildReport(requirement_id=requirement_id)
    already_recorded = store.list_existing_revision_event_ids(requirement_id)

    for event in store.list_change_events_for_requirement(requirement_id):
        if event.change_event_id in already_recorded:
            report.revisions_skipped_existing += 1
            continue

        date = event.effective_date or event.created_at
        snapshot = {
            "event_type": event.event_type,
            "summary": event.summary,
            "effective_date": event.effective_date,
        }
        store.save_revision(
            requirement_id,
            change_event_id=event.change_event_id,
            change_note=event.summary,
            snapshot=snapshot,
            created_at=date,
        )
        report.revisions_added += 1

    return report
