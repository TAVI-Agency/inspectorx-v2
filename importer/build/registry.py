"""Фабрика per-run STEP_ORDER-шагов (Задача 27, ADR-0003 «Блок 2», финал).

`load_default_steps()` (`steps.py`) регистрирует шаговые callable в
ГЛОБАЛЬНОМ реестре модуля — единственный на весь процесс, поэтому шаги с
конструкторными зависимостями (`NormStep.jurisdiction`, `ScopeStep.group_ref`,
`CasesStep.jurisdiction`, `LoadStep.group_ref`/`jurisdiction`,
`TranslateStep.target_lang`, `AssembleStep.jurisdiction`,
`SanctionsStep.jurisdiction`) получают там заглушки (`_STUB_GROUP_REF=""`,
`DEFAULT_JURISDICTION='UZ'`) — верно только для UZ-прогонов по группе,
случайно совпавшей с заглушкой. `build_step_registry` строит СВЕЖИЙ словарь
шагов на каждый прогон, подставляя реальные `group_ref`/`jurisdiction` карты
(`MapRecord.group_ref`/`.jurisdiction`, `orchestrator.py`) — `Orchestrator`
получает его через `steps=` конструктора, `get_step()`/глобальный реестр
вообще не трогается (`load_default_steps()` остаётся для обратной
совместимости тестов, которые полагаются на глобальный реестр, — см.
докстринг `steps.py:load_default_steps`).

`coverage` — вне этого словаря (14 ключей, `STEP_ORDER` без `'coverage'`,
см. докстринг `steps.py`): это run-level функция `coverage.coverage_report`,
не per-item шаг.
"""
from __future__ import annotations

from typing import Callable

from importer.build.agents import ModelsConfig
from importer.build.assembler import AssembleStep
from importer.build.embeddings import Embedder, LiveEmbedder
from importer.build.legalx import LegalXClient
from importer.build.llm_client import AgentLLMClient, RunnerAgentLLM
from importer.build.orchestrator import BuildStore
from importer.build.steps import STEP_ORDER, StepFn
from importer.build.steps_cases import CasesStep
from importer.build.steps_classify import ClassifyStep
from importer.build.steps_dedup import DedupStep
from importer.build.steps_load import LoadStep
from importer.build.steps_norm import NormStep, SummaryStep
from importer.build.steps_rule import RuleStep
from importer.build.steps_samples_lawyer import LawyerStep, SamplesStep
from importer.build.steps_sanctions import SanctionsStep
from importer.build.steps_scope_lifecycle import LifecycleStep, ScopeStep
from importer.build.steps_translate import TranslateStep
from importer.build.websearch import WebSearcher, get_web_searcher

# jurisdiction -> целевой язык перевода шага 'translate' (решение
# контроллера Задачи 27): UZ — узбекский (primary market, ADR-0002), AE —
# английский (арабский не нужен, global-constraints.md), KZ — перевод
# пропускается (контент уже ru, см. докстринг steps_translate.py). Любая
# другая/неизвестная юрисдикция — тоже None: безопасный дефолт («перевод не
# нужен»), не ошибка конфигурации.
_TARGET_LANG_BY_JURISDICTION: dict[str, str | None] = {"UZ": "uz", "AE": "en", "KZ": None}


def target_lang_for_jurisdiction(jurisdiction: str) -> str | None:
    """Целевой язык шага 'translate' по юрисдикции карты — см. таблицу выше."""
    return _TARGET_LANG_BY_JURISDICTION.get(jurisdiction)


def build_step_registry(
    store: BuildStore,
    llm_runner: Callable[[str, str], str],
    legalx: LegalXClient,
    *,
    group_ref: str,
    jurisdiction: str,
    searcher: WebSearcher | None = None,
    embedder: Embedder | None = None,
    models: ModelsConfig | None = None,
) -> dict[str, StepFn]:
    """Собирает словарь шагов `STEP_ORDER` (без `'coverage'`) для ОДНОГО
    прогона по `(group_ref, jurisdiction)` — тот же `group_ref`/`jurisdiction`,
    что и у утверждённой карты, которую гонит `Orchestrator.run_group`.

    `llm_runner`/`legalx`/`searcher`/`embedder` — общая инфраструктура прогона
    (один `AgentLLMClient` на все шаги, кроме случаев, где Verifier обязан
    получить модель другого тира — это решает `verifier_model_for` ВНУТРИ
    каждого шага, не здесь). `searcher`/`embedder` — опциональны, по
    умолчанию живые бэкенды (`get_web_searcher()`/`LiveEmbedder()`, тот же
    принцип отсрочки, что и везде в Build) — синтетический/тестовый прогон
    инжектирует свои реализации явно."""
    llm: AgentLLMClient = RunnerAgentLLM(llm_runner)
    target_lang = target_lang_for_jurisdiction(jurisdiction)
    searcher = searcher or get_web_searcher()
    embedder = embedder or LiveEmbedder()

    steps: dict[str, StepFn] = {
        "norm": NormStep(legalx, llm, jurisdiction=jurisdiction, models=models),
        "summary": SummaryStep(llm, models=models),
        "category": ClassifyStep(llm, store, models),
        "rule": RuleStep(llm, models=models),
        "scope": ScopeStep(llm, store, group_ref=group_ref, models=models),
        "lifecycle": LifecycleStep(llm, models=models),
        "sanctions": SanctionsStep(legalx, llm, jurisdiction=jurisdiction, models=models),
        "cases": CasesStep(legalx, llm, jurisdiction=jurisdiction, models=models),
        "samples": SamplesStep(searcher, llm, models=models),
        "lawyer": LawyerStep(llm, models=models),
        "translate": TranslateStep(llm, target_lang=target_lang, models=models),
        "dedup": DedupStep(llm, store, embedder, models=models),
        "assemble": AssembleStep(llm, jurisdiction=jurisdiction, models=models),
        "load": LoadStep(store, group_ref=group_ref, jurisdiction=jurisdiction),
    }
    assert set(steps) == set(STEP_ORDER), (
        f"build_step_registry разошёлся со STEP_ORDER: {sorted(set(steps) ^ set(STEP_ORDER))}"
    )
    return steps
