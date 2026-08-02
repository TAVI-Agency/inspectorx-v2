"""Реестр шагов Build-конвейера (ADR-0003, решение 5) и общие типы для
`Orchestrator` (Задача 14) и шаговых функций (Задачи 17–25).

`STEP_ORDER` зафиксирован брифом Задачи 14 — это КОД, не решение модели
(ADR-0003, решение 2 «Оркестрация — гибрид, а не агент-дирижёр»):
`Orchestrator` идёт по этому списку строго последовательно, шаг за шагом,
без единого обращения к LLM в самой маршрутизации.

Сами шаговые функции здесь не реализованы — только контракт: имя шага,
`StepResult`, реестр `callable` по имени. Конкретные функции регистрируют
себя через `register_step` в своих модулях (Задачи 17–25); в этой задаче
реестр пуст намеренно, тесты `Orchestrator` подставляют собственные
фейковые `callable` напрямую в конструктор, минуя реестр.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Literal

from importer.build.agents import Verdict

# Порядок шагов конвейера Build — РОВНО как в брифе Задачи 14. Менять список
# шагов — ревизия мастер-плана, а не побочный эффект правки кода.
STEP_ORDER: list[str] = [
    "norm", "summary", "category", "rule", "scope", "lifecycle",
    "sanctions", "cases", "samples", "lawyer", "translate", "dedup",
    "assemble", "load", "coverage",
]

StepStatus = Literal["ok", "fail", "no_norm"]


@dataclass
class StepResult:
    """Результат одного шага конвейера для одного айтема.

    - `ok` — шаг прошёл, `Orchestrator` идёт к следующему шагу STEP_ORDER;
    - `fail` — ретрай того же шага (до `MAX_STEP_RETRIES` подряд, см.
      `orchestrator.py`), после исчерпания — needs_attention;
    - `no_norm` — терминальный валидный исход (в норме — от шага 'norm'):
      остальные шаги для айтема пропускаются.
    """

    status: StepStatus
    verdicts: list[Verdict] = field(default_factory=list)
    error: str | None = None


@dataclass
class ItemRecord:
    """Строка `pipeline.items`, какой её видит `Orchestrator`/шаговые функции."""

    id: str
    run_id: str
    expected_item: str
    category_slug: str | None = None
    requirement_id: str | None = None
    status: str = "pending"
    retry_count: int = 0
    last_error: str | None = None


@dataclass
class ItemContext:
    """Контекст одного айтема, который `Orchestrator` передаёт шаговым
    функциям. `data` — накопленные промежуточные результаты предыдущих
    шагов ТЕКУЩЕГО прогона, только в памяти: что туда класть и читать —
    решают сами шаговые функции (Задачи 17–25); персистентность того, что
    должно пережить partial rerun (`Orchestrator.rerun_item`), — поля
    `item` (строка `pipeline.items`), не `data`."""

    item: ItemRecord
    data: dict = field(default_factory=dict)


StepFn = Callable[[ItemContext], StepResult]

# Реестр шаговых функций по имени — наполняется Задачами 17–25 через
# register_step. Пуст в этой задаче намеренно.
_REGISTRY: dict[str, StepFn] = {}


def register_step(name: str, fn: StepFn) -> StepFn:
    """Регистрирует шаговую функцию под именем `name`, возвращает её же
    (удобно для `register_step("norm", run_norm_step)` в модуле шага).

    `name` обязан входить в `STEP_ORDER` — иначе это опечатка в имени шага,
    а не новый шаг конвейера (список шагов меняется ревизией мастер-плана,
    не побочным эффектом регистрации)."""
    if name not in STEP_ORDER:
        raise ValueError(
            f"Шаг {name!r} не входит в STEP_ORDER {STEP_ORDER} — опечатка в имени?"
        )
    _REGISTRY[name] = fn
    return fn


def get_step(name: str) -> StepFn:
    """Возвращает зарегистрированную шаговую функцию по имени.

    Пока конкретные шаги не заведены (Задачи 17–25), любой вызов честно
    падает — лучше явная ошибка, чем молчаливый `None` дальше в `Orchestrator`.
    """
    try:
        return _REGISTRY[name]
    except KeyError as exc:
        raise KeyError(
            f"Шаг {name!r} не зарегистрирован — конкретные шаговые функции "
            "вводятся Задачами 17–25 (см. docs/adr/0003-agent-flow.md)"
        ) from exc


def load_default_steps() -> None:
    """Импортирует шаговые модули (Задачи 17–25), чтобы их `register_step`
    (вызванный на уровне модуля — см. докстринг выше) сработал.

    Ничего в кодовой базе САМО не импортирует шаговые модули: CLI (`build
    run`, `importer/cli.py`) строит `Orchestrator(store)` без явного
    `steps=`, то есть идёт через `get_step()` в реестр, пустой до первого
    импорта нужного модуля. `load_default_steps()` — минимальный механизм
    подключения (решение контроллера Задачи 17, `task-17-brief.md`): вызвать
    один раз перед прогоном, который берёт шаги из реестра, а не передаёт их
    явно, как тесты `Orchestrator` (`test_orchestrator.py`/
    `test_cartographer.py` передают фейковые callable напрямую в
    конструктор — `load_default_steps` им не нужна, реестр они не трогают).

    Список модулей растёт по мере реализации следующих шагов (Задачи
    18–25) — сейчас `steps_norm` ('norm'/'summary'), `steps_classify`
    ('category'), `steps_rule` ('rule'), `steps_scope_lifecycle`
    ('scope'/'lifecycle') и `steps_sanctions` ('sanctions')."""
    from importer.build import steps_norm  # noqa: F401
    from importer.build import steps_classify  # noqa: F401
    from importer.build import steps_rule  # noqa: F401
    from importer.build import steps_scope_lifecycle  # noqa: F401
    from importer.build import steps_sanctions  # noqa: F401
