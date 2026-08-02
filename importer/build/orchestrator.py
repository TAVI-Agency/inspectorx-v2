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
from typing import Protocol

from importer.build.agents import Verdict
from importer.build.steps import (
    STEP_ORDER,
    ItemContext,
    ItemRecord,
    StepFn,
    get_step,
)

# Сколько ПОДРЯД фейлов одного шага допускается, прежде чем айтем уходит в
# needs_attention. Ретраи не «дожимают» до pass (ADR-0003, решение 4) —
# это верхняя граница попыток одного шага, не число дополнительных ретраев
# сверх первой попытки: 1-й fail → ретрай, 2-й fail → ретрай, 3-й fail (N=3
# подряд) → escalate, к следующему шагу не переходим.
MAX_STEP_RETRIES = 3


class MapNotApprovedError(Exception):
    """`run_group` вызван по карте, чей `status != 'approved'` — стоп-точка
    ① (единственный ручной gate конвейера, ADR-0003 решение 2)."""


@dataclass(frozen=True)
class MapRecord:
    """Строка `pipeline.maps`, какой её видит `Orchestrator`."""

    id: str
    group_ref: str
    jurisdiction: str
    status: str
    payload: list[dict]


@dataclass
class RunReport:
    """Итог `run_group`: сколько айтемов куда пришли."""

    run_id: str
    map_id: str
    total_items: int
    published: int = 0
    no_norm: int = 0
    needs_attention: int = 0


class BuildStore(Protocol):
    """Тонкий интерфейс персистентности поверх `pipeline.*` (схема — Задача
    11). Реальная реализация — `SupabaseBuildStore` ниже, поверх паттерна
    `importer/db.py`; в тестах state machine — `InMemoryStore`
    (`importer/tests/build/test_orchestrator.py`), никакой живой БД."""

    def load_map(self, map_id: str) -> MapRecord: ...

    def create_run(self, map_id: str) -> str: ...

    def create_items(self, run_id: str, payload: list[dict]) -> list[ItemRecord]: ...

    def update_item_status(
        self, item_id: str, status: str, *, last_error: str | None = None
    ) -> ItemRecord: ...

    def bump_retry(self, item_id: str) -> int: ...

    def save_verdicts(self, item_id: str, step: str, verdicts: list[Verdict]) -> None: ...

    def finish_run(self, run_id: str, status: str) -> None: ...


def escalate(item: ItemRecord, reason: str, store: BuildStore) -> None:
    """Заглушка LLM-«менеджера исключений» (ADR-0003, решение 2): пишет
    `reason` в `last_error` и переводит айтем в `needs_attention`.
    Полноценный менеджер исключений — Задача 27."""
    store.update_item_status(item.id, "needs_attention", last_error=reason)


class Orchestrator:
    def __init__(self, store: BuildStore, steps: dict[str, StepFn] | None = None):
        self._store = store
        # None -> берём шаги из глобального реестра steps.py (реальный
        # прогон); в тестах передаётся словарь фейковых callable напрямую,
        # реестр вообще не трогается.
        self._steps = steps

    def run_group(self, map_id: str) -> RunReport:
        """Прогоняет все айтемы утверждённой карты по STEP_ORDER. Карта в
        статусе, отличном от 'approved', — стоп-точка ①: `MapNotApprovedError`
        ДО создания run/items (ничего не пишется в БД по неапрувленной карте)."""
        map_record = self._store.load_map(map_id)
        if map_record.status != "approved":
            raise MapNotApprovedError(
                f"Карта {map_id} не апрувнута (status={map_record.status!r}) — "
                "стоп-точка ①: сначала апрув владельцем"
            )
        run_id = self._store.create_run(map_id)
        items = self._store.create_items(run_id, map_record.payload)

        report = RunReport(run_id=run_id, map_id=map_id, total_items=len(items))
        for item in items:
            item = self._store.update_item_status(item.id, "in_progress")
            ctx = ItemContext(item=item)
            final_status = self._run_from(ctx, start_index=0)
            self._tally(report, final_status)

        self._store.finish_run(run_id, "done")
        return report

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

    def _run_from(self, ctx: ItemContext, start_index: int) -> str:
        """Гонит `ctx.item` по STEP_ORDER начиная с `start_index`. Возвращает
        терминальный статус: 'published' | 'no_norm' | 'needs_attention'."""
        for step_name in STEP_ORDER[start_index:]:
            step_fn = self._step(step_name)
            consecutive_fails = 0
            while True:
                result = step_fn(ctx)
                if result.verdicts:
                    self._store.save_verdicts(ctx.item.id, step_name, result.verdicts)

                if result.status == "ok":
                    break

                if result.status == "no_norm":
                    # Терминальный валидный исход — остальные шаги пропускаются.
                    self._store.update_item_status(ctx.item.id, "no_norm")
                    return "no_norm"

                # result.status == "fail"
                consecutive_fails += 1
                if consecutive_fails >= MAX_STEP_RETRIES:
                    reason = result.error or (
                        f"шаг {step_name!r}: {consecutive_fails} провалов подряд"
                    )
                    escalate(ctx.item, reason, self._store)
                    return "needs_attention"  # к следующему item, конвейер не публикует
                self._store.bump_retry(ctx.item.id)
                # тот же шаг — ретрай (while продолжается)

        self._store.update_item_status(ctx.item.id, "published")
        return "published"

    @staticmethod
    def _tally(report: RunReport, final_status: str) -> None:
        if final_status == "published":
            report.published += 1
        elif final_status == "no_norm":
            report.no_norm += 1
        elif final_status == "needs_attention":
            report.needs_attention += 1


# ============================================================================
# SupabaseBuildStore — реальная реализация BuildStore поверх importer/db.py
# ============================================================================


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
    )


class SupabaseBuildStore:
    """`BuildStore` поверх Supabase (паттерн `importer/db.py`, схема
    `pipeline` из Задачи 11). Используется CLI (`importer/cli.py`); тесты
    state machine её не гоняют — см. `InMemoryStore` в
    `importer/tests/build/test_orchestrator.py`."""

    def __init__(self, client):
        self._db = client.schema("pipeline")

    def load_map(self, map_id: str) -> MapRecord:
        rows = self._db.table("maps").select("*").eq("id", map_id).execute().data
        if not rows:
            raise ValueError(f"Карта {map_id} не найдена в pipeline.maps")
        row = rows[0]
        return MapRecord(
            id=row["id"],
            group_ref=row["group_ref"],
            jurisdiction=row["jurisdiction"],
            status=row["status"],
            payload=row["payload"],
        )

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

    def update_item_status(
        self, item_id: str, status: str, *, last_error: str | None = None
    ) -> ItemRecord:
        patch: dict = {"status": status}
        if last_error is not None:
            patch["last_error"] = last_error
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
