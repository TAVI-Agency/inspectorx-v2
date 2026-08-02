"""Оркестратор Build (Задача 14): state machine на `pipeline.items`.

Сценарии из брифа Задачи 14:
- порядок шагов детерминирован (код, не LLM) — `STEP_ORDER` ровно как в
  брифе, `run_group` идёт по нему строго последовательно;
- `verdict=fail` шага → ретрай того же шага; после N=3 подряд фейлов айтем
  уходит в `needs_attention` и конвейер НЕ публикует (fail-политика
  ADR-0003 р.4), обработка переходит к следующему item;
- `no_norm` от шага 'norm' — терминальный валидный исход, остальные шаги
  пропускаются;
- `run_group` по карте со статусом `draft` → `MapNotApprovedError`
  (стоп-точка ①), причём ДО создания run/items;
- `rerun_item` валидирует `from_step` и гонит только хвост STEP_ORDER;
- все переходы статуса/ретраи/вердикты идут ТОЛЬКО через `BuildStore`
  (`InMemoryStore` ниже — тесты state machine не ходят в живую БД).
"""
from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from importer.build.agents import Verdict
from importer.build.orchestrator import (
    MAX_STEP_RETRIES,
    MapNotApprovedError,
    MapRecord,
    Orchestrator,
    RunReport,
    escalate,
)
from importer.build.steps import STEP_ORDER, ItemContext, ItemRecord, StepResult


# ── тестовые дублёры ────────────────────────────────────────────────────


@dataclass
class InMemoryStore:
    """Фейковый BuildStore: без сети и без БД, только словари в памяти."""

    maps: dict[str, MapRecord] = field(default_factory=dict)
    items: dict[str, ItemRecord] = field(default_factory=dict)
    runs: dict[str, dict] = field(default_factory=dict)
    verdicts: list[tuple[str, str, list[Verdict]]] = field(default_factory=list)
    # (item_id, status) в порядке вызовов — чтобы проверять переходы, не только итог
    status_history: list[tuple[str, str]] = field(default_factory=list)
    _next_id: int = 0

    def _gen_id(self, prefix: str) -> str:
        self._next_id += 1
        return f"{prefix}-{self._next_id}"

    def load_map(self, map_id: str) -> MapRecord:
        return self.maps[map_id]

    def create_run(self, map_id: str) -> str:
        run_id = self._gen_id("run")
        self.runs[run_id] = {"map_id": map_id, "status": "running"}
        return run_id

    def create_items(self, run_id: str, payload: list[dict]) -> list[ItemRecord]:
        created = []
        for entry in payload:
            item_id = self._gen_id("item")
            item = ItemRecord(
                id=item_id,
                run_id=run_id,
                expected_item=entry["expected_item"],
                category_slug=entry.get("category_slug"),
            )
            self.items[item_id] = item
            created.append(item)
        return created

    def update_item_status(self, item_id, status, *, last_error=None) -> ItemRecord:
        item = self.items[item_id]
        item.status = status
        if last_error is not None:
            item.last_error = last_error
        self.status_history.append((item_id, status))
        return item

    def bump_retry(self, item_id: str) -> int:
        item = self.items[item_id]
        item.retry_count += 1
        return item.retry_count

    def save_verdicts(self, item_id, step, verdicts) -> None:
        self.verdicts.append((item_id, step, verdicts))

    def finish_run(self, run_id: str, status: str) -> None:
        self.runs[run_id]["status"] = status


class ScriptedStep:
    """Фейковый шаг: отдаёт `StepResult` по очереди из скрипта (последний
    повторяется, если вызовов больше). Фиксирует контекст каждого вызова."""

    def __init__(self, *results: StepResult):
        self._results = list(results) or [StepResult(status="ok")]
        self.contexts: list[ItemContext] = []

    def __call__(self, ctx: ItemContext) -> StepResult:
        self.contexts.append(ctx)
        idx = min(len(self.contexts) - 1, len(self._results) - 1)
        return self._results[idx]

    @property
    def call_count(self) -> int:
        return len(self.contexts)


def ok_step() -> ScriptedStep:
    return ScriptedStep(StepResult(status="ok"))


def make_steps(overrides: dict[str, ScriptedStep] | None = None) -> dict[str, ScriptedStep]:
    steps = {name: ok_step() for name in STEP_ORDER}
    if overrides:
        steps.update(overrides)
    return steps


