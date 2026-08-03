"""Discovery cron-джоб (Задача 41, Блок 6, финал контура C).

## Сужение брифа: откуда берём «свежие акты LegalX»

Бриф задачи просил ловить «свежие акты LegalX, никем не связанные» — метода
вроде `LegalXClient.list_recent_acts` НЕТ ни в Protocol (`importer/build/
legalx.py`), ни в Контракте 3 (`docs/adr/0005-ecosystem-contracts.md`):
самостоятельный обход LegalX за «что нового появилось» контрактом не
предусмотрен. РЕШЕНИЕ КОНТРОЛЛЕРА (см. `task-41-brief.md`, «уточнения
контроллера»): вместо отдельного опроса LegalX discovery работает от УЖЕ
полученных webhook-событий (`change_events`, Задача 39) — конкретно от
`event_type='new'`, которые Impact-маппер (Задача 40, `process_changes`)
обработал (`processed_at is not null`), но не сопоставил НИ С ОДНИМ
существующим требованием (0 строк `requirement_change_impacts`).

Это осознанное сужение: «новые акты» ловятся ТОЛЬКО через уже пришедший
webhook, не через самостоятельный обход каталога LegalX. Контракт 3
подписывает InspectorX на `new`-события — если LegalX действительно шлёт
их при появлении новых актов (как обещает контракт), дыра открывается
только пока webhook и правда молчит, а это вне контроля этого репозитория.

## Как ищет кандидатов

Для каждого такого события:
1. берём все `approved`-карты (`pipeline.maps`) той же юрисдикции;
2. для каждого айтема карты (`MapItem` из `payload`) генерируем уточняющие
   вопросы тем же движком, что и Build (`question_writer.write_questions`);
3. прогоняем каждый вопрос через `LegalXClient.search_norms` (мок/live,
   `importer/build/legalx.py:get_client`, то же переключение
   `LEGALX_BACKEND`, что и Build, — контур discovery повторно использует
   Build-контракт, не заводит параллельный).

«Хит» — среди найденных `NormFragment` есть хотя бы один с `act_id`,
совпадающим с `act_id` события (`ChangeEventRecord.legalx_act_id`,
Контракт 3): вопрос карты нашёл текст именно в ТОМ акте, который прислал
webhook, — то есть новый акт релевантен этому конкретному ожидаемому
требованию карты.

## Кандидат = `pipeline.items`, НЕ requirement

Бриф просил заводить «черновые requirements draft». РЕШЕНИЕ КОНТРОЛЛЕРА
сужает это до `pipeline.items(status='pending')` в новом «discovery-run»
(`pipeline.runs`, привязан к карте, чьи вопросы дали хит): черновой
`public.requirements` здесь НЕ заводится — кандидат дособирает обычный
Build (`Orchestrator.run_group` по новому прогону либо `rerun_item`), у
которого уже есть весь конвейер шагов (scope/rule/sanction/...); заводить
параллельный путь сборки черновика прямо в discovery избыточно и дублирует
Build.

## Идемпотентность СО СТАТУС-ФИЛЬТРОМ (фикс-раунд ревью)

`(map_id, expected_item)`, но НЕ «любой найденный item» — см. докстринг
`MonitoringStore.is_expected_item_already_covered`. Первая версия
(`find_existing_discovery_item`) блокировала кандидата, если под картой
УЖЕ существовал ЛЮБОЙ `pipeline.items` с тем же `expected_item`, независимо
от статуса. Это был баг (Important, ревью Задачи 41): для ЛЮБОЙ уже
собранной карты (а approved-карта почти всегда уже прогнана Build хотя бы
раз) discovery превращался в вечный no-op — включая ровно тот сценарий,
который просил бриф («новый акт закрывает пробел, который прежний прогон
не смог закрыть»).

Теперь блокируют только статусы `pending`/`in_progress`/`draft_loaded`/
`published` (`DISCOVERY_BLOCKING_STATUSES`, `impact_mapper.py`) — «уже в
работе или закрыт». `no_norm`/`needs_attention` НЕ блокируют: это и есть
пробел, который новый акт может закрыть, — discovery заводит НОВЫЙ
кандидат-item поверх старого (старый no_norm/needs_attention никуда не
девается, это отдельная строка `pipeline.items`, Build дособерёт по
новому). Повторный прогон discovery на уже `pending`/`published` айтеме
находит покрытие ДО вызова LLM/поиска (`write_questions`/`search_norms` не
вызываются повторно) и пропускает его.

## Известное ограничение

Айтемы карты, которые НЕ дали хита в текущем прогоне (и остались
`no_norm`/`needs_attention` либо вообще не заводили `pipeline.items`),
перепроверяются КАЖДЫЙ следующий прогон discovery (нет негативного кэша
«уже проверяли — не нашли», см. `is_expected_item_already_covered`) — цена
простоты первой итерации. Если объём карт/вопросов вырастет настолько, что
это станет дорого, стоит завести отдельный учёт проверенных пар `(event,
map_item)`.

## CLI

`monitor discovery` (`importer/cli.py`) — cron Railway, тот же принцип, что
и `monitor process-changes` (см. докстринг `impact_mapper.py`); запускать
ПОСЛЕ `process-changes` в расписании — discovery смотрит только на уже
`processed_at`-события.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from importer.build.legalx import LegalXClient, get_client
from importer.build.llm_client import AgentLLMClient
from importer.build.question_writer import MapItem, write_questions
from importer.monitoring.impact_mapper import MonitoringStore

logger = logging.getLogger(__name__)


@dataclass
class DiscoveryReport:
    """Итог одного вызова `run_discovery` — сколько событий/айтемов куда
    пришли."""

    events_seen: int = 0
    # 'new'-событие без act_id (ручное, не от LegalX) — искать нечего: «хит»
    # определяется совпадением NormFragment.act_id (докстринг модуля).
    events_skipped_no_act_id: int = 0
    items_checked: int = 0
    # Айтем уже покрыт активным/финальным статусом (см. докстринг модуля,
    # «Идемпотентность СО СТАТУС-ФИЛЬТРОМ») — НЕ считает no_norm/
    # needs_attention покрытием, только pending/in_progress/draft_loaded/
    # published.
    items_already_covered: int = 0
    # Ошибка search_norms (сеть/LegalX недоступен) на конкретном айтеме —
    # айтем считается no-hit, прогон продолжается (фикс-раунд ревью, Important).
    search_errors: int = 0
    candidates_created: int = 0


def run_discovery(
    store: MonitoringStore,
    *,
    llm: AgentLLMClient,
    legalx: LegalXClient | None = None,
) -> DiscoveryReport:
    """Прогоняет discovery по всем `change_events(event_type='new')` без
    impacts (докстринг модуля). `legalx` — опциональная инъекция (тесты
    подставляют скриптованный фейк); без неё — `get_client()` (переключение
    `LEGALX_BACKEND`, тот же принцип, что и в Build, `importer/cli.py`)."""
    legalx = legalx or get_client()
    report = DiscoveryReport()

    for event in store.list_new_events_without_impacts():
        report.events_seen += 1
        act_id = event.legalx_act_id
        if act_id is None:
            report.events_skipped_no_act_id += 1
            continue

        for map_record in store.list_approved_maps(event.jurisdiction):
            for raw_item in map_record.payload:
                report.items_checked += 1
                map_item = MapItem(
                    expected_item=raw_item["expected_item"],
                    category_slug=raw_item["category_slug"],
                    rationale=raw_item.get("rationale", ""),
                    benchmark_countries=raw_item.get("benchmark_countries", []),
                )

                if store.is_expected_item_already_covered(
                    map_record.id, map_item.expected_item
                ):
                    report.items_already_covered += 1
                    continue

                try:
                    questions = write_questions(map_item, llm=llm)
                except ValueError as exc:
                    # question_writer исчерпал ретраи (докстринг
                    # write_questions) — не повод падать всему прогону
                    # discovery, просто этот айтем в этот раз пропускается.
                    logger.warning(
                        "discovery: write_questions упал на map=%s item=%r: %s",
                        map_record.id, map_item.expected_item, exc,
                    )
                    continue

                try:
                    hit = _has_hit(legalx, questions, event.jurisdiction, act_id)
                except Exception as exc:
                    # search_norms — сетевой вызов к LegalX без узкого
                    # контракта исключений (в отличие от AgentLLMClient,
                    # чьи ошибки — AgentLLMError/ValueError); ловим широко
                    # (паттерн NormStep, `steps_norm.py`, «шаги ловят
                    # исключения сами, а не дают им всплыть»), иначе
                    # временная недоступность LegalX на ОДНОМ айтеме роняла
                    # бы весь `monitor discovery` (фикс-раунд ревью, Important).
                    logger.warning(
                        "discovery: search_norms упал на map=%s item=%r: %s",
                        map_record.id, map_item.expected_item, exc,
                    )
                    report.search_errors += 1
                    continue

                if not hit:
                    continue

                run_id = store.create_discovery_run(map_record.id)
                item_id = store.create_discovery_item(
                    run_id, map_item.expected_item, map_item.category_slug
                )
                report.candidates_created += 1
                logger.info(
                    "discovery: событие=%s карта=%s айтем=%r -> кандидат pipeline.items=%s",
                    event.id, map_record.id, map_item.expected_item, item_id,
                )

    return report


def _has_hit(legalx: LegalXClient, questions: list, jurisdiction: str, act_id: str) -> bool:
    """«Хит» — см. докстринг модуля: хотя бы один найденный `NormFragment`
    принадлежит именно акту события."""
    for question in questions:
        fragments = legalx.search_norms(question.text, jurisdiction, limit=5)
        if any(fragment.act_id == act_id for fragment in fragments):
            return True
    return False
