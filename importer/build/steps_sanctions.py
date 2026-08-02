"""Шаг 'sanctions' Build-конвейера (Задача 21, ADR-0003 «Блок 2»,
`docs/TARGET_FORMAT.md` §4 «Дополнение 02.08.2026, б) Санкции — структура»).

Один шаг STEP_ORDER, внутри — три фазы (task-21-brief.md, уточнения
контроллера):

## 1) Retriever (профиль 'sanctions', тир 'mid')

Запрос строится из СУТИ требования — `ctx.data['summary']` (шаг 'summary'
уже отработал в обычном порядке STEP_ORDER) либо, если саммари ещё нет
(например, партиальный `rerun_item` начиная не с начала), из
`ctx.data['norm_fragment'].content`; на крайний случай — `ctx.item.expected_item`
(тот же принцип избежания `AttributeError`, что и в остальных шагах) — в
форме «ответственность за нарушение …» (`_build_query` ниже). Итеративность
и переформулировки запроса при пустом результате — уже внутри самого
`Retriever.run` (`agents.py`, `MAX_REFORMULATIONS`), этот шаг вызывает его
ровно один раз с одним запросом, не крутит собственный цикл вопросов (в
отличие от 'norm', где вопросов несколько — `question_writer`).

Исход `not_found` (переформулировки исчерпаны, ничего не нашли) —
`StepResult(ok)` с ПУСТЫМИ `ctx.data['sanctions'] = []` и пометкой
`ctx.data['sanctions_not_found'] = True`: санкция может быть не установлена
— валидный исход уровня 0 TARGET_FORMAT («санкция не установлена»), не
повод ретраить весь шаг. Исход `no_norm` (LLM сигналит, что такой нормы об
ответственности в этой юрисдикции нет) — трактуется ТАК ЖЕ: тоже
`StepResult(ok)` с пустыми `sanctions` и тем же флагом (решение
контроллера: «для санкций различие не критично» — в отличие от 'norm', где
`no_norm` терминален отдельно от `fail`/not_found).

## 2) Verifier (профиль 'sanctions', `verifier_model_for(mid)` — 'expensive')

Проверяет независимо: «фрагмент реально об ответственности по ЭТОМУ
требованию» (не просто похожий текст о санкциях вообще). `fragment` —
найденный текст, `source` — тот же контекст требования, что пошёл в запрос
Retriever'а (summary/norm_fragment/expected_item). `passed=False` ->
`StepResult(fail)` — обычный retry/эскалация `Orchestrator`'а
(`MAX_STEP_RETRIES`), структуризатор (фаза 3) вообще не вызывается.

## 3) Структуризатор (Classifier, тир 'cheap')

Текст ПОДТВЕРЖДЁННОГО фрагмента -> JSON-массив
`[{"article": str, "fine": {"amount": number, "unit": str}, "measure": str|null}]`.
`unit` — СТРОКА из текста фрагмента (БРВ/МРП/AED/...), НЕ хардкод: разные
юрисдикции считают штраф в разных единицах (УЗ — БРВ, КЗ — МРП, ОАЭ — AED),
код шага не привязывается ни к одной из них, просто передаёт то, что вернул
структуризатор (`_sanctions_from_structurer_output` ниже никак не
интерпретирует значение `unit`, только проверяет, что это непустая строка).

Невалидный вывод (не JSON / не массив / пустой массив / элемент без
`article`/`fine.amount`/`fine.unit`) -> один ретрай с указанием ошибки ->
всё ещё невалиден -> `StepResult(fail)` (тот же паттерн `steps_rule.py`
Rule-maker/`steps_scope_lifecycle.py` lifecycle-экстрактора). Вердикт
Verifier'а из фазы 2 (уже полученный к этому моменту) НЕ теряется —
попадает в `StepResult.verdicts` даже при провале структуризатора (тот же
принцип «все вердикты попадают в результат независимо от статуса», что и в
`steps_rule.py`).

## Успех

`ctx.data['sanctions'] = [{"article", "fine": {"amount", "unit"}, "measure"}, ...]`,
`StepResult(ok, verdicts=[verdict_фазы_2])`.

## Почему шаг ловит исключения сам

Тот же принцип, что и во всех остальных шагах (`steps_norm.py`/
`steps_rule.py`/`steps_scope_lifecycle.py`): `Orchestrator._run_from`
вызывает `step_fn(ctx)` через `_call_step` (Задача 20, фикс-раунд) —
страховка ловит НЕОЖИДАННЫЕ исключения, но это последний рубеж, а не замена
дисциплине самого шага. `AgentLLMError`/`ValueError` (мусорный ответ LLM у
Retriever/Verifier — оба сигналят `AgentLLMError`, см. `agents.py`)
перехватываются здесь и превращаются в обычный `StepResult(fail)`.

## Регистрация

Тот же паттерн отсрочки, что и у всех предыдущих шагов: `_default_llm_runner`
падает `NotImplementedError` только при РЕАЛЬНОМ вызове модели, не при
импорте/регистрации шага. Живое подключение — Задача 27.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from importer.build.agents import (
    Classifier,
    ModelsConfig,
    Retriever,
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

if TYPE_CHECKING:  # только тип — импорт по значению создал бы цикл steps_sanctions<->trace
    from importer.build.trace import Tracer

# Форма запроса Retriever'а (уточнение контроллера задачи) — суть требования
# приклеивается ПОСЛЕ этого префикса, см. `_build_query`.
SANCTIONS_QUERY_PREFIX = "ответственность за нарушение"

SANCTIONS_PROFILE = Profile(
    name="sanctions",
    system_prompt=(
        "Ты ищешь норму об ответственности (санкции) за нарушение конкретного "
        "требования комплаенс-чеклиста — статью КоАО/НК/аналога с размером "
        "штрафа и дополнительной мерой (если есть)."
    ),
    response_schema={"type": "object"},
    tier="mid",
)

SANCTIONS_STRUCTURE_PROFILE = Profile(
    name="sanctions",
    system_prompt=(
        "Ты превращаешь текст нормы об ответственности в компактный "
        "JSON-массив санкций по ключу 'sanctions' — по одному элементу на "
        'каждую отдельную санкцию: {"article": "ст. ... КоАО", "fine": '
        '{"amount": число, "unit": "единица штрафа ИЗ ТЕКСТА (например БРВ, '
        'МРП, AED — не придумывай и не переводи в другую единицу)"}, '
        '"measure": "дополнительная мера, если есть, иначе null"}. Ничего не '
        "придумывай от себя: каждая санкция обязана напрямую следовать из "
        "текста фрагмента."
    ),
    response_schema={
        "type": "object",
        "properties": {
            "sanctions": {
                "type": "array",
                "minItems": 1,
                "items": {
                    "type": "object",
                    "properties": {
                        "article": {"type": "string"},
                        "fine": {
                            "type": "object",
                            "properties": {
                                "amount": {"type": "number"},
                                "unit": {"type": "string"},
                            },
                            "required": ["amount", "unit"],
                        },
                        "measure": {"type": ["string", "null"]},
                    },
                    "required": ["article", "fine"],
                },
            }
        },
        "required": ["sanctions"],
    },
    tier="cheap",
)


def _validate_sanction_item(item: object) -> dict | None:
    """Достаёт одну нормализованную санкцию из элемента ответа
    структуризатора либо `None`, если элемент не проходит минимальный
    контракт — сигнал «невалидный вывод -> ретрай»."""
    if not isinstance(item, dict):
        return None
    article = item.get("article")
    if not isinstance(article, str) or not article:
        return None
    fine = item.get("fine")
    if not isinstance(fine, dict):
        return None
    amount = fine.get("amount")
    # bool — подкласс int в Python, {"amount": true} не валидная сумма штрафа.
    if isinstance(amount, bool) or not isinstance(amount, (int, float)):
        return None
    unit = fine.get("unit")
    if not isinstance(unit, str) or not unit:
        return None  # единица ОБЯЗАНА быть в ответе — код её не подставляет
    measure = item.get("measure")
    if measure is not None and not isinstance(measure, str):
        return None
    return {"article": article, "fine": {"amount": amount, "unit": unit}, "measure": measure}


def _sanctions_from_structurer_output(data: object) -> list[dict] | None:
    """Достаёт список нормализованных санкций из ответа структуризатора либо
    `None`, если ответ не проходит контракт (не список/не объект с ключом
    'sanctions' / пуст / хотя бы один элемент невалиден)."""
    if isinstance(data, dict):
        candidate = data.get("sanctions")
    else:
        candidate = data  # на случай голого массива без обёртки {"sanctions": [...]}
    if not isinstance(candidate, list) or len(candidate) == 0:
        return None
    validated: list[dict] = []
    for item in candidate:
        parsed = _validate_sanction_item(item)
        if parsed is None:
            return None
        validated.append(parsed)
    return validated


class SanctionsStep:
    """Шаговый callable 'sanctions' (см. докстринг модуля)."""

    def __init__(
        self,
        legalx: LegalXClient,
        llm: AgentLLMClient,
        *,
        jurisdiction: str = DEFAULT_JURISDICTION,
        models: ModelsConfig | None = None,
        profile: Profile = SANCTIONS_PROFILE,
        structure_profile: Profile = SANCTIONS_STRUCTURE_PROFILE,
        tracer: "Tracer | None" = None,
    ):
        self._llm = llm
        self._jurisdiction = jurisdiction
        self._models = models or load_models_config()
        self._profile = profile
        self._structure_profile = structure_profile
        self._tracer = tracer
        self._retriever = Retriever(legalx, llm, self._models, tracer=tracer)
        self._classifier = Classifier(llm, self._models, tracer=tracer)

    def __call__(self, ctx: ItemContext) -> StepResult:
        try:
            return self._run(ctx)
        except (AgentLLMError, ValueError) as exc:
            return StepResult(status="fail", error=f"шаг 'sanctions': {exc}")

    def _run(self, ctx: ItemContext) -> StepResult:
        context_text = self._context_text(ctx)
        query = f"{SANCTIONS_QUERY_PREFIX} {context_text}"

        result = self._retriever.run(query, self._jurisdiction, self._profile)
        if result.outcome != "found":
            # not_found И no_norm — оба трактуются одинаково (уточнение
            # контроллера: различие не критично для санкций) — санкция
            # просто не установлена, это НЕ fail.
            ctx.data["sanctions"] = []
            ctx.data["sanctions_not_found"] = True
            return StepResult(status="ok")

        fragment = result.fragments[0]
        producer_model = self._models.tiers[self._profile.tier]
        verifier_model = verifier_model_for(producer_model, self._models)
        verifier = Verifier(llm=self._llm, model=verifier_model, tracer=self._tracer)
        verdict: Verdict = verifier.run(
            question="Фрагмент реально об ответственности (санкции) за нарушение именно этого требования?",
            fragment=fragment.content,
            source=context_text,
            profile=self._profile,
        )

        if not verdict.passed:
            return StepResult(
                status="fail",
                verdicts=[verdict],
                error=verdict.reason or "шаг 'sanctions': верификатор не подтвердил фрагмент об ответственности",
            )

        sanctions = self._structure(fragment.content, self._structure_profile)
        if sanctions is None:
            retry_profile = self._profile_with_error(
                self._structure_profile,
                "Предыдущий ответ был невалиден: верни СТРОГО непустой "
                "JSON-массив санкций по ключу 'sanctions', каждый элемент — "
                '{"article": str, "fine": {"amount": число, "unit": str}, '
                '"measure": str|null}.',
            )
            sanctions = self._structure(fragment.content, retry_profile)

        if sanctions is None:
            return StepResult(
                status="fail",
                verdicts=[verdict],
                error=(
                    "шаг 'sanctions': структуризатор дважды вернул невалидный "
                    "вывод (не JSON-массив непустых валидных санкций)"
                ),
            )

        ctx.data["sanctions"] = sanctions
        return StepResult(status="ok", verdicts=[verdict])

    def _structure(self, text: str, profile: Profile) -> list[dict] | None:
        try:
            result = self._classifier.run(text, profile)
        except AgentLLMError:
            return None
        return _sanctions_from_structurer_output(result)

    @staticmethod
    def _context_text(ctx: ItemContext) -> str:
        """Суть требования для запроса Retriever'а и `source` Verifier'а —
        `summary` (шаг 'summary' уже отработал в обычном порядке STEP_ORDER),
        иначе `norm_fragment.content` (партиальный прогон без 'summary'),
        иначе `expected_item` (крайний случай, тот же принцип избежания
        `AttributeError`, что и в остальных шагах)."""
        summary = ctx.data.get("summary")
        if summary:
            return summary
        fragment = ctx.data.get("norm_fragment")
        if fragment is not None:
            return fragment.content
        return ctx.item.expected_item

    @staticmethod
    def _profile_with_error(profile: Profile, error_message: str) -> Profile:
        return Profile(
            name=profile.name,
            system_prompt=f"{profile.system_prompt}\n\n{error_message}",
            response_schema=profile.response_schema,
            tier=profile.tier,
        )


def _default_llm_runner(prompt: str, model: str) -> str:
    """Заглушка runner'а для регистрации по умолчанию (см. докстринг
    модуля) — падает только при РЕАЛЬНОМ вызове модели, не при
    импорте/регистрации шага."""
    raise NotImplementedError(
        "Живой LLM-runner для шага 'sanctions' ещё не подключён — заработает "
        "после пилотного прогона Задачи 27 (см. "
        "importer/build/llm_client.py:RunnerAgentLLM)"
    )


_default_llm = RunnerAgentLLM(_default_llm_runner)
register_step("sanctions", SanctionsStep(get_client(), _default_llm))
