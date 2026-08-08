"""Шаг 'rule' Build-конвейера (Задача 19, ADR-0003 решение 5: «критическая
точка» Rule-maker → Verifier).

## ПРИОСТАНОВЛЕН (06.08.2026, поправка 4 к ADR-0003, план фотоконтроля §3)

Роль Rule-maker приостановлена до этапа 6 плана фотоконтроля: шаг — БЕЗУСЛОВНЫЙ
no-op, ни одного вызова LLM, ни одной записи в `requirement_rules` (таблица
объявлена deprecated). Источник правды машинных правил — YAML-пакеты
`config/requirements/*.yaml` в `inspectorx-vision` (решение владельца по
развилке 5, `PHOTOCONTROL_DECISIONS.md`). На этапе 6 шаг вернётся в другой
роли: генератор PR-кандидатов в YAML-пакет, не писатель в базу. Класс
`RuleStep._run` и его тесты сохранены под skip как эталон поведения для
возвращения роли. Всё, что ниже по докстрингу, описывает приостановленный
LLM-путь.

Rule-maker — `Classifier` (`agents.py`) в роли producer'а, тир `mid`
(ADR-0003 решение 9: «Средний = Retriever, Vision, Rule-maker»). Он читает
ПЕРВОИСТОЧНИК нормы — `ctx.data['norm_fragment'].content`, НЕ `summary`
(решение контроллера задачи, `task-19-brief.md`: саммари — уже упрощение
человеку, а машинное правило обязано опираться на исходный текст, тот же
принцип, что заставил `SummaryStep` в `steps_norm.py` читать `norm_fragment`,
а не наоборот) — и превращает его в JSON-массив правил вида
`{"field": "состав", "lang": "uz", "required": true}` /
`{"barcode": "EAN-13"}`. Невалидный вывод (не JSON, не массив, пустой
массив, элементы — не объекты) → один ретрай с указанием ошибки → всё ещё
невалиден → `StepResult(fail)` (тот же паттерн, что и невалидный
`category_slug` в `steps_classify.py`).

## Шаг применяется не ко всем айтемам

Машинные правила осмысленны только для категории маркировки/упаковки
(`category_slug == 'marking'`): у санитарного или таможенного требования,
например, физически нет «поля этикетки», которое можно бы проверить
фото-чеком — это норма, а не дефект. Поэтому для любой ДРУГОЙ категории
(включая отсутствие `category_slug` в контексте вовсе — например, партиальный
`rerun_item` не с начала) шаг — не fail, а осознанный no-op:
`StepResult(ok)` с пустым `ctx.data['rules'] = []` и пометкой
`ctx.data['skipped_rule_step'] = True`, ноль обращений к LLM.
`category_slug` берётся из `ctx.data` (положен туда шагом 'category',
`steps_classify.py`, который в STEP_ORDER идёт прямо перед 'rule') — НЕ из
`ctx.item.category_slug` (черновая классификация Cartographer'а из карты,
см. докстринг `steps_norm.py:_map_item_from_ctx`).

## Verifier — критическая точка (ADR-0003 решение 5)

«Кривое правило = кривой фото-чек пользователю, а не просто неточный абзац»
(ADR-0003) → верификация здесь строже, чем у любого другого шага: не один
общий вердикт на весь список, а ОТДЕЛЬНЫЙ вызов `Verifier` на КАЖДОЕ
правило (вопрос «правило точно соответствует норме?», `fragment` — само
правило, `source` — исходный текст нормы). Правило, которое `Verifier`
отклонил, исключается; но если исключено ХОТЯ БЫ одно правило из
сгенерированного набора — весь `StepResult` уходит в `fail`, а не только
список без этого правила (решение контроллера: частично проверенный набор
— не то же самое, что подтверждённый набор целиком; консервативная
политика — выбраковка всего набора и ретрай ЦЕЛОГО шага оркестратором, не
публикация того, что уже подтвердилось). После `MAX_STEP_RETRIES=3`
провалов подряд `Orchestrator` эскалирует айтем в `needs_attention` —
обычный путь `Orchestrator._run_from` (тот же принцип, что и not_found у
'norm' в `steps_norm.py`), шаг про эскалацию ничего не знает.

Все вердикты (и pass, и fail) попадают в `StepResult.verdicts` независимо
от итогового статуса шага.

## Контракт `ItemContext.data`

Вход:
- `category_slug` (положен шагом 'category') — если не `'marking'` (в т.ч.
  отсутствует), контракт ниже не действует, шаг сразу возвращает skip-ok;
- `norm_fragment` (`NormFragment`, положен шагом 'norm') — обязателен при
  `category_slug == 'marking'`; отсутствует → `StepResult(fail)` (шаг
  'norm' ещё не отработал, тот же паттерн, что и `SummaryStep`).

Выход (только при `status == 'ok'`):
- `rules: list[{"rule": dict, "verified": True}]` — ТОЛЬКО подтверждённые
  правила (`verified=True` — единственное значение, которое сюда попадает:
  до pass Verifier'а правило в `ctx.data` не появляется, а если хоть одно
  отклонено — не появляется целиком набор). Запись в `requirement_rules`
  (таблица БД) — НЕ здесь, а на шаге 'load' (Задача 26); этот шаг только
  копит проверенные правила в in-memory контексте прогона.

## Почему шаг ловит исключения сам

Тот же принцип, что и в `steps_norm.py`/`steps_classify.py`:
`Orchestrator._run_from` вызывает `step_fn(ctx)` без try/except вокруг
вызова, поэтому необработанное исключение прервало бы весь `run_group`
(все айтемы прогона), а не только текущий айтем. `AgentLLMError`/
`ValueError` (мусорный ответ LLM у `Verifier`) здесь перехватываются и
превращаются в обычный `StepResult(fail)`.

## Регистрация

Тот же паттерн отсрочки, что и `steps_norm.py`/`steps_classify.py`:
`_default_llm_runner` падает `NotImplementedError` только при РЕАЛЬНОМ
вызове модели, не при импорте/регистрации шага. Живое подключение —
Задача 27.
"""
from __future__ import annotations

