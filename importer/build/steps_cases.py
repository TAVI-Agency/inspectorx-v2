"""Шаг 'cases' Build-конвейера (Задача 22, ADR-0003 «Блок 2»,
`docs/TARGET_FORMAT.md` §4 «Судебные кейсы»).

Один шаг STEP_ORDER, внутри — три фазы (task-22-brief.md, уточнения
контроллера):

## 1) LegalX.search_cases(article) → ≤5 кейсов

Статья берётся из ctx.data['sanctions'][0]['article']. Если санкции не найдены
или пусты (sanctions_not_found/ПУСТОЙ массив) — кейсы не ищем, возвращаем ok с
court_cases=None.

## 2) Verifier (профиль 'cases', один вызов на пачку)

Проверяет независимо: «кейсы реально по этой статье/теме» (не просто похожие
кейсы вообще). `passed=False` -> `StepResult(fail)` — обычный retry
`Orchestrator`'а, Summarizer вообще не вызывается.

## 3) Summarizer (cheap)

Для каждого кейса однострочное саммари (суть · исход · сумма). Результат:
ctx.data['court_cases'] = [{case_url, case_title, summary_line, outcome, amount}]
— снапшот (URL сохраняются; витрина в SudX в рантайме не ходит).

## Только УЗ

При jurisdiction != 'UZ' шаг пропускается без ошибки: `StepResult(ok)` с
court_cases=None, ноль вызовов LLM/LegalX (граница плана).

## Успех

`ctx.data['court_cases'] = [{case_url, case_title, summary_line, outcome, amount}, ...]`,
`StepResult(ok, verdicts=[verdict_фазы_2])`.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from importer.build.agents import (
    ModelsConfig,
    Summarizer,
    Verdict,
    Verifier,
    load_models_config,
    verifier_model_for,
)
from importer.build.legalx import LegalXClient, get_client
from importer.build.llm_client import AgentLLMClient, AgentLLMError, RunnerAgentLLM
from importer.build.profiles import Profile
from importer.build.steps import ItemContext, StepResult, register_step
from importer.build.steps_norm import DEFAULT_JURISDICTION

if TYPE_CHECKING:  # только тип — импорт по значению создал бы цикл steps_cases<->trace
    from importer.build.trace import Tracer

CASES_PROFILE = Profile(
    name="cases",
    system_prompt=(
        "Ты проверяешь судебные кейсы по статье ответственности за нарушение "
        "конкретного требования комплаенс-чеклиста — только реальные кейсы, "
        "которые действительно иллюстрируют эту статью и это требование."
    ),
    response_schema={"type": "object"},
    tier="mid",
)

CASES_SUMMARY_PROFILE = Profile(
    name="cases",
    system_prompt=(
        "Ты сжимаешь судебный кейс в однострочное резюме: суть нарушения, "
        "исход дела (решение/приговор) и размер штрафа, если есть. "
        "Максимум одна строка, никаких лишних деталей."
    ),
    response_schema={"type": "object"},
    tier="cheap",
)


class CasesStep:
    """Шаговый callable 'cases' (см. докстринг модуля)."""

    def __init__(
        self,
        legalx: LegalXClient,
        llm: AgentLLMClient,
        *,
        jurisdiction: str = DEFAULT_JURISDICTION,
        models: ModelsConfig | None = None,
        profile: Profile = CASES_PROFILE,
        summary_profile: Profile = CASES_SUMMARY_PROFILE,
        tracer: "Tracer | None" = None,
    ):
        self._legalx = legalx
        self._llm = llm
        self._jurisdiction = jurisdiction
        self._models = models or load_models_config()
        self._profile = profile
        self._summary_profile = summary_profile
        self._tracer = tracer
        self._summarizer = Summarizer(llm, self._models, tracer=tracer)

    def __call__(self, ctx: ItemContext) -> StepResult:
        try:
            return self._run(ctx)
        except (AgentLLMError, ValueError) as exc:
            return StepResult(status="fail", error=f"шаг 'cases': {exc}")

    def _run(self, ctx: ItemContext) -> StepResult:
        # Шаг 'cases' работает только для УЗ
        if self._jurisdiction != "UZ":
            ctx.data["court_cases"] = None
            return StepResult(status="ok")

        # Санкции не найдены или пусты — кейсы не ищем
        sanctions = ctx.data.get("sanctions")
        if not sanctions or ctx.data.get("sanctions_not_found"):
            ctx.data["court_cases"] = None
            return StepResult(status="ok")

        # Статья из первой санкции
        article = sanctions[0].get("article")
        if not article:
            ctx.data["court_cases"] = None
            return StepResult(status="ok")

        # Поиск кейсов
        cases = self._legalx.search_cases(article, limit=5)

        # Если кейсов нет — это валидный исход
        if not cases:
            ctx.data["court_cases"] = []
            return StepResult(status="ok")

        # Проверка Verifier'ом: кейсы реально по этой статье/теме
        producer_model = self._models.tiers[self._profile.tier]
        verifier_model = verifier_model_for(producer_model, self._models)
        verifier = Verifier(llm=self._llm, model=verifier_model, tracer=self._tracer)

        # Собираем кейсы кратко для вопроса Verifier'а
        cases_brief = "; ".join(
            f"{case.case_title} ({case.outcome})" for case in cases
        )

        verdict: Verdict = verifier.run(
            question=f"Кейсы реально по статье {article}?",
            fragment=cases_brief,
            source=article,
            profile=self._profile,
        )

        if not verdict.passed:
            return StepResult(
                status="fail",
                verdicts=[verdict],
                error=verdict.reason or "шаг 'cases': верификатор не подтвердил кейсы",
            )

        # Саммаризируем каждый кейс
        result_cases = []
        for case in cases:
            try:
                summary_line = self._summarizer.run(case.summary, self._summary_profile)
            except AgentLLMError as exc:
                return StepResult(
                    status="fail",
                    verdicts=[verdict],
                    error=f"шаг 'cases': саммаризатор падал: {exc}",
                )

            result_cases.append({
                "case_url": case.case_url,
                "case_title": case.case_title,
                "summary_line": summary_line,
                "outcome": case.outcome,
                "amount": case.amount,
            })

        ctx.data["court_cases"] = result_cases
        return StepResult(status="ok", verdicts=[verdict])


def _default_llm_runner(prompt: str, model: str) -> str:
    """Заглушка runner'а для регистрации по умолчанию (см. докстринг
    модуля) — падает только при РЕАЛЬНОМ вызове модели, не при
    импорте/регистрации шага."""
    raise NotImplementedError(
        "Живой LLM-runner для шага 'cases' ещё не подключён — заработает "
        "после пилотного прогона Задачи 27 (см. "
        "importer/build/llm_client.py:RunnerAgentLLM)"
    )


_default_llm = RunnerAgentLLM(_default_llm_runner)
register_step("cases", CasesStep(get_client(), _default_llm))
