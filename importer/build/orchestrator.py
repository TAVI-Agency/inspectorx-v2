"""Оркестратор Build (Задача 14, ADR-0003 решения 2 и 5): детерминированная
state machine поверх `pipeline.items`.

Скелет конвейера — код, не LLM (ADR-0003, решение 2 «гибрид, а не
агент-дирижёр»): `Orchestrator` идёт по `STEP_ORDER` (`steps.py`) строго
последовательно, ретраи и переходы статусов — маршрутизация по коду.
LLM работает только ВНУТРИ шаговых функций (Задачи 17–25), которых в этой
задаче ещё нет — тесты подставляют фейковые `callable`.

Единственный ручной gate конвейера — апрув карты владельцем (стоп-точка ①
глобальных ограничений, `global-constraints.md`): `run_group` отказывается
запускаться по карте в статусе, отличном от `approved`.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Protocol

from importer.build.agents import Verdict
from importer.build.manager import ExceptionManagerLike, NullExceptionManager
from importer.build.steps import (
    STEP_ORDER,
    ItemContext,
    ItemRecord,
    StepFn,
    StepResult,
    get_step,
)

if TYPE_CHECKING:  # без реального импорта на рантайме (цикл с coverage.py) — см. RunReport.coverage
    from importer.build.coverage import CoverageReport

# Сколько ПОДРЯД фейлов одного шага допускается, прежде чем айтем уходит в
# needs_attention. Ретраи не «дожимают» до pass (ADR-0003, решение 4) —
# это верхняя граница попыток одного шага, не число дополнительных ретраев
# сверх первой попытки: 1-й fail → ретрай, 2-й fail → ретрай, 3-й fail (N=3
# подряд) → escalate, к следующему шагу не переходим.
MAX_STEP_RETRIES = 3


class MapNotApprovedError(Exception):
    """`run_group` вызван по карте, чей `status != 'approved'` — стоп-точка
    ① (единственный ручной gate конвейера, ADR-0003 решение 2)."""


class MapAlreadyApprovedError(Exception):
    """`Cartographer.build_map` (Задача 15) вызван повторно на ту же
    `(group_ref, jurisdiction)`, чья карта уже `approved` — `save_map`
    перезаписывает только `draft`; апрувленную карту трогать нельзя,
    новый цикл — явное решение владельца (реджект + новый `build_map`)."""


@dataclass(frozen=True)
class MapRecord:
    """Строка `pipeline.maps`, какой её видит `Orchestrator`."""

    id: str
    group_ref: str
    jurisdiction: str
    status: str
    payload: list[dict]
    approved_at: str | None = None
    approved_by: str | None = None


@dataclass
class RunReport:
    """Итог `run_group`: сколько айтемов куда пришли.

    Задача 27: `published`/`draft_loaded`/`no_norm`/`needs_attention` —
    ФИНАЛЬНЫЙ снимок статусов `pipeline.items` этого прогона (пересчитан из
    стора ПОСЛЕ coverage/публикации, не накопленный по ходу цикла) —
    `draft_loaded` теперь отдельная категория от `published`: конвейер сам
    доводит айтем только до `draft_loaded` (шаг 'load'), а `published` —
    результат `publish_ready` (вызывается автоматически, если
    `run_group(..., publish=True)`, дефолт). `coverage` — приложенный
    coverage-отчёт (`importer/build/coverage.py:CoverageReport`), всегда
    заполнен после `run_group` (coverage считается независимо от `publish`)."""

    run_id: str
    map_id: str
    total_items: int
    published: int = 0
    draft_loaded: int = 0
    no_norm: int = 0
    needs_attention: int = 0
    coverage: "CoverageReport | None" = None


class BuildStore(Protocol):
    """Тонкий интерфейс персистентности поверх `pipeline.*` (схема — Задача
    11). Реальная реализация — `SupabaseBuildStore` ниже, поверх паттерна
    `importer/db.py`; в тестах state machine — `InMemoryStore`
    (`importer/tests/build/test_orchestrator.py`), никакой живой БД."""

    def load_map(self, map_id: str) -> MapRecord: ...

    def save_map(self, group_ref: str, jurisdiction: str, payload: list[dict]) -> str:
        """Cartographer (Задача 15): upsert по уникальному ключу
        `(group_ref, jurisdiction)`. Существующая `draft`-карта
        перезаписывается новым `payload` (тот же `id`); если существующая
        карта уже `approved` — `MapAlreadyApprovedError`, ничего не
        перезаписывается. Отсутствующая строка — обычная вставка новой
        `draft`-карты. Возвращает `id` карты."""
        ...

    def set_map_status(
        self, map_id: str, status: str, *, approved_by: str | None = None
    ) -> MapRecord:
        """CLI `build approve-map` / `build reject-map` (Задача 15):
        `draft -> approved | rejected`. При `status='approved'` заполняет
        `approved_at` (текущее время) и `approved_by`; при `'rejected'` эти
        поля не трогает."""
        ...

    def list_category_slugs(self) -> list[str]:
        """Активные слаги `public.requirement_categories` — ось валидации
        Cartographer (Задача 15): `category_slug` вне этого списка не
        попадает в карту."""
        ...

    def list_group_product_types(self, group_ref: str) -> list[dict]:
        """Типы каталога `catalog.product_types` (ADR-0004), чей код
        (`hs_code` у товаров либо `unspsc_code` у услуг) начинается с
        `group_ref` — кандидаты привязки шага 'scope' (Задача 20): каждый
        элемент `{"id", "hs_code", "unspsc_code", "name_ru"}` (ровно как
        строка таблицы — один из кодов всегда `None`, см. `check` в
        `20260803100000_catalog_schema.sql`). Пустой список — валидный
        исход (у группы пока нет привязанных типов в каталоге), не ошибка."""
        ...

    def create_run(self, map_id: str) -> str: ...

    def create_items(self, run_id: str, payload: list[dict]) -> list[ItemRecord]: ...

    def list_run_item_texts(self, run_id: str) -> list[dict]:
        """Тексты айтемов ПРОГОНА `run_id` для шага 'dedup' (Задача 25,
        `steps_dedup.py`) — сравнение текущего айтема с уже обработанными
        айтемами того же прогона. Каждый элемент — `{"item_id", "text"}`.

        ИНВАРИАНТ (фикс-раунд ревью Задачи 25, Critical): кандидат — ТОЛЬКО
        айтем, чей черновик реально дошёл до записи в БД —
        `status in ('draft_loaded', 'published')`. `pending`/`in_progress`/
        `needs_attention`/`no_norm` — НЕ кандидаты: `Orchestrator.run_group`
        создаёт ВСЕ айтемы прогона одной пачкой ДО цикла обработки
        (`create_items`), поэтому без этого фильтра dedup первого айтема
        видел бы ещё не начатые айтемы 2..N (у них тоже есть `expected_item`)
        и мог бы схлопнуть айтем с тем, что ещё не прошёл конвейер и не будет
        иметь строки `requirements` к моменту шага 'load' — ложная склейка "в
        пустоту". Порядок результата — по `updated_at` (детерминизм «первый
        найденный дубль побеждает» и в `SupabaseBuildStore`, и в
        `InMemoryStore`, где порядок и так стабилен — словарь сохраняет
        порядок вставки).

        `text = coalesce(summary_text, expected_item)` (Задача 27, фикс-раунд
        ревью): `pipeline.items.summary_text` (миграция
        `20260803210000_pipeline_item_summary.sql`) пишет шаг 'summary'
        (`steps_norm.py:SummaryStep`, через `BuildStore.set_item_summary`)
        сразу после успешной верификации саммари. Раньше (до этой миграции)
        колонки под `summary` в БД не было, `SupabaseBuildStore` мог отдать
        только `expected_item` для ВСЕХ айтемов — асимметричное сравнение
        (текущий айтем по `summary`, кандидаты по `expected_item`) срывало
        дедуп парафразов одного требования (см. `docs`/отчёт Задачи 27,
        фикс-раунд ревью, Important №3). Теперь сравнение симметрично:
        айтем без `summary_text` (partial `rerun_item`, начатый не с начала)
        честно фолбэкается на `expected_item` — тот же принцип, что и у
        текущего айтема в `steps_dedup.py:DedupStep._run`."""
        ...

    def update_item_status(
        self,
        item_id: str,
        status: str,
        *,
        last_error: str | None = None,
        requirement_id: str | None = None,
    ) -> ItemRecord:
        """`requirement_id` (Задача 26, шаг 'load') — необязательный kwarg,
        та же обратная совместимость, что и `last_error`: существующие
        вызовы без него продолжают работать, только 'load' привязывает
        айтем к созданному/обновлённому `public.requirements` этим
        параметром."""
        ...

    def bump_retry(self, item_id: str) -> int: ...

    def save_verdicts(self, item_id: str, step: str, verdicts: list[Verdict]) -> None: ...

    def set_item_summary(self, item_id: str, summary: str) -> None:
        """Пишет `pipeline.items.summary_text` (Задача 27, фикс-раунд
        ревью) — вызывается `steps_norm.py:SummaryStep` сразу после
        успешной верификации саммари. Единственный потребитель —
        `list_run_item_texts` (см. её докстринг): позволяет шагу 'dedup'
        сравнивать айтемы СИММЕТРИЧНО (`summary` vs `summary`), не
        `summary` текущего айтема vs `expected_item` кандидатов."""
        ...

    def finish_run(self, run_id: str, status: str) -> None: ...

    # ── Задача 27: coverage/публикация/менеджер исключений ────────────────

    def get_run(self, run_id: str) -> dict:
        """Строка `pipeline.runs` (как минимум `{"map_id", "status"}`) —
        `coverage_report` (`coverage.py`) резолвит по ней `map_id` прогона,
        чтобы сравнить факт (`pipeline.items`) с картой (`pipeline.maps.payload`)."""
        ...

    def list_run_items(self, run_id: str) -> list[ItemRecord]:
        """ВСЕ айтемы прогона `run_id`, ЛЮБОГО статуса (в отличие от
        `list_run_item_texts`, который отдаёт только `draft_loaded`/
        `published` для дедупа) — вход `coverage_report`/`publish_ready`
        (`coverage.py`): карта vs факт обязана видеть и `no_norm`, и
        `needs_attention`, и незавершённые `pending`/`in_progress`, не
        только успешно закрытые айтемы."""
        ...

    def save_coverage_report(self, run_id: str, markdown: str) -> None:
        """Сохраняет markdown coverage-отчёта (`coverage.py:coverage_report`)
        в `pipeline.runs.coverage_report` — переживает процесс, доступен
        `build coverage --run <id>` без пересчёта, если нужно свериться с
        отчётом, который видел оператор во время прогона."""
        ...

    def list_item_verdicts(self, item_id: str) -> list[tuple[str, Verdict]]:
        """ВСЕ вердикты айтема за весь прогон как пары `(step, Verdict)`, В
        ХРОНОЛОГИЧЕСКОМ ПОРЯДКЕ (`pipeline.verdicts` копится append-only,
        `save_verdicts` ничего не удаляет; `SupabaseBuildStore` сортирует по
        `created_at`, `InMemoryStore` — порядок вставки) — вход
        `publish_ready` (`coverage.py`).

        **Фикс-раунд ревью Задачи 27 (Important)**: раньше `publish_ready`
        требовал `passed=True` у КАЖДОГО исторического вердикта — блокировал
        публикацию НАВСЕГДА, если шаг хоть раз провалился и потом прошёл
        ретраем (обычный, штатный путь `Orchestrator._run_from`: fail →
        retry → pass). Теперь `list_item_verdicts` отдаёт `step` вместе с
        `Verdict` именно для того, чтобы `publish_ready` мог взять ПОСЛЕДНИЙ
        по времени вердикт КАЖДОГО шага (не всю историю) — см. докстринг
        `coverage.py:publish_ready`."""
        ...

    def publish_requirement(self, requirement_id: str) -> None:
        """`publish_ready` (`coverage.py`): `public.requirements.status ->
        'published'`, `published_at -> now()`. Публикация НЕ идёт через
        `save_requirement_draft` (тот пишет `status` ровно как в карточке,
        а Assembler всегда кладёт `'draft'`, см. `steps_load.py`) — это
        отдельное, явное действие, которое дёргает только `publish_ready`
        (и транзитивно — `build publish` CLI), никогда сам конвейер шагов."""
        ...

    # ── Задача 26: Assembler/Load ────────────────────────────────────────

    def find_or_create_authority(self, name: str) -> str:
        """Резолвит `authority_name` (текст, который вернул Assembler) в
        `authorities.id` — по `name_ru`, вставляя новую строку, если такого
        ведомства ещё нет. Шаг 'load' (`steps_load.py`) вызывает это ПЕРЕД
        `save_requirement_draft`, т.к. `requirements.authority_id` — FK, не
        текстовое поле."""
        ...

    def set_item_note(self, item_id: str, note: str) -> None:
        """Пишет `note` в `pipeline.items.last_error` БЕЗ смены статуса —
        отдельно от `update_item_status(..., last_error=...)`, потому что
        это не диагностика провала последней попытки шага, а постоянная
        пометка айтема (сейчас единственное применение — 'load' помечает
        дубль `'duplicate_of=<id>'` перед переводом в `draft_loaded`, см.
        `steps_load.py`)."""
        ...

    def save_requirement_draft(self, card: dict, *, item_id: str) -> str:
        """Пишет карточку, собранную Assembler'ом (`assembler.py:
        AssembleStep._build_card`), в БД: upsert `public.requirements` по
        `card['requirement']['external_key']`, затем ПОЛНАЯ замена строк
        `requirement_contents`/`requirement_details`/
        `requirement_applicability`/`requirement_rules` этого требования
        (replace-семантика — не merge построчно, см. докстринг
        `steps_load.py`). `card['citations']` НЕ используется — известный
        пробел (нет ETL LegalX-фрагмент -> локальный `act_paragraphs`, см.
        докстринг `assembler.py`). Возвращает `requirements.id`.

        **Фикс-раунд ревью Задачи 26 (Important)**: `card['requirement']
        ['status']` от Assembler'а ВСЕГДА `'draft'` — но апсерт может
        попасть в УЖЕ `published` строку (повторный `load` того же
        `external_key` после публикации — ре-ревью флоу, Задача 27+). Если
        существующая строка `status == 'published'`, этот метод НЕ
        перезаписывает статус (контент — обновляется как обычно, публикацию
        откатывать нельзя без явного ревью выше по потоку) и пишет пометку
        через `set_item_note(item_id, ...)` — `item_id` поэтому обязательный
        параметр этого метода, не опциональный."""
        ...


def escalate(item: ItemRecord, reason: str, store: BuildStore) -> None:
    """Пишет `reason` в `last_error` и переводит айтем в `needs_attention` —
    ветка «эскалация владельцу» решения менеджера исключений
    (`manager.py:ExceptionManagerLike`, действие `'escalate_owner'`).

    Раньше (до Задачи 27) это была единственная реакция `Orchestrator` на
    исчерпанные ретраи шага; теперь — один из двух исходов
    `Orchestrator._handle_exhausted_retries` (второй — `retry_reformulated`,
    ОДНА дополнительная попытка шага перед эскалацией). Остаётся отдельной
    функцией модуля (не методом) — используется и напрямую (см.
    `test_orchestrator.py:test_escalate_writes_reason_to_last_error_and_sets_needs_attention`),
    и внутри `_handle_exhausted_retries`."""
    store.update_item_status(item.id, "needs_attention", last_error=reason)


class Orchestrator:
    def __init__(
        self,
        store: BuildStore,
        steps: dict[str, StepFn] | None = None,
        manager: ExceptionManagerLike | None = None,
    ):
        self._store = store
        # None -> берём шаги из глобального реестра steps.py (реальный
        # прогон); в тестах передаётся словарь фейковых callable напрямую,
        # реестр вообще не трогается.
        self._steps = steps
        # None -> NullExceptionManager (Задача 27): не трогает LLM, решение
        # всегда 'escalate_owner' — ровно старое поведение до менеджера
        # исключений, чтобы существующие вызовы без manager= не заметили
        # разницы (см. docstring NullExceptionManager в manager.py).
        self._manager: ExceptionManagerLike = manager or NullExceptionManager()

    def run_group(self, map_id: str, *, publish: bool = True) -> RunReport:
        """Прогоняет все айтемы утверждённой карты по STEP_ORDER, затем
        (Задача 27, порядок зафиксирован фикс-раундом ревью, Important №2):
        1) если `publish=True` (дефолт) — публикует чистые `draft_loaded`-
           айтемы (`coverage.publish_ready`) — публикация идёт ПЕРЕД coverage,
           а не после;
        2) считает coverage-отчёт (`coverage.coverage_report`, с менеджером
           исключений на найденных пробелах) и сохраняет его.

        Почему publish ПЕРЕД coverage, не наоборот: coverage — «снимок
        состояния прогона для оператора» — обязан отражать ФИНАЛЬНЫЕ статусы,
        а не промежуточные. Если считать coverage ДО публикации, айтем,
        которого `publish_ready` в ЭТОТ ЖЕ вызов демотирует в
        `needs_attention` (последний вердикт хотя бы одного шага — fail, см.
        `coverage.publish_ready`), в отчёте попал бы в «closed» — устаревший
        снимок, ещё до того, как отчёт вообще показан оператору. При старом
        порядке (coverage до publish) это давало РОВНО такое расхождение —
        зафиксировано регрессионным тестом
        `test_run_group_publish_before_coverage_reflects_final_demotion_status`.

        Айтемы, которые менеджер исключений посоветовал ретраить
        (`retry_reformulated`) уже НА ЭТАПЕ coverage (не на этапе ретраев
        самого шага — это другая, более ранняя точка вызова, см.
        `_handle_exhausted_retries`) — coverage их НЕ перезапускает и не
        публикует сама (докстринг `manager.py`/`coverage.py`: менеджер в
        coverage только советует). Починка такого айтема — `rerun_item` (вне
        `run_group`) с последующим ЯВНЫМ `build publish --run <id>`, не
        автоматика внутри этого вызова.

        Карта в статусе, отличном от 'approved', — стоп-точка ①:
        `MapNotApprovedError` ДО создания run/items (ничего не пишется в БД
        по неапрувленной карте)."""
        map_record = self._store.load_map(map_id)
        if map_record.status != "approved":
            raise MapNotApprovedError(
                f"Карта {map_id} не апрувнута (status={map_record.status!r}) — "
                "стоп-точка ①: сначала апрув владельцем"
            )
        run_id = self._store.create_run(map_id)
        items = self._store.create_items(run_id, map_record.payload)

        for item in items:
            item = self._store.update_item_status(item.id, "in_progress")
            ctx = ItemContext(item=item)
            self._run_from(ctx, start_index=0)

        self._store.finish_run(run_id, "done")

        # Локальный импорт — coverage.py импортирует BuildStore ИЗ этого
        # модуля на уровне модуля; импорт на верхнем уровне orchestrator.py
        # создал бы цикл.
        from importer.build.coverage import coverage_report, publish_ready

        if publish:
            publish_ready(self._store, run_id)

        # coverage — ПОСЛЕДНИЙ шаг: считается уже по финальным статусам
        # (после публикации, если она была) — источник истины для отчёта.
        coverage = coverage_report(self._store, run_id, manager=self._manager)
        self._store.save_coverage_report(run_id, coverage.markdown)

        return RunReport(
            run_id=run_id,
            map_id=map_id,
            total_items=len(items),
            coverage=coverage,
            **self._final_status_counts(run_id),
        )

    def _final_status_counts(self, run_id: str) -> dict[str, int]:
        """Пересчитывает published/draft_loaded/no_norm/needs_attention ИЗ
        стора ПОСЛЕ coverage/публикации — источник истины один (реальные
        статусы `pipeline.items`), не ручная бухгалтерия по ходу цикла: она
        разъехалась бы с фактом, как только `publish_ready` меняет статус
        айтема уже ПОСЛЕ того, как per-item цикл его протолкнул."""
        counts = {"published": 0, "draft_loaded": 0, "no_norm": 0, "needs_attention": 0}
        for item in self._store.list_run_items(run_id):
            if item.status in counts:
                counts[item.status] += 1
        return counts

    def rerun_item(self, item_id: str, from_step: str) -> None:
        """Частичный Build для контура C: сбрасывает статус айтема в
        'in_progress' и гонит шаги STEP_ORDER, начиная с `from_step`."""
        if from_step not in STEP_ORDER:
            raise ValueError(
                f"Неизвестный шаг {from_step!r} — ожидается один из {STEP_ORDER}"
            )
        item = self._store.update_item_status(item_id, "in_progress")
        ctx = ItemContext(item=item)
        self._run_from(ctx, start_index=STEP_ORDER.index(from_step))

    # ── внутреннее ───────────────────────────────────────────────────────

    def _step(self, name: str) -> StepFn:
        if self._steps is not None:
            try:
                return self._steps[name]
            except KeyError as exc:
                raise KeyError(
                    f"Шаг {name!r} не передан в Orchestrator(steps=...)"
                ) from exc
        return get_step(name)

    @staticmethod
    def _call_step(step_fn: StepFn, step_name: str, ctx: ItemContext) -> StepResult:
        """Вызывает `step_fn(ctx)` со страховкой от НЕОЖИДАННЫХ исключений
        (фикс-раунд ревью Задачи 20): каждая шаговая функция уже ловит свои
        ожидаемые типы сама (`AgentLLMError`/`ValueError` — см. докстринги
        `steps_norm.py`/`steps_classify.py`/`steps_rule.py`/
        `steps_scope_lifecycle.py`), но это дисциплина конкретного шага, а не
        гарантия интерфейса `StepFn`. Что угодно ещё — например,
        `postgrest.APIError` у `SupabaseBuildStore` внутри шага, который сам
        стучится в БД (`ScopeStep.list_group_product_types`) — раньше долетало
        сюда необработанным и роняло ВЕСЬ `run_group` (все айтемы прогона), а
        не только текущий шаг текущего айтема. Здесь — последний рубеж:
        `Exception` превращается в обычный `StepResult(fail)`, дальше по коду
        идёт обычный путь retry/эскалации (`MAX_STEP_RETRIES`), как и любой
        другой fail."""
        try:
            return step_fn(ctx)
        except Exception as exc:  # noqa: BLE001 — намеренно широкий catch, см. докстринг
            return StepResult(
                status="fail",
                error=f"unhandled exception in step {step_name!r}: {exc}",
            )

    def _run_from(self, ctx: ItemContext, start_index: int) -> str:
        """Гонит `ctx.item` по STEP_ORDER начиная с `start_index`. Возвращает
        терминальный статус: 'draft_loaded' | 'no_norm' | 'needs_attention'.

        Задача 27: раньше конвейер по завершении STEP_ORDER безусловно писал
        `'published'` — это конфликтовало с публикацией по вердиктам
        (`coverage.publish_ready`): шаг 'load' уже пишет `'draft_loaded'`
        сам (`steps_load.py`), и Orchestrator НЕ обязан переопределять его в
        `'published'` — терминальный статус конвейера теперь `'draft_loaded'`,
        публикация — отдельный, ЯВНЫЙ шаг поверх (`run_group`)."""
        for step_name in STEP_ORDER[start_index:]:
            step_fn = self._step(step_name)
            consecutive_fails = 0
            fail_history: list[str] = []  # причины ВСЕХ провалов ЭТОГО шага подряд, не только последней
            while True:
                result = self._call_step(step_fn, step_name, ctx)
                if result.verdicts:
                    self._store.save_verdicts(ctx.item.id, step_name, result.verdicts)

                status = result.status
                error = result.error
                if status == "no_norm" and step_name != "norm":
                    # no_norm легален ТОЛЬКО от шага 'norm' (решение
                    # контроллера) — от любого другого шага это ошибка
                    # контракта степ-функции, не валидный терминальный исход.
                    # Трактуем как обычный fail — идёт в retry/эскалацию.
                    status = "fail"
                    error = f"шаг {step_name!r} вернул no_norm — только 'norm' может"

                if status == "ok":
                    break

                if status == "no_norm":
                    # Терминальный валидный исход (только от 'norm') —
                    # остальные шаги пропускаются.
                    self._store.update_item_status(ctx.item.id, "no_norm")
                    return "no_norm"

                # status == "fail"
                consecutive_fails += 1
                reason = error or (
                    f"шаг {step_name!r}: провал попытки {consecutive_fails}"
                )
                fail_history.append(reason)
                if consecutive_fails >= MAX_STEP_RETRIES:
                    outcome = self._handle_exhausted_retries(
                        step_fn, step_name, ctx, reason, fail_history
                    )
                    if outcome is None:
                        break  # доп. попытка менеджера удалась — к следующему шагу
                    return outcome  # 'no_norm' | 'needs_attention'
                self._store.bump_retry(ctx.item.id)
                # тот же шаг — ретрай (while продолжается)

        self._store.update_item_status(ctx.item.id, "draft_loaded")
        return "draft_loaded"

    def _handle_exhausted_retries(
        self,
        step_fn: StepFn,
        step_name: str,
        ctx: ItemContext,
        reason: str,
        fail_history: list[str],
    ) -> str | None:
        """Вызывается РОВНО один раз на исчерпанные `MAX_STEP_RETRIES` подряд
        фейлы шага (решение контроллера Задачи 27: менеджер исключений
        вызывается «ТОЛЬКО при N подряд фейлов»). Спрашивает
        `self._manager.review(ctx.item, fail_history)` — `fail_history`
        (Minor фикс-раунда ревью) несёт причины ВСЕХ `MAX_STEP_RETRIES`
        провалов подряд этого шага, не только последнего: менеджеру нужен
        весь ход попыток, чтобы отличить «один и тот же провал N раз» от
        «разные причины на каждой попытке» — по одной последней причине
        этого не увидеть.

        - `'retry_reformulated'` -> кладёт `note` в `ctx.data['manager_note']`
          и делает РОВНО ОДНУ дополнительную попытку того же шага (менеджер
          НЕ спрашивается снова, даже если и эта попытка провалится —
          иначе никакой верхней границы попыток бы не было). Успех ->
          `None` (сигнал вызывающему коду: `break`, идти к следующему шагу
          STEP_ORDER как обычно). `no_norm`/`fail` доп. попытки -> тот же
          терминальный исход, что и у обычного исчерпания (`no_norm` для
          шага 'norm', иначе `escalate`);
        - `'escalate_owner'` (или любое иное/невалидное действие —
          консервативный дефолт) -> `escalate(ctx.item, reason, store)`, ровно
          как до Задачи 27.

        Менеджер НЕ публикует (докстринг `manager.py`) — здесь только выбор
        между доп. попыткой и эскалацией."""
        decision = self._manager.review(ctx.item, fail_history)
        if decision.get("action") != "retry_reformulated":
            escalate(ctx.item, reason, self._store)
            return "needs_attention"

        ctx.data["manager_note"] = decision.get("note")
        retry_result = self._call_step(step_fn, step_name, ctx)
        if retry_result.verdicts:
            self._store.save_verdicts(ctx.item.id, step_name, retry_result.verdicts)

        retry_status = retry_result.status
        retry_error = retry_result.error
        if retry_status == "no_norm" and step_name != "norm":
            retry_status = "fail"
            retry_error = f"шаг {step_name!r} вернул no_norm — только 'norm' может"

        if retry_status == "ok":
            return None
        if retry_status == "no_norm":
            self._store.update_item_status(ctx.item.id, "no_norm")
            return "no_norm"

        # Доп. попытка менеджера тоже провалилась — эскалация владельцу,
        # менеджер второй раз не спрашивается.
        escalate(ctx.item, retry_error or reason, self._store)
        return "needs_attention"


# ============================================================================
# SupabaseBuildStore — реальная реализация BuildStore поверх importer/db.py
# ============================================================================


def _map_from_row(row: dict) -> MapRecord:
    return MapRecord(
        id=row["id"],
        group_ref=row["group_ref"],
        jurisdiction=row["jurisdiction"],
        status=row["status"],
        payload=row["payload"],
        approved_at=row.get("approved_at"),
        approved_by=row.get("approved_by"),
    )


def _item_from_row(row: dict) -> ItemRecord:
    return ItemRecord(
        id=row["id"],
        run_id=row["run_id"],
        expected_item=row["expected_item"],
        category_slug=row.get("category_slug"),
        requirement_id=row.get("requirement_id"),
        status=row.get("status", "pending"),
        retry_count=row.get("retry_count", 0),
        last_error=row.get("last_error"),
        summary_text=row.get("summary_text"),
    )


class SupabaseBuildStore:
    """`BuildStore` поверх Supabase (паттерн `importer/db.py`, схема
    `pipeline` из Задачи 11). Используется CLI (`importer/cli.py`); тесты
    state machine её не гоняют — см. `InMemoryStore` в
    `importer/tests/build/test_orchestrator.py`."""

    def __init__(self, client):
        self._client = client  # схема public по умолчанию — requirement_categories
        self._db = client.schema("pipeline")

    def load_map(self, map_id: str) -> MapRecord:
        rows = self._db.table("maps").select("*").eq("id", map_id).execute().data
        if not rows:
            raise ValueError(f"Карта {map_id} не найдена в pipeline.maps")
        return _map_from_row(rows[0])

    def save_map(self, group_ref: str, jurisdiction: str, payload: list[dict]) -> str:
        existing = (
            self._db.table("maps").select("id, status")
            .eq("group_ref", group_ref).eq("jurisdiction", jurisdiction)
            .execute().data
        )
        if existing:
            row = existing[0]
            if row["status"] == "approved":
                raise MapAlreadyApprovedError(
                    f"Карта {group_ref}/{jurisdiction} (id={row['id']}) уже approved — "
                    "повторный build_map запрещён, см. Cartographer (Задача 15)"
                )
            updated = (
                self._db.table("maps")
                .update({"payload": payload, "status": "draft"})
                .eq("id", row["id"]).execute().data[0]
            )
            return updated["id"]
        inserted = (
            self._db.table("maps")
            .insert({
                "group_ref": group_ref,
                "jurisdiction": jurisdiction,
                "payload": payload,
                "status": "draft",
            })
            .execute().data[0]
        )
        return inserted["id"]

    def set_map_status(
        self, map_id: str, status: str, *, approved_by: str | None = None
    ) -> MapRecord:
        patch: dict = {"status": status}
        if status == "approved":
            patch["approved_at"] = datetime.now(timezone.utc).isoformat()
            patch["approved_by"] = approved_by
        row = self._db.table("maps").update(patch).eq("id", map_id).execute().data[0]
        return _map_from_row(row)

    def list_category_slugs(self) -> list[str]:
        rows = (
            self._client.table("requirement_categories")
            .select("slug").eq("is_active", True).execute().data
        )
        return [row["slug"] for row in rows]

    def list_group_product_types(self, group_ref: str) -> list[dict]:
        rows = (
            self._client.schema("catalog").table("product_types")
            .select("id, hs_code, unspsc_code, name_ru")
            .or_(f"hs_code.like.{group_ref}%,unspsc_code.like.{group_ref}%")
            .execute().data
        )
        return rows

    def create_run(self, map_id: str) -> str:
        row = self._db.table("runs").insert({"map_id": map_id}).execute().data[0]
        return row["id"]

    def create_items(self, run_id: str, payload: list[dict]) -> list[ItemRecord]:
        rows_to_insert = [
            {
                "run_id": run_id,
                "expected_item": entry["expected_item"],
                "category_slug": entry.get("category_slug"),
            }
            for entry in payload
        ]
        rows = self._db.table("items").insert(rows_to_insert).execute().data
        return [_item_from_row(row) for row in rows]

    def list_run_item_texts(self, run_id: str) -> list[dict]:
        """См. докстринг `BuildStore.list_run_item_texts` — `text =
        coalesce(summary_text, expected_item)` (Задача 27, фикс-раунд ревью:
        симметричное сравнение summary-vs-summary для dedup, не
        summary-vs-expected_item). Фильтр `status in ('draft_loaded',
        'published')` (Critical фикс-раунда ревью Задачи 25) —
        `pending`/`in_progress`/`needs_attention`/`no_norm` не кандидаты,
        черновика в БД у них ещё (или уже никогда) не будет. `order("updated_at")`
        — детерминизм «первый найденный дубль побеждает» (Minor того же
        ревью)."""
        rows = (
            self._db.table("items").select("id, expected_item, summary_text")
            .eq("run_id", run_id)
            .in_("status", ["draft_loaded", "published"])
            .order("updated_at")
            .execute().data
        )
        return [
            {"item_id": row["id"], "text": row.get("summary_text") or row["expected_item"]}
            for row in rows
        ]

    def set_item_summary(self, item_id: str, summary: str) -> None:
        self._db.table("items").update({"summary_text": summary}).eq("id", item_id).execute()

    def update_item_status(
        self,
        item_id: str,
        status: str,
        *,
        last_error: str | None = None,
        requirement_id: str | None = None,
    ) -> ItemRecord:
        patch: dict = {"status": status}
        if last_error is not None:
            patch["last_error"] = last_error
        if requirement_id is not None:
            patch["requirement_id"] = requirement_id
        row = self._db.table("items").update(patch).eq("id", item_id).execute().data[0]
        return _item_from_row(row)

    def bump_retry(self, item_id: str) -> int:
        row = self._db.table("items").select("retry_count").eq("id", item_id).execute().data[0]
        new_count = row["retry_count"] + 1
        self._db.table("items").update({"retry_count": new_count}).eq("id", item_id).execute()
        return new_count

    def save_verdicts(self, item_id: str, step: str, verdicts: list[Verdict]) -> None:
        if not verdicts:
            return
        rows = [
            {
                "item_id": item_id,
                "step": step,
                "verdict": "pass" if v.passed else "fail",
                "reason": v.reason,
                "model": v.model,
            }
            for v in verdicts
        ]
        self._db.table("verdicts").insert(rows).execute()

    def finish_run(self, run_id: str, status: str) -> None:
        self._db.table("runs").update(
            {"status": status, "finished_at": datetime.now(timezone.utc).isoformat()}
        ).eq("id", run_id).execute()

    # ── Задача 27: coverage/публикация/менеджер исключений ─────────────────

    def get_run(self, run_id: str) -> dict:
        rows = self._db.table("runs").select("*").eq("id", run_id).execute().data
        if not rows:
            raise ValueError(f"Прогон {run_id} не найден в pipeline.runs")
        return rows[0]

    def list_run_items(self, run_id: str) -> list[ItemRecord]:
        rows = self._db.table("items").select("*").eq("run_id", run_id).execute().data
        return [_item_from_row(row) for row in rows]

    def save_coverage_report(self, run_id: str, markdown: str) -> None:
        self._db.table("runs").update({"coverage_report": markdown}).eq("id", run_id).execute()

    def list_item_verdicts(self, item_id: str) -> list[tuple[str, Verdict]]:
        rows = (
            self._db.table("verdicts").select("*").eq("item_id", item_id)
            .order("created_at").execute().data
        )
        return [
            (
                row["step"],
                Verdict(passed=row["verdict"] == "pass", reason=row.get("reason") or "", model=row.get("model") or ""),
            )
            for row in rows
        ]

    def publish_requirement(self, requirement_id: str) -> None:
        self._client.table("requirements").update({
            "status": "published",
            "published_at": datetime.now(timezone.utc).isoformat(),
        }).eq("id", requirement_id).execute()

    # ── Задача 26: Assembler/Load ─────────────────────────────────────────

    def find_or_create_authority(self, name: str) -> str:
        existing = (
            self._client.table("authorities").select("id")
            .eq("name_ru", name).execute().data
        )
        if existing:
            return existing[0]["id"]
        inserted = (
            self._client.table("authorities").insert({"name_ru": name}).execute().data[0]
        )
        return inserted["id"]

    def set_item_note(self, item_id: str, note: str) -> None:
        self._db.table("items").update({"last_error": note}).eq("id", item_id).execute()

    def save_requirement_draft(self, card: dict, *, item_id: str) -> str:
        requirement = dict(card["requirement"])
        external_key = requirement.get("external_key")

        existing = []
        if external_key:
            existing = (
                self._client.table("requirements").select("id, status")
                .eq("external_key", external_key).execute().data
            )
        if existing:
            requirement_id = existing[0]["id"]
            if existing[0]["status"] == "published":
                # published сохраняется — контент обновляем, статус не
                # трогаем (докстринг Protocol.save_requirement_draft).
                requirement = {**requirement, "status": "published"}
                self.set_item_note(item_id, "existing published, status preserved")
            self._client.table("requirements").update(requirement).eq(
                "id", requirement_id
            ).execute()
        else:
            inserted = self._client.table("requirements").insert(requirement).execute().data[0]
            requirement_id = inserted["id"]

        # replace-семантика (докстринг steps_load.py): удаляем старый набор
        # строк требования, затем вставляем актуальный из card.
        self._client.table("requirement_contents").delete().eq(
            "requirement_id", requirement_id
        ).execute()
        contents_rows = [
            {**row, "requirement_id": requirement_id, "lang": lang}
            for lang, row in (card.get("contents") or {}).items()
        ]
        if contents_rows:
            self._client.table("requirement_contents").insert(contents_rows).execute()

        self._client.table("requirement_details").delete().eq(
            "requirement_id", requirement_id
        ).execute()
        details_rows = [
            {**row, "requirement_id": requirement_id, "lang": lang}
            for lang, row in (card.get("details") or {}).items()
        ]
        if details_rows:
            self._client.table("requirement_details").insert(details_rows).execute()

        self._client.table("requirement_applicability").delete().eq(
            "requirement_id", requirement_id
        ).execute()
        applicability = card.get("applicability")
        if applicability:
            self._client.table("requirement_applicability").insert(
                {**applicability, "requirement_id": requirement_id}
            ).execute()

        self._client.table("requirement_rules").delete().eq(
            "requirement_id", requirement_id
        ).execute()
        rules = card.get("rules") or []
        if rules:
            rule_rows = [
                {
                    "requirement_id": requirement_id,
                    "rule": r["rule"],
                    "verified": r["verified"],
                }
                for r in rules
            ]
            self._client.table("requirement_rules").insert(rule_rows).execute()

        return requirement_id

    # ── доп. запросы для CLI (вне BuildStore Protocol, нужны только `build
    # status` / `build attention`) ─────────────────────────────────────────

    def run_summary(self, run_id: str) -> dict[str, int]:
        rows = self._db.table("items").select("status").eq("run_id", run_id).execute().data
        summary: dict[str, int] = {}
        for row in rows:
            summary[row["status"]] = summary.get(row["status"], 0) + 1
        return summary

    def list_needs_attention(self) -> list[ItemRecord]:
        rows = self._db.table("items").select("*").eq("status", "needs_attention").execute().data
        return [_item_from_row(row) for row in rows]