import json
from typing import TYPE_CHECKING

from importer.build.agents import (
    Classifier,
    ModelsConfig,
    Verdict,
    Verifier,
    load_models_config,
    verifier_model_for,
)
from importer.build.legalx import NormFragment
from importer.build.llm_client import AgentLLMClient, AgentLLMError, RunnerAgentLLM
from importer.build.profiles import Profile
from importer.build.steps import ItemContext, StepResult, register_step

if TYPE_CHECKING:  # только тип — импорт по значению создал бы цикл steps_rule<->trace
    from importer.build.trace import Tracer

# Единственная категория, для которой машинные правила фото-чека вообще
# имеют смысл (решение контроллера задачи) — для остальных шаг skip-ok.
MARKING_CATEGORY_SLUG = "marking"

RULE_PROFILE = Profile(
    name="rule",
    system_prompt=(
        "Ты превращаешь текст нормы права о маркировке/упаковке в "
        "машинно-проверяемые правила для фото-чека этикетки — компактные "
        'JSON-объекты вида {"field": "состав", "lang": "uz", "required": true} '
        'или {"barcode": "EAN-13"}. Правил может быть несколько — по одному '
        "на каждое проверяемое условие нормы. Ничего не придумывай от себя: "
        "каждое правило обязано напрямую следовать из текста нормы."
    ),
    response_schema={
        "type": "object",
        "properties": {
            "rules": {
                "type": "array",
                "minItems": 1,
                "items": {"type": "object"},
            }
        },
        "required": ["rules"],
    },
    tier="mid",
)


def _rules_from_maker_output(data: object) -> list[dict] | None:
    """Достаёт список правил из ответа Rule-maker'а либо `None`, если ответ
    не проходит минимальный контракт (не список / пуст / элементы — не
    объекты) — сигнал «невалидный вывод → ретрай»."""
    if isinstance(data, dict):
        candidate = data.get("rules")
    else:
        candidate = data  # на случай голого массива без обёртки {"rules": [...]}
    if not isinstance(candidate, list) or len(candidate) == 0:
        return None
    if not all(isinstance(rule, dict) for rule in candidate):
        return None
    return candidate


