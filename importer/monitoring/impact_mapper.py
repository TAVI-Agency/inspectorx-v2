"""Impact-маппер + In-house lawyer (мониторинг) + ре-ревью (Задача 40, Блок 6
контур C, `docs/adr/0005-ecosystem-contracts.md` Контракт 3).

## Конвейер `process_changes`

`change_events` (webhook LegalX, Задача 39, `ingest_change_event`) →
1. дедуп повторной доставки webhook'а (idempotency, ADR-0005) →
2. маппинг на затронутые `requirements` (два пути, см. ниже) →
3. `requirement_change_impacts(status='pending_review')` + `review_flag=
   'flagged_by_change'` на каждом затронутом требовании (карточка ОСТАЁТСЯ
   на витрине — `flagged_by_change` не статус, а флаг поверх `published`,
   см. `20260711120000_initial_schema.sql`) →
4. In-house lawyer (expensive Classifier) решает ПО КАЖДОМУ затронутому
   требованию — нужна ли полная переимплементация (`needs_reimplementation`);
   если да — `rerun_item(item_id, from_step)` частичного Build →
5. фан-аут `user_notifications(kind='change')` пользователям, у кого выбран
   применимый товар/услуга.

## Два пути маппинга событие → требования

**(а) Точный — по цитатам.** `change_events.payload->>'act_id'` — LegalX-uuid
акта (контракт 3); ЛОКАЛЬНЫЙ `change_events.act_id` (FK на `public.acts`)
всегда `NULL` для webhook-событий (см. докстринг
`20260804110000_ingest_change_event.sql`) — сопоставление делает ЭТОТ модуль.
Мост: `public.acts.jurisbase_act_id` (text) — тот же LegalX-uuid, СТРОКОЙ,
который резолвер отчётов (`importer/resolver.py:resolve_act`) пишет при
импорте отчёта через lex.uz/JurisBase. Путь: `acts.jurisbase_act_id =
payload->>'act_id'` → `act_paragraphs.act_id` → `requirement_citations.
paragraph_id` → `requirement_id` (`MonitoringStore.find_requirements_by_
citation`).

**ИЗВЕСТНОЕ ОГРАНИЧЕНИЕ пути (а)** (важно для отчёта задачи): цитаты
(`requirement_citations`) пишет ТОЛЬКО легаси-конвейер импорта отчётов
(`importer/loader.py`, `import-report`) — Build-конвейер (`importer/build/
orchestrator.py:SupabaseBuildStore.save_requirement_draft`) их пока НЕ
пишет (собственный докстринг метода: «card['citations'] НЕ используется —
известный пробел, нет ETL LegalX-фрагмент -> локальный act_paragraphs»).
Значит точный маппинг СЕЙЧАС работает только для требований, заведённых
через `import-report`, а не для растущего корпуса Build-конвейера — для них
остаётся только путь (б), пока этот пробел не закрыт отдельной задачей.
`act_paragraphs` к тому же не хранит LegalX `fragment_id` пунктов — точный
маппинг работает на грануляции АКТА, не конкретного пункта/фрагмента.

**(б) Текстовый кандидат — Classifier (cheap).** Когда путь (а) не дал ни
одного требования (либо `payload` вообще не содержит `act_id` — ручное
событие) — Classifier сравнивает `summary` события с заголовками
ОПУБЛИКОВАННЫХ требований той же юрисдикции (`list_published_requirements`)
и возвращает кандидатов со скором; проходят порог `CANDIDATE_SCORE_
THRESHOLD`. Мусорный/невалидный ответ LLM — не повод падать (это
best-effort подсказка, не авторитетная запись): просто ноль кандидатов.
Пустой список опубликованных требований юрисдикции — Classifier вообще не
вызывается (экономия, тот же принцип, что и в `steps_samples_lawyer.py` при
пустом веб-поиске).

## Дедупликация повторной доставки webhook'а

`ingest_change_event` (Задача 39) идемпотентности не гарантирует — повторная
доставка создаёт НОВУЮ строку `change_events`. Перед обработкой каждого
необработанного события маппер проверяет: есть ли УЖЕ обработанное событие
с тем же `(payload->>'act_id', event_type, effective_date)` — если да,
текущее событие помечается `processed_at` и пропускается без повторной
записи impacts/уведомлений. Событие БЕЗ `act_id` (ручное, не от LegalX)
дедупу не подлежит — ложных совпадений «два независимых ручных события в
одну дату» быть не должно.

## In-house lawyer (мониторинг) — ОТДЕЛЬНАЯ роль от шага 'lawyer' Build

`steps_samples_lawyer.py:LawyerStep` (шаг 'lawyer' STEP_ORDER) формулирует
verdict/steps ДЛЯ карточки при ПЕРВИЧНОЙ сборке. `InHouseLawyer` этого
модуля — другая роль: оценивает СОБЫТИЕ изменения источника против УЖЕ
существующей опубликованной карточки и решает, перезапускать ли Build
partial rerun (`Orchestrator.rerun_item`), либо изменение не требует
пересборки (косметика, подтверждение статус-кво).

## Устойчивость к «ядовитому» требованию (ревью Задачи 40, Important)

`InHouseLawyer.decide` может исчерпать свой ретрай и бросить `AgentLLMError`
(дважды невалидный ответ LLM) НА ОДНОМ КОНКРЕТНОМ затронутом требовании
события. `process_changes` ловит эту ошибку ЛОКАЛЬНО, вокруг вызова
`.decide` для ЭТОГО требования — impacts и `flag_requirement` для него уже
записаны СТРОКОЙ ВЫШЕ и НЕ откатываются; просто ре-ревью для этого
требования не ставится в очередь автоматически (чинится вручную —
`orchestrator.rerun_item(item_id, from_step)` напрямую, после разбора
причины в логе warning). Остальные требования этого же события и
остальные события очереди обрабатываются как обычно, событие в конце всё
равно помечается `processed_at` — без этого одно «ядовитое» требование
стопорило бы ВСЮ очередь необработанных событий навсегда (head-of-line
blocking, событие с ним никогда бы не помечалось обработанным, следующие
события до него бы не доходили).

## Railway cron (докстринг-заметка, инфра вне репозитория)

Продовый запуск — cron-джоб Railway `python -m importer monitor
process-changes` раз в 15 минут (без публичного endpoint — YAGNI, wake-по-
pg_net добавится при необходимости). Сама настройка джоба — вне этого
репозитория (Railway), здесь только CLI-точка входа (`importer/cli.py`).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Literal, Protocol

from importer.build.agents import Classifier, ModelsConfig, load_models_config
from importer.build.llm_client import AgentLLMClient, AgentLLMError
from importer.build.profiles import Profile
from importer.build.steps import STEP_ORDER

if TYPE_CHECKING:  # только тип — импорт по значению создал бы цикл impact_mapper<->trace
    from importer.build.trace import Tracer

# Задача 41 (история изменений) — импорт ПО ЗНАЧЕНИЮ безопасен: change_history
# импортирует MonitoringStore обратно ТОЛЬКО под TYPE_CHECKING (см. докстринг
# change_history.py), поэтому цикла на рантайме нет, в отличие от Tracer выше.
from importer.monitoring.change_history import build_change_history

logger = logging.getLogger(__name__)

# Порог скора Classifier-кандидата (путь б) — решение контроллера задачи:
# ниже порога кандидат отбрасывается ДО записи impact (не попадает даже в
# pending_review — это шум, не спорная связь для ревью).
CANDIDATE_SCORE_THRESHOLD = 0.5

# Задача 41 (фикс-раунд ревью, discovery): статусы `pipeline.items`
# (`20260803170000_pipeline_schema.sql`, полный набор — `pending |
# in_progress | draft_loaded | published | needs_attention | no_norm`), при
# которых `is_expected_item_already_covered` считает айтем карты «уже
# покрытым» — discovery НЕ заводит второго кандидата. Осознанно БЕЗ
# `no_norm`/`needs_attention`: это как раз тот пробел, который новый акт
# может закрыть (см. докстринг метода в `MonitoringStore`).
DISCOVERY_BLOCKING_STATUSES = ("pending", "in_progress", "draft_loaded", "published")


# ══════════════════════════════════════════════════════════════════════════
# Типы
# ══════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class ChangeEventRecord:
    """Строка `change_events`, какой её видит маппер."""

    id: str
    event_type: str  # 'new' | 'amended' | 'repealed' | 'effective_soon'
    jurisdiction: str
    effective_date: str | None
    summary: str | None
    payload: dict

    @property
    def legalx_act_id(self) -> str | None:
        """`payload->>'act_id'` (Контракт 3) — LegalX-uuid акта, СТРОКОЙ.
        `None`, если ключа нет либо он пуст (ручное событие без акта)."""
        act_id = self.payload.get("act_id")
        return act_id or None


@dataclass(frozen=True)
class ImpactRecord:
    """Строка `requirement_change_impacts`, какой её видит маппер."""

    id: str
    change_event_id: str
    requirement_id: str
    status: str = "pending_review"


@dataclass(frozen=True)
class MappingCandidate:
    """Кандидат «это требование затронуто этим событием» — до записи в
    `requirement_change_impacts`. `method` — какой путь его нашёл
    (докстринг модуля, пути (а)/(б))."""

    requirement_id: str
    method: Literal["citation", "classifier"]
    score: float = 1.0


@dataclass(frozen=True)
class LawyerDecision:
    """Решение `InHouseLawyer.decide` по одному затронутому требованию."""

    needs_reimplementation: bool
    from_step: str | None
    note: str


@dataclass(frozen=True)
class HistorySourceEvent:
    """`change_events`, каким его видит `change_history.build_change_history`
    (Задача 41) — шире `ChangeEventRecord`: несёт `title`/`created_at`/
    `was_text`/`now_text`, которые фронт реально читает через join
    `requirement_revisions -> change_events(title, was_text, now_text)`
    (`src/data/real.ts:fetchRequirementCard`). Отдельный тип, а не расширение
    `ChangeEventRecord`, — путь (а)/(б) маппинга эти поля не использует."""

    change_event_id: str
    event_type: str
    effective_date: str | None
    created_at: str
    summary: str | None
    title: str
    was_text: str | None
    now_text: str | None


@dataclass(frozen=True)
class ApprovedMapRecord:
    """Строка `pipeline.maps(status='approved')`, какой её видит discovery
    (Задача 41, `discovery.py`) — только то, что нужно прогону вопросов:
    без `approved_at`/`approved_by`, в отличие от `orchestrator.py:
    MapRecord`."""

    id: str
    group_ref: str
    jurisdiction: str
    payload: list[dict]


@dataclass
class ProcessingReport:
    """Итог одного вызова `process_changes` — сколько событий куда пришли."""

    events_seen: int = 0
    events_processed: int = 0
    duplicates_skipped: int = 0
    events_no_candidates: int = 0
    impacts_created: int = 0
    requirements_flagged: int = 0
    rereviews_enqueued: int = 0
    notifications_sent: int = 0
    # Ревью Задачи 40 (Important, head-of-line blocking): сколько раз
    # `InHouseLawyer.decide` упал (дважды невалидный ответ) на КОНКРЕТНОМ
    # требовании — событие/остальные требования этого события ИДУТ ДАЛЬШЕ
    # (см. докстринг `process_changes`), это только счётчик для наблюдения.
    lawyer_errors: int = 0
    # Задача 41: сколько строк `requirement_revisions` реально добавлено
    # `build_change_history` за этот прогон (по всем затронутым требованиям
    # всех обработанных событий) — идемпотентные пропуски сюда не считаются,
    # см. `change_history.HistoryBuildReport.revisions_added`.
    revisions_recorded: int = 0


class RerunOrchestratorLike(Protocol):
    """Структурный контракт частичного Build для `process_changes` —
    `importer.build.orchestrator.Orchestrator.rerun_item` уже удовлетворяет
    этому Protocol; в тестах — фейк, который просто фиксирует вызовы."""

    def rerun_item(self, item_id: str, from_step: str) -> None: ...


class MonitoringStore(Protocol):
    """Тонкий интерфейс персистентности мониторинга (Задача 40). Реальная
    реализация — `SupabaseMonitoringStore` ниже; в тестах —
    `InMemoryMonitoringStore` (`importer/tests/monitoring/stores.py`)."""

    def list_unprocessed_events(self) -> list[ChangeEventRecord]:
        """`change_events` с `processed_at is null`, в порядке `created_at`."""
        ...

    def find_duplicate_processed_event(
        self,
        legalx_act_id: str | None,
        event_type: str,
        effective_date: str | None,
        jurisdiction: str,
    ) -> bool:
        """Есть ли УЖЕ обработанное (`processed_at is not null`) событие с
        тем же `(payload->>'act_id', event_type, effective_date, jurisdiction)`
        — идемпотентность повторной доставки webhook'а (докстринг модуля).
        `jurisdiction` — defense-in-depth (ревью Задачи 40, Minor): один и
        тот же LegalX `act_id` теоретически не должен всплывать в двух
        юрисдикциях одновременно, но ключ дедупа не обязан на это полагаться.
        `legalx_act_id=None` -> всегда `False` (ручные события без акта
        дедупу не подлежат)."""
        ...

    def mark_processed(self, event_id: str) -> None:
        """Пишет `change_events.processed_at = now()` — маркер «обработано»
        (в т.ч. для событий без единого кандидата — они тоже обработаны)."""
        ...

    def find_requirements_by_citation(self, legalx_act_id: str) -> list[str]:
        """Точный путь (а) — см. докстринг модуля: `acts.jurisbase_act_id =
        legalx_act_id` -> `act_paragraphs` -> `requirement_citations` ->
        ТОЛЬКО `published` `requirement_id`. Пустой список — валидный исход
        (акт не резолвился локально либо у него пока нет привязанных
        требований), не ошибка."""
        ...

    def list_published_requirements(self, jurisdiction: str) -> list[dict]:
        """`[{"id", "title"}, ...]` опубликованных требований юрисдикции —
        вход Classifier-кандидатов (путь б) и контекста `InHouseLawyer`."""
        ...

    def save_impacts(
        self, change_event_id: str, requirement_ids: list[str]
    ) -> list[ImpactRecord]:
        """Upsert `requirement_change_impacts(status='pending_review')` по
        уникальному `(change_event_id, requirement_id)` — повторный вызов с
        пересекающимся набором `requirement_ids` не плодит дублей, отдаёт
        существующую строку как есть (статус ре-ревью не трогает)."""
        ...

    def flag_requirement(self, requirement_id: str, change_event_id: str) -> None:
        """`requirements.review_flag = 'flagged_by_change'`, `flagged_at =
        now()`, `flagged_by_event_id = change_event_id` — карточка ОСТАЁТСЯ
        на витрине (флаг поверх `published`, не статус)."""
        ...

    def fanout_notifications(self, impact_ids: list[str]) -> int:
        """`user_notifications(kind='change', impact_id=…)` для юзеров с
        применимым товаром/услугой (та же применимость, что и
        `user_deadline_events`: точный `product_type_id` либо широкий scope
        `all_products`/`all_services`) — `ON CONFLICT (user_id, impact_id)
        DO NOTHING` (unique-constraint из `20260711120000_initial_schema.sql`
        уже это гарантирует). Возвращает число РЕАЛЬНО вставленных строк —
        повторный вызов с теми же `impact_ids` возвращает 0."""
        ...

    def enqueue_rereview(self, requirement_id: str) -> str | None:
        """Находит `pipeline.items.id` по `pipeline.items.requirement_id`
        (последний по `updated_at`, если их несколько) — НЕ запускает
        `rerun_item` сама (оркестратор ей не передаётся, см. `process_
        changes`), только резолвит `item_id`. `None`, если у требования нет
        айтема Build-конвейера (например, оно из легаси `import-report`) —
        ре-ревью для такого требования технически невозможен."""
        ...

    # ── Задача 41: история изменений (change_history.py) ──────────────────

    def list_change_events_for_requirement(
        self, requirement_id: str
    ) -> list[HistorySourceEvent]:
        """Все `change_events`, связанные с `requirement_id` через
        `requirement_change_impacts` (Задача 40) — вход `change_history.
        build_change_history`. Дублей `change_event_id` быть не может
        (уникальность `(change_event_id, requirement_id)`, см. `save_impacts`);
        порядок — по `created_at` события (хронология для фронта)."""
        ...

    def list_existing_revision_event_ids(self, requirement_id: str) -> set[str]:
        """`requirement_revisions.change_event_id`, уже записанные для этого
        требования, — идемпотентность `build_change_history` (докстринг
        `change_history.py`): событие с уже существующей ревизией
        пропускается, повторный вызов не плодит дублей."""
        ...

    def save_revision(
        self,
        requirement_id: str,
        *,
        change_event_id: str,
        change_note: str | None,
        snapshot: dict,
        created_at: str,
    ) -> str:
        """Вставляет строку `requirement_revisions` — `revision_no` считает
        сам стор (следующий свободный для `requirement_id`, `unique
        (requirement_id, revision_no)` из `20260711120000_initial_schema.sql`).
        `created_at` — ЯВНО переданное значение (`event.effective_date` либо
        `event.created_at`, см. `change_history.build_change_history`), не
        дефолт колонки `now()`: ревизия обязана нести дату СОБЫТИЯ, а не
        момента, когда её досчитал этот скрипт. Возвращает `id` новой строки."""
        ...

    # ── Задача 41: discovery новых актов (discovery.py) ────────────────────

    def list_new_events_without_impacts(self) -> list[ChangeEventRecord]:
        """`change_events(event_type='new')`, уже обработанные Impact-
        маппером (`processed_at is not null`), но БЕЗ ни одного
        `requirement_change_impacts` — «свежий акт, никем не связанный»
        (докстринг `discovery.py`, сужение брифа Задачи 41: вместо
        самостоятельного обхода LegalX используются уже пришедшие webhook-
        события)."""
        ...

    def list_approved_maps(self, jurisdiction: str) -> list[ApprovedMapRecord]:
        """`pipeline.maps(status='approved', jurisdiction=...)` — вход
        discovery: вопросы каждого айтема карты гоняются против нового акта
        события той же юрисдикции."""
        ...

    def is_expected_item_already_covered(self, map_id: str, expected_item: str) -> bool:
        """Есть ли УЖЕ `pipeline.items` с этим `expected_item` под КАКИМ-ЛИБО
        `pipeline.runs` этой карты СО СТАТУСОМ `pending`/`in_progress`/
        `draft_loaded`/`published` — «уже в работе или закрыт», discovery не
        должен заводить дубль-кандидата (Задача 41, фикс-раунд ревью).

        `no_norm`/`needs_attention` НЕ считаются покрытием: это ГЛАВНЫЙ
        сценарий брифа задачи — предыдущий Build-прогон не нашёл нормы (или
        застрял), а новый акт (webhook `event_type='new'`) как раз МОЖЕТ
        закрыть этот пробел. Первая версия метода (`find_existing_discovery_
        item`) блокировала ЛЮБОЙ статус — для уже собранной карты это делало
        discovery вечным no-op, включая ровно тот сценарий, который бриф
        просил ловить; исправлено ревью.

        В схеме `pipeline.*` нет колонки «этот item породило discovery
        события X» (миграция вне периметра этой задачи, см. докстринг
        `discovery.py`), поэтому проверка идёт по паре `(map_id,
        expected_item)` — тот же текст айтема карты, УЖЕ дошедший до
        активного/финального статуса, не даёт второго кандидата; тот же
        текст, застрявший на `no_norm`/`needs_attention`, — даёт."""
        ...

    def create_discovery_run(self, map_id: str) -> str:
        """Новый `pipeline.runs` для карты — «специальный discovery-run»
        (докстринг `discovery.py`), отдельный от обычных прогонов
        `Orchestrator.run_group`, но та же таблица/схема."""
        ...

    def create_discovery_item(
        self, run_id: str, expected_item: str, category_slug: str
    ) -> str:
        """`pipeline.items(status='pending')` — кандидат, дособерёт обычный
        Build; черновой `requirements` здесь НЕ создаётся (докстринг
        `discovery.py`). Возвращает `id` новой строки."""
        ...


# ══════════════════════════════════════════════════════════════════════════
# Путь (б): Classifier-кандидаты
# ══════════════════════════════════════════════════════════════════════════

CANDIDATE_PROFILE = Profile(
    name="monitoring_candidate",  # вне ProfileName Literal в profiles.py — тот
    # же прецедент, что и 'lawyer'/'manager'/'scope'/'rule' в соседних модулях.
    system_prompt=(
        "Ты сравниваешь описание события изменения законодательства со "
        "списком опубликованных требований комплаенс-чеклиста той же "
        "юрисдикции и решаешь, какие из них могут быть затронуты этим "
        "событием. Верни ТОЛЬКО реально вероятные совпадения (не все "
        "подряд) — по каждому укажи requirement_id (СТРОГО из списка "
        "кандидатов, не выдумывай) и score от 0 до 1 (уверенность). Если "
        "ни одно требование не подходит — верни пустой список matches."
    ),
    response_schema={
        "type": "object",
        "properties": {
            "matches": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "requirement_id": {"type": "string"},
                        "score": {"type": "number"},
                    },
                    "required": ["requirement_id", "score"],
                },
            }
        },
        "required": ["matches"],
    },
    tier="cheap",
)


def _candidate_prompt_text(event: ChangeEventRecord, requirements: list[dict]) -> str:
    candidates_text = "\n".join(f"- id={r['id']}: {r['title']}" for r in requirements)
    return (
        f"Событие: {event.event_type} (юрисдикция {event.jurisdiction})\n"
        f"Описание: {event.summary or '(без описания)'}\n\n"
        f"Кандидаты (id: заголовок):\n{candidates_text}"
    )


def _validate_candidate_matches(data: object, valid_ids: set[str]) -> list[dict]:
    """Достаёт валидные `{"requirement_id", "score"}` из ответа Classifier'а
    (путь б), МОЛЧА отбрасывая мусорные записи (не всё сообщение целиком —
    best-effort подсказка, не авторитетная запись, см. докстринг модуля)."""
    if not isinstance(data, dict):
        return []
    matches = data.get("matches")
    if not isinstance(matches, list):
        return []
    result: list[dict] = []
    for m in matches:
        if not isinstance(m, dict):
            continue
        requirement_id = m.get("requirement_id")
        score = m.get("score")
        if not isinstance(requirement_id, str) or requirement_id not in valid_ids:
            continue
        if not isinstance(score, (int, float)) or isinstance(score, bool):
            continue
        result.append({"requirement_id": requirement_id, "score": float(score)})
    return result


def _find_candidates(
    store: MonitoringStore, event: ChangeEventRecord, classifier: Classifier | None
) -> list[MappingCandidate]:
    """Путь (а) — точный, приоритетный: если хоть одно требование нашлось
    по цитатам, путь (б) вообще не запускается (экономия — cheap-вызов LLM
    не нужен, если есть авторитетный ответ)."""
    legalx_act_id = event.legalx_act_id
    if legalx_act_id:
        exact_ids = store.find_requirements_by_citation(legalx_act_id)
        if exact_ids:
            deduped = dict.fromkeys(exact_ids)  # сохраняет порядок, убирает дубли
            return [
                MappingCandidate(requirement_id=rid, method="citation", score=1.0)
                for rid in deduped
            ]

    if classifier is None:
        return []

    requirements = store.list_published_requirements(event.jurisdiction)
    if not requirements:
        return []  # нечего сравнивать — LLM не вызываем вовсе

    try:
        raw = classifier.run(_candidate_prompt_text(event, requirements), CANDIDATE_PROFILE)
    except AgentLLMError:
        return []  # мусорный (не-JSON) ответ — тоже «нет кандидатов», не падаем

    valid_ids = {r["id"] for r in requirements}
    matches = _validate_candidate_matches(raw, valid_ids)
    return [
        MappingCandidate(requirement_id=m["requirement_id"], method="classifier", score=m["score"])
        for m in matches
        if m["score"] >= CANDIDATE_SCORE_THRESHOLD
    ]


# ══════════════════════════════════════════════════════════════════════════
# In-house lawyer (мониторинг)
# ══════════════════════════════════════════════════════════════════════════

LAWYER_MONITORING_PROFILE = Profile(
    name="monitoring_lawyer",
    system_prompt=(
        "Ты — юрист-инхаус, оцениваешь событие изменения источника права "
        "для уже ОПУБЛИКОВАННОГО требования комплаенс-чеклиста. Реши: "
        "требует ли это изменение полной переимплементации карточки "
        "(needs_reimplementation) — и если да, с какого шага Build-"
        "конвейера начинать пересборку (from_step — СТРОГО один из "
        "перечисленных шагов). Если изменение косметическое или не меняет "
        "суть требования — needs_reimplementation=false, from_step=null. "
        "note — краткое обоснование решения, ОБЯЗАТЕЛЬНО непустое."
    ),
    response_schema={
        "type": "object",
        "properties": {
            "needs_reimplementation": {"type": "boolean"},
            "from_step": {"type": ["string", "null"], "enum": [*STEP_ORDER, None]},
            "note": {"type": "string"},
        },
        "required": ["needs_reimplementation", "from_step", "note"],
    },
    tier="expensive",
)


def _validate_lawyer_decision(data: object) -> dict | None:
    """Достаёт `{"needs_reimplementation", "from_step", "note"}` из ответа
    юриста либо `None`, если ответ не проходит контракт: `note` обязана
    быть непустой строкой; `from_step` ОБЯЗАН быть валидным шагом STEP_ORDER
    при `needs_reimplementation=true` и СТРОГО `null` при `false` (код,
    посчитанный из STEP_ORDER, а не мнение LLM — тот же приём, что и
    `status_note`/`_validate_lawyer` в `steps_samples_lawyer.py`)."""
    if not isinstance(data, dict):
        return None
    needs = data.get("needs_reimplementation")
    if not isinstance(needs, bool):
        return None
    note = data.get("note")
    if not isinstance(note, str) or not note:
        return None
    from_step = data.get("from_step")
    if needs:
        if not isinstance(from_step, str) or from_step not in STEP_ORDER:
            return None
    elif from_step is not None:
        return None
    return {"needs_reimplementation": needs, "from_step": from_step, "note": note}


class InHouseLawyer:
    """Юрист-инхаус мониторинга (Задача 40, тир 'expensive', Classifier-
    движок `agents.py`) — см. докстринг модуля («ОТДЕЛЬНАЯ роль от шага
    'lawyer' Build»). БЕЗ Verifier (тот же прецедент, что и у шага 'lawyer'
    Build-конвейера — `docs/miro-agent-flow.csv` не несёт отдельной
    Verifier-колонки для In-house lawyer)."""

    def __init__(
        self,
        llm: AgentLLMClient,
        models: ModelsConfig | None = None,
        *,
        profile: Profile = LAWYER_MONITORING_PROFILE,
        tracer: "Tracer | None" = None,
    ):
        self._models = models or load_models_config()
        self._profile = profile
        self._classifier = Classifier(llm, self._models, tracer=tracer, role="monitoring_lawyer")

    def decide(self, event: ChangeEventRecord, requirement_title: str) -> LawyerDecision:
        """Один ретрай на невалидный ответ (тот же паттерн, что и
        `LawyerStep`/`RuleStep`) — дважды невалидно -> `AgentLLMError`
        наружу (в отличие от Classifier-кандидатов пути (б), решение юриста
        — авторитетное, молча проглатывать мусор здесь нельзя)."""
        text = self._prompt_text(event, requirement_title)
        result = self._extract(text, self._profile)
        if result is None:
            retry_profile = self._make_profile(
                error_message=(
                    "Предыдущий ответ был невалиден: верни СТРОГО JSON "
                    '{"needs_reimplementation": bool, "from_step": str|null, '
                    '"note": непустая строка}; from_step ОБЯЗАН быть одним '
                    f"из {list(STEP_ORDER)} при needs_reimplementation=true "
                    "и строго null при false."
                )
            )
            result = self._extract(text, retry_profile)
        if result is None:
            raise AgentLLMError(
                "InHouseLawyer: дважды вернул невалидный ответ (не "
                "соответствует контракту needs_reimplementation/from_step/note)"
            )
        return LawyerDecision(**result)

    def _extract(self, text: str, profile: Profile) -> dict | None:
        try:
            raw = self._classifier.run(text, profile)
        except AgentLLMError:
            return None
        return _validate_lawyer_decision(raw)

    def _make_profile(self, error_message: str = "") -> Profile:
        system_prompt = self._profile.system_prompt
        if error_message:
            system_prompt = f"{system_prompt}\n\n{error_message}"
        return Profile(
            name=self._profile.name,
            system_prompt=system_prompt,
            response_schema=self._profile.response_schema,
            tier=self._profile.tier,
        )

    @staticmethod
    def _prompt_text(event: ChangeEventRecord, requirement_title: str) -> str:
        return (
            f"Требование: {requirement_title}\n"
            f"Событие изменения источника: {event.event_type} (юрисдикция "
            f"{event.jurisdiction}, вступает в силу "
            f"{event.effective_date or 'не указано'})\n"
            f"Описание события: {event.summary or '(без описания)'}"
        )


# ══════════════════════════════════════════════════════════════════════════
# process_changes — оркестрация (см. докстринг модуля)
# ══════════════════════════════════════════════════════════════════════════


def process_changes(
    store: MonitoringStore,
    *,
    classifier_llm: AgentLLMClient | None = None,
    lawyer: InHouseLawyer | None = None,
    orchestrator: RerunOrchestratorLike | None = None,
    models: ModelsConfig | None = None,
) -> ProcessingReport:
    """Читает необработанные `change_events` и прогоняет каждое через
    дедуп → маппинг → impacts/флаг → In-house lawyer → фан-аут (докстринг
    модуля). Все LLM/оркестратор — опциональные инъекции: без них событие
    без точного цитатного совпадения даёт 0 кандидатов (Classifier не
    вызывается), а найденные impacts флагаются, но ре-ревью не ставится в
    очередь (тот же принцип отсрочки live-подключения, что и везде в Build —
    см. `importer/cli.py`).

    `InHouseLawyer.decide`, упавший на ОДНОМ требовании (`AgentLLMError`),
    НЕ прерывает ни обработку остальных требований этого события, ни
    очередь остальных событий — см. докстринг модуля («Устойчивость к
    ядовитому требованию»): impacts/флаг для этого требования уже
    сохранены и не откатываются, событие в конце всё равно помечается
    `processed_at`, ре-ревью для пропущенного требования — вручную
    (`orchestrator.rerun_item(item_id, from_step)` напрямую)."""
    models = models or load_models_config()
    classifier = (
        Classifier(classifier_llm, models, role="monitoring_candidate")
        if classifier_llm is not None
        else None
    )
    report = ProcessingReport()

    for event in store.list_unprocessed_events():
        report.events_seen += 1

        if store.find_duplicate_processed_event(
            event.legalx_act_id, event.event_type, event.effective_date, event.jurisdiction
        ):
            store.mark_processed(event.id)
            report.duplicates_skipped += 1
            continue

        candidates = _find_candidates(store, event, classifier)
        if not candidates:
            store.mark_processed(event.id)
            report.events_no_candidates += 1
            continue

        requirement_ids = list(dict.fromkeys(c.requirement_id for c in candidates))
        impacts = store.save_impacts(event.id, requirement_ids)
        report.impacts_created += len(impacts)

        titles_by_id = {
            row["id"]: row["title"]
            for row in store.list_published_requirements(event.jurisdiction)
        }

        for requirement_id in requirement_ids:
            store.flag_requirement(requirement_id, event.id)
            report.requirements_flagged += 1

            # Задача 41: история изменений СРАЗУ по свежему impact'у, не
            # отдельным cron'ом — build_change_history сама идемпотентна
            # (пропускает уже записанные change_event_id), поэтому повторный
            # вызов на том же требовании в рамках следующего события — не
            # дублирует уже существующие ревизии, только добавляет новую.
            history_report = build_change_history(store, requirement_id)
            report.revisions_recorded += history_report.revisions_added

            if lawyer is None:
                continue
            title = titles_by_id.get(requirement_id, requirement_id)
            try:
                decision = lawyer.decide(event, title)
            except AgentLLMError as exc:
                # Head-of-line blocking фикс (ревью Задачи 40, Important) —
                # см. докстринг модуля/этой функции: impacts/флаг для
                # requirement_id уже записаны выше и не теряются, просто
                # ре-ревью для НЕГО не ставится в очередь автоматически.
                # Остальные требования и остальные события — как обычно.
                logger.warning(
                    "InHouseLawyer.decide упал на event.id=%s requirement_id=%s: %s",
                    event.id, requirement_id, exc,
                )
                report.lawyer_errors += 1
                continue
            if not decision.needs_reimplementation:
                continue
            item_id = store.enqueue_rereview(requirement_id)
            if item_id is None or orchestrator is None:
                continue
            orchestrator.rerun_item(item_id, decision.from_step)
            report.rereviews_enqueued += 1

        report.notifications_sent += store.fanout_notifications(
            [impact.id for impact in impacts]
        )
        store.mark_processed(event.id)
        report.events_processed += 1

    return report


# ══════════════════════════════════════════════════════════════════════════
# SupabaseMonitoringStore — реальная реализация MonitoringStore поверх
# importer/db.py (паттерн `SupabaseBuildStore`, orchestrator.py)
# ══════════════════════════════════════════════════════════════════════════


def _event_from_row(row: dict) -> ChangeEventRecord:
    return ChangeEventRecord(
        id=row["id"],
        event_type=row["event_type"],
        jurisdiction=row["jurisdiction"],
        effective_date=row.get("effective_date"),
        summary=row.get("summary"),
        payload=row.get("payload") or {},
    )


def _impact_from_row(row: dict) -> ImpactRecord:
    return ImpactRecord(
        id=row["id"],
        change_event_id=row["change_event_id"],
        requirement_id=row["requirement_id"],
        status=row.get("status", "pending_review"),
    )


class SupabaseMonitoringStore:
    """`MonitoringStore` поверх Supabase (паттерн `importer/db.py` /
    `SupabaseBuildStore`). Используется CLI (`importer/cli.py: monitor
    process-changes`); тесты `process_changes` её не гоняют — см.
    `InMemoryMonitoringStore` (`importer/tests/monitoring/stores.py`)."""

    def __init__(self, client):
        self._client = client  # схема public по умолчанию
        self._pipeline = client.schema("pipeline")

    def list_unprocessed_events(self) -> list[ChangeEventRecord]:
        rows = (
            self._client.table("change_events")
            .select("id, event_type, jurisdiction, effective_date, summary, payload")
            .is_("processed_at", "null")
            .order("created_at")
            .execute()
            .data
        )
        return [_event_from_row(row) for row in rows]

    def find_duplicate_processed_event(
        self,
        legalx_act_id: str | None,
        event_type: str,
        effective_date: str | None,
        jurisdiction: str,
    ) -> bool:
        if not legalx_act_id:
            return False
        query = (
            self._client.table("change_events")
            .select("id")
            .eq("event_type", event_type)
            .eq("payload->>act_id", legalx_act_id)
            .eq("jurisdiction", jurisdiction)
            .not_.is_("processed_at", "null")
        )
        query = (
            query.is_("effective_date", "null")
            if effective_date is None
            else query.eq("effective_date", effective_date)
        )
        rows = query.limit(1).execute().data
        return bool(rows)

    def mark_processed(self, event_id: str) -> None:
        self._client.table("change_events").update(
            {"processed_at": datetime.now(timezone.utc).isoformat()}
        ).eq("id", event_id).execute()

    def find_requirements_by_citation(self, legalx_act_id: str) -> list[str]:
        acts = (
            self._client.table("acts").select("id")
            .eq("jurisbase_act_id", legalx_act_id).execute().data
        )
        if not acts:
            return []
        act_ids = [row["id"] for row in acts]

        paragraphs = (
            self._client.table("act_paragraphs").select("id")
            .in_("act_id", act_ids).execute().data
        )
        if not paragraphs:
            return []
        paragraph_ids = [row["id"] for row in paragraphs]

        citations = (
            self._client.table("requirement_citations").select("requirement_id")
            .in_("paragraph_id", paragraph_ids).execute().data
        )
        requirement_ids = list(dict.fromkeys(row["requirement_id"] for row in citations))
        if not requirement_ids:
            return []

        published = (
            self._client.table("requirements").select("id")
            .in_("id", requirement_ids).eq("status", "published").execute().data
        )
        return [row["id"] for row in published]

    def list_published_requirements(self, jurisdiction: str) -> list[dict]:
        """ОДИН запрос с embedded-джойном (`requirement_contents!inner`),
        не `select id` + `in_(ids)` вторым запросом: у юрисдикции UZ уже
        сотни `published`-требований (сиды сигарет/молока/аптеки/кафе) —
        список `ids` во втором запросе ушёл бы в query string GET-запроса и
        на реальном объёме упирается в лимит длины URI PostgREST (проверено
        руками на локальной БД после сида — `414 URI too long`). Embedded-
        фильтр `.eq("requirement_contents.lang", "ru")` фильтрует ВЛОЖЕННЫЙ
        ресурс на стороне PostgREST, `!inner` исключает требования без
        русского `title` (та же семантика, что раньше давал `if rid in
        titles` при двух запросах)."""
        rows = (
            self._client.table("requirements")
            .select("id, requirement_contents!inner(title)")
            .eq("status", "published").eq("jurisdiction", jurisdiction)
            .eq("requirement_contents.lang", "ru")
            .execute().data
        )
        return [
            {"id": row["id"], "title": row["requirement_contents"][0]["title"]}
            for row in rows
            if row.get("requirement_contents")
        ]

    def save_impacts(
        self, change_event_id: str, requirement_ids: list[str]
    ) -> list[ImpactRecord]:
        if not requirement_ids:
            return []
        existing = (
            self._client.table("requirement_change_impacts").select("*")
            .eq("change_event_id", change_event_id)
            .in_("requirement_id", requirement_ids)
            .execute().data
        )
        existing_by_req = {row["requirement_id"]: row for row in existing}
        to_insert = [
            {"change_event_id": change_event_id, "requirement_id": rid}
            for rid in requirement_ids
            if rid not in existing_by_req
        ]
        inserted = (
            self._client.table("requirement_change_impacts").insert(to_insert).execute().data
            if to_insert
            else []
        )
        rows = list(existing_by_req.values()) + inserted
        return [_impact_from_row(row) for row in rows]

    def flag_requirement(self, requirement_id: str, change_event_id: str) -> None:
        self._client.table("requirements").update(
            {
                "review_flag": "flagged_by_change",
                "flagged_at": datetime.now(timezone.utc).isoformat(),
                "flagged_by_event_id": change_event_id,
            }
        ).eq("id", requirement_id).execute()

    def fanout_notifications(self, impact_ids: list[str]) -> int:
        """Джойн-логика (product_type_id/scope-применимость, та же, что у
        `user_deadline_events`) и `ON CONFLICT (user_id, impact_id) DO
        NOTHING` живут в SQL-функции `public.fanout_change_notifications`
        (`20260804120000_change_event_processed.sql`) — тот же принцип, что
        и `process_lifecycle_transitions` (`20260804100000_lifecycle_cron.sql`):
        сложный join через `chosen_products`/`products`/`services` короче и
        надёжнее в SQL, чем N+1 запросов из Python."""
        if not impact_ids:
            return 0
        result = self._client.rpc(
            "fanout_change_notifications", {"p_impact_ids": impact_ids}
        ).execute()
        return result.data or 0

    def enqueue_rereview(self, requirement_id: str) -> str | None:
        rows = (
            self._pipeline.table("items").select("id")
            .eq("requirement_id", requirement_id)
            .order("updated_at", desc=True)
            .limit(1)
            .execute()
            .data
        )
        return rows[0]["id"] if rows else None

    # ── Задача 41: история изменений ────────────────────────────────────────

    def list_change_events_for_requirement(
        self, requirement_id: str
    ) -> list[HistorySourceEvent]:
        impacts = (
            self._client.table("requirement_change_impacts")
            .select("change_event_id")
            .eq("requirement_id", requirement_id)
            .execute()
            .data
        )
        event_ids = list(dict.fromkeys(row["change_event_id"] for row in impacts))
        if not event_ids:
            return []
        rows = (
            self._client.table("change_events")
            .select("id, event_type, effective_date, created_at, summary, title, was_text, now_text")
            .in_("id", event_ids)
            .order("created_at")
            .execute()
            .data
        )
        return [
            HistorySourceEvent(
                change_event_id=row["id"],
                event_type=row["event_type"],
                effective_date=row.get("effective_date"),
                created_at=row["created_at"],
                summary=row.get("summary"),
                title=row["title"],
                was_text=row.get("was_text"),
                now_text=row.get("now_text"),
            )
            for row in rows
        ]

    def list_existing_revision_event_ids(self, requirement_id: str) -> set[str]:
        rows = (
            self._client.table("requirement_revisions")
            .select("change_event_id")
            .eq("requirement_id", requirement_id)
            .execute()
            .data
        )
        return {row["change_event_id"] for row in rows if row.get("change_event_id")}

    def save_revision(
        self,
        requirement_id: str,
        *,
        change_event_id: str,
        change_note: str | None,
        snapshot: dict,
        created_at: str,
    ) -> str:
        existing = (
            self._client.table("requirement_revisions")
            .select("revision_no")
            .eq("requirement_id", requirement_id)
            .order("revision_no", desc=True)
            .limit(1)
            .execute()
            .data
        )
        next_revision_no = (existing[0]["revision_no"] + 1) if existing else 1
        row = (
            self._client.table("requirement_revisions")
            .insert(
                {
                    "requirement_id": requirement_id,
                    "revision_no": next_revision_no,
                    "change_event_id": change_event_id,
                    "change_note": change_note,
                    "snapshot": snapshot,
                    "created_at": created_at,
                }
            )
            .execute()
            .data[0]
        )
        return row["id"]

    # ── Задача 41: discovery новых актов ────────────────────────────────────

    def list_new_events_without_impacts(self) -> list[ChangeEventRecord]:
        rows = (
            self._client.table("change_events")
            .select("id, event_type, jurisdiction, effective_date, summary, payload")
            .eq("event_type", "new")
            .not_.is_("processed_at", "null")
            .order("created_at")
            .execute()
            .data
        )
        if not rows:
            return []
        event_ids = [row["id"] for row in rows]
        impacted = (
            self._client.table("requirement_change_impacts")
            .select("change_event_id")
            .in_("change_event_id", event_ids)
            .execute()
            .data
        )
        impacted_ids = {row["change_event_id"] for row in impacted}
        return [_event_from_row(row) for row in rows if row["id"] not in impacted_ids]

    def list_approved_maps(self, jurisdiction: str) -> list[ApprovedMapRecord]:
        rows = (
            self._pipeline.table("maps")
            .select("id, group_ref, jurisdiction, payload")
            .eq("status", "approved")
            .eq("jurisdiction", jurisdiction)
            .execute()
            .data
        )
        return [
            ApprovedMapRecord(
                id=row["id"],
                group_ref=row["group_ref"],
                jurisdiction=row["jurisdiction"],
                payload=row["payload"],
            )
            for row in rows
        ]

    def is_expected_item_already_covered(self, map_id: str, expected_item: str) -> bool:
        run_rows = (
            self._pipeline.table("runs").select("id").eq("map_id", map_id).execute().data
        )
        run_ids = [row["id"] for row in run_rows]
        if not run_ids:
            return False
        rows = (
            self._pipeline.table("items")
            .select("id")
            .in_("run_id", run_ids)
            .eq("expected_item", expected_item)
            .in_("status", list(DISCOVERY_BLOCKING_STATUSES))
            .limit(1)
            .execute()
            .data
        )
        return bool(rows)

    def create_discovery_run(self, map_id: str) -> str:
        row = self._pipeline.table("runs").insert({"map_id": map_id}).execute().data[0]
        return row["id"]

    def create_discovery_item(self, run_id: str, expected_item: str, category_slug: str) -> str:
        row = (
            self._pipeline.table("items")
            .insert(
                {
                    "run_id": run_id,
                    "expected_item": expected_item,
                    "category_slug": category_slug,
                    "status": "pending",
                }
            )
            .execute()
            .data[0]
        )
        return row["id"]
