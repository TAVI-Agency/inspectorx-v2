"""Coverage checker + автопубликация (Задача 27, ADR-0003 «Блок 2», финал
блока: сквозная сшивка конвейера).

## `coverage_report` — RUN-level, не per-item шаг `STEP_ORDER`

Раньше 'coverage' был последним элементом `STEP_ORDER` (Задачи 14–26), но
семантически это не шаг одного айтема, а сверка ВСЕГО прогона: карта
(`pipeline.maps.payload`, что должно получиться) против факта
(`pipeline.items` этого прогона — что реально получилось). Задача 27 убрала
его из `STEP_ORDER` (`steps.py`) и превратила в эту run-level функцию,
которую `Orchestrator.run_group` (`orchestrator.py`) зовёт ПОСЛЕ цикла по
айтемам, плюс отдельная CLI-команда `build coverage --run <id>`
(`importer/cli.py`) — для восстановления отчёта по уже завершённому прогону.

Категории (решение контроллера задачи):
- **closed** — `published`/`draft_loaded`: айтем реально дошёл до карточки
  в БД (опубликованной или ждущей публикации);
- **no_norm** — терминальный валидный исход шага 'norm' (норма не найдена
  ни разу — не ошибка, а честный «нормы нет»);
- **needs_attention** — эскалация после `MAX_STEP_RETRIES` подряд фейлов
  шага (через менеджера исключений — `manager.py`, `orchestrator.py`);
- **pending** — айтем ещё не дошёл до терминального статуса
  (`pending`/`in_progress`, а также любой ДРУГОЙ неизвестный статус —
  консервативный дефолт, не молчим на новом значении enum). Штатно пуст
  после нормального завершения `run_group` (цикл айтемов доводит КАЖДЫЙ
  айтем до терминального статуса перед следующим) — непустой `pending`
  сигналит о прогоне, оборвавшемся на середине.

## Менеджер исключений в coverage — только советует

Для каждого `needs_attention`-пробела, если `coverage_report` вызван с
`manager=`, менеджер (`manager.py`) даёт совет (`retry_reformulated` /
`escalate_owner`) — попадает в `CoverageGap.manager_suggestion` и в
markdown-отчёт. Coverage НИЧЕГО не перезапускает и не публикует сама — это
чисто информативная сверка (см. докстринг `manager.py`).

## `publish_ready` — публикация по ПОСЛЕДНЕМУ вердикту каждого шага

**Фикс-раунд ревью Задачи 27 (Important)**: первая версия требовала
`passed=True` у КАЖДОГО исторического вердикта айтема — это блокировало
публикацию НАВСЕГДА, стоило хоть одному шагу провалиться на первой попытке
и пройти вторым/третьим ретраем (обычный, штатный путь
`Orchestrator._run_from`: fail → retry → pass — `pipeline.verdicts` копится
append-only, старый провалившийся вердикт остаётся в таблице НАВСЕГДА, даже
после успешного ретрая). Продуктовое решение контроллера: «нерешённый fail»
— это ПОСЛЕДНИЙ по времени вердикт ДАННОГО ШАГА, а не любой исторический.

Реализация: `store.list_item_verdicts(item_id)` отдаёт `[(step, Verdict), ...]`
в хронологическом порядке; группируем по `step`, для каждого шага берём
ПОСЛЕДНИЙ вердикт (более поздний перезаписывает более ранний в `dict`
однопроходным циклом) — публикация идёт, только если ПОСЛЕДНИЙ вердикт
КАЖДОГО шага `passed=True`. Шаги без единого вердикта вообще (Verifier ни
разу не вызывался — например, 'scope'/'lawyer' не имеют Verifier по
дизайну) в группировку не попадают — вакуально «pass» для НИХ, но не
маскируют fail других шагов.

Хотя бы один шаг, чей ПОСЛЕДНИЙ вердикт — fail: требование остаётся
`draft`, айтем эскалируется в `needs_attention` (публикация не идёт,
обычный цикл ре-ревью — `rerun_item` — подхватит его позже). Айтем без
`requirement_id` (дедуп-дубль, `steps_load.py` DEDUP-скип — см. докстринг
`steps_load.py`) — публиковать нечего (нет своей строки `requirements`), но
сам айтем всё равно помечается `published` как терминальная отметка «айтем
дошёл до конца, дальше делать нечего» (dedup-дубль и так смердился в
канонический item отдельной строкой).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from importer.build.agents import Verdict
from importer.build.manager import ExceptionManagerLike
from importer.build.orchestrator import BuildStore
from importer.build.steps import ItemRecord

_CLOSED_STATUSES = ("published", "draft_loaded")
_PENDING_STATUSES = ("pending", "in_progress")


@dataclass
class CoverageGap:
    """Один пробел в покрытии — `needs_attention`-айтем (кандидат для
    менеджера исключений/владельца)."""

    item_id: str
    expected_item: str
    last_error: str | None
    manager_suggestion: dict | None = None


@dataclass
class CoverageReport:
    run_id: str
    map_id: str
    total_expected: int
    total_actual: int
    closed: int
    no_norm: int
    needs_attention: int
    pending: int
    gaps: list[CoverageGap] = field(default_factory=list)
    markdown: str = ""


def _classify(items: list[ItemRecord]) -> dict[str, list[ItemRecord]]:
    buckets: dict[str, list[ItemRecord]] = {
        "closed": [], "no_norm": [], "needs_attention": [], "pending": [],
    }
    for item in items:
        if item.status in _CLOSED_STATUSES:
            buckets["closed"].append(item)
        elif item.status == "no_norm":
            buckets["no_norm"].append(item)
        elif item.status == "needs_attention":
            buckets["needs_attention"].append(item)
        else:
            # 'pending'/'in_progress' — штатный «ещё не завершился»; любой
            # ДРУГОЙ статус здесь тоже консервативно пробел, а не молчаливая
            # потеря айтема из отчёта (докстринг модуля).
            buckets["pending"].append(item)
    return buckets


def _build_markdown(
    *,
    run_id: str,
    map_id: str,
    total_expected: int,
    total_actual: int,
    buckets: dict[str, list[ItemRecord]],
    gaps: list[CoverageGap],
) -> str:
    lines = [
        f"# Coverage-отчёт по прогону {run_id}",
        "",
        f"Карта `{map_id}` — ожидалось {total_expected} айтемов, "
        f"фактически создано в `pipeline.items` этого прогона: {total_actual}.",
        "",
        "| Категория | Кол-во |",
        "|---|---|",
        f"| закрыто (published/draft_loaded) | {len(buckets['closed'])} |",
        f"| no_norm | {len(buckets['no_norm'])} |",
        f"| needs_attention | {len(buckets['needs_attention'])} |",
        f"| pending | {len(buckets['pending'])} |",
    ]
    if total_expected != total_actual:
        lines += [
            "",
            f"**Расхождение карты и факта**: карта несёт {total_expected} "
            f"айтемов, `pipeline.items` этого прогона — {total_actual}. "
            "Обрыв прогона до создания всех айтемов (`run_group` создаёт их "
            "одной пачкой ДО цикла обработки) — проверить логи прогона.",
        ]
    if gaps:
        lines += ["", "## Пробелы (needs_attention)"]
        for gap in gaps:
            suggestion = ""
            if gap.manager_suggestion:
                action = gap.manager_suggestion.get("action")
                note = gap.manager_suggestion.get("note")
                suggestion = f" — менеджер: {action}" + (f" ({note})" if note else "")
            lines.append(
                f"- `{gap.item_id}` {gap.expected_item[:80]!r} "
                f"({gap.last_error}){suggestion}"
            )
    return "\n".join(lines) + "\n"


def coverage_report(
    store: BuildStore,
    run_id: str,
    *,
    manager: ExceptionManagerLike | None = None,
) -> CoverageReport:
    """Карта vs факт по прогону `run_id` — см. докстринг модуля."""
    run_row = store.get_run(run_id)
    map_id = run_row["map_id"]
    map_record = store.load_map(map_id)
    items = store.list_run_items(run_id)

    buckets = _classify(items)
    gaps = [
        CoverageGap(item_id=item.id, expected_item=item.expected_item, last_error=item.last_error)
        for item in buckets["needs_attention"]
    ]
    if manager is not None:
        needs_attention_by_id = {item.id: item for item in buckets["needs_attention"]}
        for gap in gaps:
            history = [gap.last_error] if gap.last_error else []
            gap.manager_suggestion = manager.review(needs_attention_by_id[gap.item_id], history)

    total_expected = len(map_record.payload)
    total_actual = len(items)
    markdown = _build_markdown(
        run_id=run_id, map_id=map_id,
        total_expected=total_expected, total_actual=total_actual,
        buckets=buckets, gaps=gaps,
    )

    return CoverageReport(
        run_id=run_id,
        map_id=map_id,
        total_expected=total_expected,
        total_actual=total_actual,
        closed=len(buckets["closed"]),
        no_norm=len(buckets["no_norm"]),
        needs_attention=len(buckets["needs_attention"]),
        pending=len(buckets["pending"]),
        gaps=gaps,
        markdown=markdown,
    )


def _last_verdict_per_step(pairs: list[tuple[str, Verdict]]) -> dict[str, Verdict]:
    """`pairs` — `[(step, Verdict), ...]` в хронологическом порядке
    (`store.list_item_verdicts`). Более поздняя запись того же `step`
    ПЕРЕЗАПИСЫВАЕТ более раннюю — однопроходная свёртка «последний вердикт
    каждого шага» (см. докстринг модуля, Important фикс-раунда ревью)."""
    last_by_step: dict[str, Verdict] = {}
    for step, verdict in pairs:
        last_by_step[step] = verdict
    return last_by_step


def publish_ready(store: BuildStore, run_id: str) -> int:
    """Публикует `draft_loaded`-айтемы прогона `run_id`, у которых ПОСЛЕДНИЙ
    вердикт КАЖДОГО шага — pass (не вся история, см. докстринг модуля,
    Important фикс-раунда ревью). Возвращает число реально опубликованных
    айтемов (`item.status -> 'published'`)."""
    items = store.list_run_items(run_id)
    published_count = 0
    for item in items:
        if item.status != "draft_loaded":
            continue
        last_by_step = _last_verdict_per_step(store.list_item_verdicts(item.id))
        is_dedup_duplicate = (item.last_error or "").startswith("duplicate_of=")
        if not last_by_step and not is_dedup_duplicate:
            # `all()` над пустым словарём — True: айтем без единой верификации
            # публиковался бы как готовый (план фотоконтроля §3, «вакуальный pass»).
            # Дедуп-дубль — исключение: он маркер, вердикты живут на оригинале.
            store.update_item_status(
                item.id, "needs_attention",
                last_error="публикация отклонена: у айтема нет ни одного вердикта — он не проверялся",
            )
            continue
        if not all(v.passed for v in last_by_step.values()):
            store.update_item_status(
                item.id, "needs_attention",
                last_error="публикация отклонена: последний вердикт хотя бы одного шага — fail",
            )
            continue
        if item.requirement_id:
            store.publish_requirement(item.requirement_id)
        store.update_item_status(item.id, "published")
        published_count += 1
    return published_count