def approved_map(**over) -> MapRecord:
    base = dict(
        id="map-1", group_ref="2203", jurisdiction="UZ", status="approved",
        payload=[{"expected_item": "маркировка акцизной маркой", "category_slug": "marking"}],
    )
    return MapRecord(**{**base, **over})


# ── STEP_ORDER: зафиксирован брифом, код — не LLM ───────────────────────


def test_step_order_matches_brief_exactly():
    assert STEP_ORDER == [
        "norm", "summary", "category", "rule", "scope", "lifecycle",
        "sanctions", "cases", "samples", "lawyer", "translate", "dedup",
        "assemble", "load", "coverage",
    ]


def test_max_step_retries_is_three():
    assert MAX_STEP_RETRIES == 3


def test_run_group_processes_all_steps_in_fixed_order():
    store = InMemoryStore()
    store.maps["map-1"] = approved_map()
    call_order: list[str] = []

    def tracking_step(name):
        def _step(ctx):
            call_order.append(name)
            return StepResult(status="ok")
        return _step

    steps = {name: tracking_step(name) for name in STEP_ORDER}
    orchestrator = Orchestrator(store, steps=steps)

    report = orchestrator.run_group("map-1")

    assert call_order == STEP_ORDER
    assert isinstance(report, RunReport)
    assert report.total_items == 1
    assert report.published == 1
    assert report.no_norm == 0
    assert report.needs_attention == 0
    item = next(iter(store.items.values()))
    assert item.status == "published"


def test_run_group_finishes_run_with_done_status():
    store = InMemoryStore()
    store.maps["map-1"] = approved_map()
    orchestrator = Orchestrator(store, steps=make_steps())

    report = orchestrator.run_group("map-1")

    assert store.runs[report.run_id]["status"] == "done"
    assert store.runs[report.run_id]["map_id"] == "map-1"


# ── стоп-точка ①: run по draft-карте ─────────────────────────────────────


def test_run_group_raises_map_not_approved_for_draft_map():
    store = InMemoryStore()
    store.maps["map-1"] = approved_map(status="draft")
    orchestrator = Orchestrator(store, steps=make_steps())

    with pytest.raises(MapNotApprovedError):
        orchestrator.run_group("map-1")

    # исключение — ДО создания run/items, ничего не пишется по неапрувленной карте
    assert store.runs == {}
    assert store.items == {}


def test_run_group_raises_map_not_approved_for_rejected_map():
    store = InMemoryStore()
    store.maps["map-1"] = approved_map(status="rejected")
    orchestrator = Orchestrator(store, steps=make_steps())

    with pytest.raises(MapNotApprovedError):
        orchestrator.run_group("map-1")


# ── ретраи: fail → retry → needs_attention после N=3 подряд ─────────────


def test_step_that_fails_twice_then_succeeds_does_not_escalate():
    store = InMemoryStore()
    store.maps["map-1"] = approved_map()
    flaky = ScriptedStep(
        StepResult(status="fail", error="e1"),
        StepResult(status="fail", error="e2"),
        StepResult(status="ok"),
    )
    steps = make_steps({"category": flaky})
    orchestrator = Orchestrator(store, steps=steps)

    report = orchestrator.run_group("map-1")

    assert flaky.call_count == 3
    assert report.published == 1
    assert report.needs_attention == 0
    item = next(iter(store.items.values()))
    assert item.status == "published"
    assert item.retry_count == 2  # два ретрая, третья попытка — успех


def test_step_that_fails_three_times_in_a_row_escalates_and_stops_pipeline():
    store = InMemoryStore()
    store.maps["map-1"] = approved_map()
    always_fails = ScriptedStep(StepResult(status="fail", error="верификация не прошла"))
    steps = make_steps({"sanctions": always_fails})
    orchestrator = Orchestrator(store, steps=steps)

    report = orchestrator.run_group("map-1")

    assert always_fails.call_count == MAX_STEP_RETRIES  # ровно N=3, не больше
    assert report.needs_attention == 1
    assert report.published == 0
    item = next(iter(store.items.values()))
    assert item.status == "needs_attention"
    assert item.last_error == "верификация не прошла"
    assert item.retry_count == 2  # ретраи между 3 попытками — их 2

    # шаги ПОСЛЕ 'sanctions' не вызывались вообще — конвейер не публикует
    idx = STEP_ORDER.index("sanctions")
    for name in STEP_ORDER[idx + 1:]:
        assert steps[name].call_count == 0
    # 'published' для этого айтема не встречается в истории вообще
    assert "published" not in [s for (_id, s) in store.status_history]