class RuleStep:
    """Шаговый callable 'rule' (см. докстринг модуля)."""

    def __init__(
        self,
        llm: AgentLLMClient,
        *,
        models: ModelsConfig | None = None,
        profile: Profile = RULE_PROFILE,
        tracer: "Tracer | None" = None,
    ):
        self._llm = llm
        self._models = models or load_models_config()
        self._profile = profile
        self._tracer = tracer
        self._maker = Classifier(llm, self._models, tracer=tracer)

    def __call__(self, ctx: ItemContext) -> StepResult:
        # Приостановка Rule-maker (см. заголовок докстринга модуля):
        # безусловный no-op для ЛЮБОЙ категории, включая 'marking'.
        ctx.data["rules"] = []
        ctx.data["skipped_rule_step"] = True
        return StepResult(status="ok")

    def _suspended_llm_path(self, ctx: ItemContext) -> StepResult:
        """Приостановленный LLM-путь шага (бывший `__call__`). Не вызывается;
        сохранён как эталон для возвращения роли на этапе 6."""
        category_slug = ctx.data.get("category_slug")
        if category_slug != MARKING_CATEGORY_SLUG:
            ctx.data["rules"] = []
            ctx.data["skipped_rule_step"] = True
            return StepResult(status="ok")

        norm_fragment = ctx.data.get("norm_fragment")
        if norm_fragment is None:
            return StepResult(
                status="fail",
                error=(
                    "шаг 'rule': в item_ctx нет 'norm_fragment' — шаг 'norm' "
                    "ещё не отработал"
                ),
            )

        try:
            return self._run(ctx, norm_fragment)
        except (AgentLLMError, ValueError) as exc:
            return StepResult(status="fail", error=f"шаг 'rule': {exc}")

    def _run(self, ctx: ItemContext, norm_fragment: NormFragment) -> StepResult:
        rules = self._make_rules(norm_fragment.content, self._profile)
        if rules is None:
            retry_profile = self._profile_with_error(
                "Предыдущий ответ был невалиден: верни СТРОГО непустой "
                "JSON-массив правил по ключу 'rules'."
            )
            rules = self._make_rules(norm_fragment.content, retry_profile)
        if rules is None:
            return StepResult(
                status="fail",
                error=(
                    "шаг 'rule': Rule-maker дважды вернул невалидный вывод "
                    "(не JSON-массив непустых правил-объектов)"
                ),
            )

        producer_model = self._models.tiers[self._profile.tier]
        verifier_model = verifier_model_for(producer_model, self._models)
        verifier = Verifier(llm=self._llm, model=verifier_model, tracer=self._tracer)

        verdicts: list[Verdict] = []
        verified_rules: list[dict] = []
        any_rejected = False

        for index, rule in enumerate(rules, start=1):
            try:
                verdict = verifier.run(
                    question="Правило точно соответствует норме (не искажает и не додумывает)?",
                    fragment=json.dumps(rule, ensure_ascii=False, sort_keys=True),
                    source=norm_fragment.content,
                    profile=self._profile,
                )
            except (AgentLLMError, ValueError) as exc:
                # Исключение здесь НЕ должно долетать до внешнего
                # try/except в __call__ — тот вернул бы fail с ПУСТЫМИ
                # verdicts, стерев уже собранные к этому моменту вердикты
                # предыдущих правил (фикс-раунд ревью Задачи 19: докстринг
                # обещает «все вердикты попадают в StepResult.verdicts
                # независимо от статуса» — это обязано быть правдой и при
                # обрыве цикла на середине, не только при штатном fail).
                return StepResult(
                    status="fail",
                    verdicts=verdicts,
                    error=f"шаг 'rule': verifier error on rule {index}: {exc}",
                )
            verdicts.append(verdict)
            if verdict.passed:
                verified_rules.append({"rule": rule, "verified": True})
            else:
                any_rejected = True

        if any_rejected:
            # Консервативная политика «критической точки» (ADR-0003 решение
            # 5, докстринг модуля): исключение ХОТЯ БЫ одного правила
            # бракует весь набор — не публикуем частично проверенный
            # чек-лист.
            return StepResult(
                status="fail",
                verdicts=verdicts,
                error=(
                    "шаг 'rule': верификатор отклонил хотя бы одно из "
                    f"{len(rules)} правил — весь набор бракуется"
                ),
            )

        ctx.data["rules"] = verified_rules
        return StepResult(status="ok", verdicts=verdicts)

    def _make_rules(self, text: str, profile: Profile) -> list[dict] | None:
        try:
            result = self._maker.run(text, profile)
        except AgentLLMError:
            return None
        return _rules_from_maker_output(result)

    def _profile_with_error(self, error_message: str) -> Profile:
        return Profile(
            name=self._profile.name,
            system_prompt=f"{self._profile.system_prompt}\n\n{error_message}",
            response_schema=self._profile.response_schema,
            tier=self._profile.tier,
        )


def _default_llm_runner(prompt: str, model: str) -> str:
    """Заглушка runner'а для регистрации по умолчанию (см. докстринг
    модуля) — падает только при РЕАЛЬНОМ вызове модели, не при
    импорте/регистрации шага."""
    raise NotImplementedError(
        "Живой LLM-runner для шага 'rule' ещё не подключён — заработает "
        "после пилотного прогона Задачи 27 (см. "
        "importer/build/llm_client.py:RunnerAgentLLM)"
    )


_default_llm = RunnerAgentLLM(_default_llm_runner)
register_step("rule", RuleStep(_default_llm))
