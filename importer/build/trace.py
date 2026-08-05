"""Трейсинг LLM-вызовов и стоимость Build-конвейера по ролям (Задача 29,
ADR-0003, «Блок 3» — контур D, гейт качества).

## `Tracer` — точка записи `pipeline.llm_calls`

`Tracer` — тонкая обёртка над `BuildStore.save_llm_call` (Задача 29
добавляет этот метод в Protocol `BuildStore`, см. `orchestrator.py`): агент
передаёт роль/модель/токены, `Tracer.record` считает `cost_usd` по
прайс-таблице `models.yaml` (`agents.py: ModelsConfig.pricing`, usd за 1M
токенов вход/выход) и делегирует персистентность стору — сам `Tracer` в БД
не ходит напрямую, та же дисциплина «один слой персистентности», что и у
остального Build (`orchestrator.py`/`coverage.py`).

## Откуда токены, если бэкенд их не отдаёт

Ни один текущий LLM-раннер (`Callable[[str, str], str]`, инжектируется в
`RunnerAgentLLM` — `llm_client.py`) реального счётчика токенов не отдаёт —
живого LLM-подключения ещё нет (см. докстринги `cli.py`/`steps_norm.py`).
Задача 29 расширяет контракт раннера ОПЦИОНАЛЬНЫМ путём: раннер МОЖЕТ
вернуть `tuple[str, dict]` вместо `str` — тогда `RunnerAgentLLM` берёт
реальные `input_tokens`/`output_tokens` бэкенда. Если раннер вернул просто
`str` (ВСЕ существующие scripted-раннеры тестов) — `RunnerAgentLLM`
оценивает токены грубой эвристикой `len(text)//4`; клиенты, которые вообще
не считают usage (например, `ScriptedLLM` из `test_agents.py`), заставляют
трейсящий агент (`agents.py: _trace_llm_call`) оценить токены тем же
способом самостоятельно. Это ПРИБЛИЖЕНИЕ для прикидки стоимости, не точный
биллинг — отдельной колонки/флага "estimated" в `pipeline.llm_calls` нет
(решение контроллера задачи), факт оценки задокументирован только здесь и в
докстринге `llm_client.py:RunnerAgentLLM.complete`.

## `cost_report` — вход CLI `build cost --run <id>`

Тот же паттерн, что и `coverage.py:coverage_report`/`eval_golden.py:run_eval`:
run-level функция агрегирует `store.list_llm_calls(run_id)` по роли и
собирает markdown-таблицу с итогом — печатает CLI (`cli.py`), сама ничего в
БД не пишет (в отличие от `Tracer.record`)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from importer.build.agents import ModelsConfig, load_models_config


class LLMCallStoreLike(Protocol):
    """Минимальный контракт стора, который нужен `Tracer` — подмножество
    `BuildStore` (`orchestrator.py`), достаточное для юнит-тестов `Tracer`
    без полного `InMemoryStore`/`SupabaseBuildStore`."""

    def save_llm_call(
        self,
        run_id: str,
        role: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        cost_usd: float,
        *,
        item_id: str | None = None,
    ) -> None: ...


class Tracer:
    """Трейсер прогона — LATE-BOUND и MUTABLE (фикс-раунд ревью Задачи 29,
    Important: старый дизайн с `run_id`, фиксированным в конструкторе,
    физически не мог доехать до живых LLM-вызовов внутри шагов — фабрика
    шагов (`registry.py: build_step_registry`) строит `Step`-объекты и их
    агентов ДО того, как `Orchestrator.run_group` создаёт `run_id`, а
    `Tracer` со старым дизайном требовал `run_id` уже на этапе конструктора).

    Теперь `Tracer` создаётся ОДИН РАЗ (`Tracer(store)`, `run_id=None` —
    "не привязан"), передаётся И в `build_step_registry(tracer=...)` (тот же
    объект долетает до каждого `Step` и его агентов, см. `registry.py`), И в
    `Orchestrator(steps=registry, tracer=tracer)` — оркестратор мутирует ТОТ
    ЖЕ объект по ходу прогона: `bind_run(run_id)` один раз в начале
    `run_group`/`rerun_item`, `bind_item(item.id)` перед шагами каждого
    айтема и `bind_item(None)` после. Поскольку все держатели этого объекта
    (агенты внутри шагов) видят одну и ту же мутацию, `record()`, вызванный
    ЛЮБЫМ агентом ЛЮБОГО шага в любой момент прогона, попадает под правильные
    `run_id`/`item_id` без явной передачи их через сигнатуры шагов.

    Мутабельность безопасна: CLI и `Orchestrator` — однопоточные (никакого
    параллелизма по айтемам внутри одного прогона, `_run_from` идёт строго
    последовательно), гонок за `self._run_id`/`self._item_id` нет.

    `record()`, вызванный ДО `bind_run` (например, конструирование шагов на
    этапе, где `run_id` ещё не существует) — намеренный no-op, не ошибка и
    не буферизация "на потом": до Задачи 29 трейсинга не было вовсе,
    пропущенный вызов до первого `bind_run` не хуже старого поведения."""

    def __init__(
        self,
        store: LLMCallStoreLike,
        run_id: str | None = None,
        models: ModelsConfig | None = None,
    ):
        self._store = store
        self._run_id = run_id
        self._item_id: str | None = None
        self._models = models or load_models_config()

    @property
    def run_id(self) -> str | None:
        return self._run_id

    def bind_run(self, run_id: str) -> None:
        """Привязывает трейсер к прогону — вызывается РОВНО один раз в
        начале `Orchestrator.run_group`/`rerun_item`, сразу после того, как
        `run_id` реально создан (`store.create_run`/уже существующий
        `item.run_id`). Сбрасывает `item_id` (новый прогон — старый
        item-контекст не имеет смысла)."""
        self._run_id = run_id
        self._item_id = None

    def bind_item(self, item_id: str | None) -> None:
        """Привязывает трейсер к текущему айтему прогона — `Orchestrator`
        вызывает перед шагами айтема (`bind_item(item.id)`) и
        `bind_item(None)` сразу после (вызовы вне цикла по айтемам,
        например будущие run-level агенты, не приписываются айтему)."""
        self._item_id = item_id

    def record(
        self,
        role: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        *,
        item_id: str | None = None,
    ) -> None:
        """Пишет один вызов LLM в `pipeline.llm_calls` через
        `store.save_llm_call` — `cost_usd` считается здесь по прайсу
        `models.yaml`, не хранится готовым у вызывающего кода.

        `item_id`: явный override (используется юнит-тестами `Tracer`
        напрямую); если не передан — берётся текущее связанное состояние
        `self._item_id` (обычный путь агентов внутри шага, см. докстринг
        класса). `run_id=None` (трейсер ещё не забинден вызовом `bind_run`)
        — намеренный no-op."""
        if self._run_id is None:
            return
        resolved_item_id = item_id if item_id is not None else self._item_id
        cost_usd = self._cost_usd(model, input_tokens, output_tokens)
        self._store.save_llm_call(
            self._run_id, role, model, input_tokens, output_tokens, cost_usd,
            item_id=resolved_item_id,
        )

    def _cost_usd(self, model: str, input_tokens: int, output_tokens: int) -> float:
        pricing = self._models.pricing.get(model)
        if pricing is None:
            raise ValueError(
                f"Tracer.record: нет прайса для модели {model!r} в models.yaml "
                f"(известные модели: {sorted(self._models.pricing)})"
            )
        cost = (
            input_tokens * pricing["input_per_1m_usd"]
            + output_tokens * pricing["output_per_1m_usd"]
        ) / 1_000_000
        return round(cost, 5)


@dataclass
class CostRoleRow:
    """Одна строка таблицы `build cost --run <id>` — агрегат по роли."""

    role: str
    calls: int
    input_tokens: int
    output_tokens: int
    cost_usd: float


@dataclass
class CostReport:
    run_id: str
    rows: list[CostRoleRow] = field(default_factory=list)
    total_calls: int = 0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_cost_usd: float = 0.0
    markdown: str = ""


def _build_cost_markdown(run_id: str, rows: list[CostRoleRow], report: CostReport) -> str:
    lines = [
        f"# Стоимость прогона {run_id} по ролям",
        "",
        "| role | calls | in_tokens | out_tokens | cost_usd |",
        "|---|---|---|---|---|",
    ]
    for row in rows:
        lines.append(
            f"| {row.role} | {row.calls} | {row.input_tokens} | {row.output_tokens} | "
            f"{row.cost_usd:.5f} |"
        )
    lines.append(
        f"| **итого** | {report.total_calls} | {report.total_input_tokens} | "
        f"{report.total_output_tokens} | {report.total_cost_usd:.5f} |"
    )
    return "\n".join(lines) + "\n"


def cost_report(store, run_id: str) -> CostReport:
    """Агрегирует `store.list_llm_calls(run_id)` по роли — вход CLI
    `build cost --run <id>` (`cli.py`). Порядок строк — первое появление
    роли в `list_llm_calls` (хронологический порядок вызовов прогона, см.
    `SupabaseBuildStore.list_llm_calls`/`InMemoryStore.list_llm_calls`)."""
    calls = store.list_llm_calls(run_id)

    order: list[str] = []
    by_role: dict[str, CostRoleRow] = {}
    for call in calls:
        role = call["role"]
        if role not in by_role:
            order.append(role)
            by_role[role] = CostRoleRow(
                role=role, calls=0, input_tokens=0, output_tokens=0, cost_usd=0.0
            )
        row = by_role[role]
        row.calls += 1
        row.input_tokens += call.get("input_tokens") or 0
        row.output_tokens += call.get("output_tokens") or 0
        row.cost_usd = round(row.cost_usd + float(call.get("cost_usd") or 0), 5)

    rows = [by_role[role] for role in order]
    report = CostReport(
        run_id=run_id,
        rows=rows,
        total_calls=sum(r.calls for r in rows),
        total_input_tokens=sum(r.input_tokens for r in rows),
        total_output_tokens=sum(r.output_tokens for r in rows),
        total_cost_usd=round(sum(r.cost_usd for r in rows), 5),
    )
    report.markdown = _build_cost_markdown(run_id, rows, report)
    return report