def test_run_group_continues_to_next_item_after_one_item_escalates():
    """'к следующему item' — эскалация одного айтема не должна останавливать
    обработку остальных айтемов того же запуска."""
    store = InMemoryStore()
    store.maps["map-1"] = approved_map(
        payload=[
            {"expected_item": "требование A"},
            {"expected_item": "требование B"},
        ]
    )

    def flaky_norm(ctx):
        if ctx.item.expected_item == "требование A":
            return StepResult(status="fail", error="норм не нашли")
        return StepResult(status="ok")

    steps = make_steps({"norm": flaky_norm})
    orchestrator = Orchestrator(store, steps=steps)

    report = orchestrator.run_group("map-1")

    assert report.total_items == 2
    assert report.needs_attention == 1
    assert report.published == 1
    statuses = {item.expected_item: item.status for item in store.items.values()}
    assert statuses["требование A"] == "needs_attention"
    assert statuses["требование B"] == "published"


def test_escalate_writes_reason_to_last_error_and_sets_needs_attention():
    store = InMemoryStore()
    item = ItemRecord(id="item-1", run_id="run-1", expected_item="x")
    store.items[item.id] = item

    escalate(item, "3 провала verifier подряд", store)

    assert store.items["item-1"].status == "needs_attention"
    assert store.items["item-1"].last_error == "3 провала verifier подряд"


# ── no_norm: терминальный исход, остальные шаги пропускаются ────────────


def test_no_norm_from_norm_step_is_terminal_and_skips_remaining_steps():
    store = InMemoryStore()
    store.maps["map-1"] = approved_map()
    steps = make_steps({"norm": ScriptedStep(StepResult(status="no_norm"))})
    orchestrator = Orchestrator(store, steps=steps)

    report = orchestrator.run_group("map-1")

    assert report.no_norm == 1
    assert report.published == 0
    assert report.needs_attention == 0
    item = next(iter(store.items.values()))
    assert item.status == "no_norm"
    for name in STEP_ORDER[1:]:
        assert steps[name].call_count == 0


# ── вердикты пишутся через store ─────────────────────────────────────────


def test_step_verdicts_are_persisted_via_store():
    store = InMemoryStore()
    store.maps["map-1"] = approved_map()
    verdict = Verdict(passed=True, reason="фрагмент подтверждён", model="gpt-5")
    steps = make_steps({"rule": ScriptedStep(StepResult(status="ok", verdicts=[verdict]))})
    orchestrator = Orchestrator(store, steps=steps)

    orchestrator.run_group("map-1")

    assert len(store.verdicts) == 1
    item_id, step_name, verdicts = store.verdicts[0]
    assert step_name == "rule"
    assert verdicts == [verdict]
    assert item_id in store.items


# ── rerun_item: частичный Build для контура C ────────────────────────────


def test_rerun_item_runs_only_steps_from_given_step_onward():
    store = InMemoryStore()
    item = ItemRecord(id="item-1", run_id="run-1", expected_item="x", status="needs_attention")
    store.items[item.id] = item
    steps = make_steps()
    orchestrator = Orchestrator(store, steps=steps)

    orchestrator.rerun_item("item-1", from_step="rule")

    idx = STEP_ORDER.index("rule")
    for name in STEP_ORDER[:idx]:
        assert steps[name].call_count == 0
    for name in STEP_ORDER[idx:]:
        assert steps[name].call_count == 1
    assert store.items["item-1"].status == "published"
    assert store.status_history[0] == ("item-1", "in_progress")


def test_rerun_item_rejects_step_not_in_step_order():
    store = InMemoryStore()
    store.items["item-1"] = ItemRecord(id="item-1", run_id="run-1", expected_item="x")
    orchestrator = Orchestrator(store, steps=make_steps())

    with pytest.raises(ValueError):
        orchestrator.rerun_item("item-1", from_step="not-a-real-step")

    # статус не тронут — валидация до любых обращений к store по item_id
    assert store.status_history == []


def test_rerun_item_can_also_escalate_if_tail_keeps_failing():
    store = InMemoryStore()
    store.items["item-1"] = ItemRecord(id="item-1", run_id="run-1", expected_item="x")
    always_fails = ScriptedStep(StepResult(status="fail", error="снова не прошло"))
    steps = make_steps({"translate": always_fails})
    orchestrator = Orchestrator(store, steps=steps)

    orchestrator.rerun_item("item-1", from_step="translate")

    assert always_fails.call_count == MAX_STEP_RETRIES
    assert store.items["item-1"].status == "needs_attention"
    assert store.items["item-1"].last_error == "снова не прошло"
