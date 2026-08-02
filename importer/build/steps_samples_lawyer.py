"""Шаги 'samples' и 'lawyer' Build-конвейера (Задача 23, ADR-0003 «Блок 2»,
`docs/miro-agent-flow.csv` строки Samples judge/Template hunter/Verifier
(Samples)/In-house lawyer).

## 'samples' — один шаг STEP_ORDER, внутри — три фазы (task-23-brief.md,
уточнения контроллера)

### 1) Samples judge (Classifier, тир 'mid')

«Нужны ли примеры документов для этого требования?» Вход — контекст
требования (`summary`/`norm_fragment.content`/`expected_item`, тот же приём
`_context_text`, что и `steps_sanctions.py:SanctionsStep._context_text`).
Ответ `{"needed": bool, "document_type": str|null}`.

`needed=False` -> шаг завершается сразу: `ctx.data['templates'] = None`
(шаблоны для ЭТОГО требования не нужны в принципе — не то же самое, что
«нужны, но не нашли», см. семантику ниже), `StepResult(ok)`, Hunter/Verifier
вообще не вызываются.

### 2) Template hunter — веб-поиск (`websearch.WebSearcher.search`)

Запрос строится из `document_type`, который вернул судья (`SAMPLES_QUERY_PREFIX`
+ `document_type`). Пустой результат поиска -> сразу `ctx.data['templates'] =
[]` + `ctx.data['templates_not_found'] = True` -> `StepResult(ok)` (сигнал
менеджеру — витрина покажет «Данных пока нет», TARGET_FORMAT §4 «Дополнение
02.08.2026 в»); НИ ОДНОГО обращения к LLM на этой ветке — тот же экономный
принцип, что и у `SanctionsStep`/`CasesStep` при пустом результате поиска.

Непустой результат -> Hunter (Classifier, тир 'mid') выбирает из находок
ЛУЧШИЙ шаблон -> `{"found": bool, "template": {"name", "source_url", "note"}
|null}`. `found=False` (ни одна находка не тянет на шаблон) -> та же ветка
not_found+флаг, Verifier не вызывается.

### 3) Verifier (профиль 'samples', `verifier_model_for(mid) == 'expensive'`)

Независимо проверяет качество и источник найденного шаблона (актуальность,
официальность источника, соответствие типу документа) — `fragment` — сам
шаблон (JSON), `source` — находки поиска, из которых он выбран. `passed=False`
-> `StepResult(fail)` — обычный retry `Orchestrator`'а.

### Семантика `ctx.data['templates']` (уточнение контроллера)

- `None` — шаблоны для этого требования НЕ нужны (судья: `needed=False`);
- `[]` (+ `ctx.data['templates_not_found']=True`) — нужны, но не найдены
  (пустой поиск ИЛИ Hunter не выбрал ни одной находки);
- `[{"name", "source_url", "note"}]` — найдены и подтверждены Verifier'ом.

## 'lawyer' — In-house lawyer, один Classifier-вызов (тир 'expensive'), БЕЗ Verifier

`docs/miro-agent-flow.csv` строка In-house lawyer не несёт отдельной
Verifier-колонки (в отличие от строки Verifier (Samples)) — решение
контроллера задачи: `StepResult.verdicts` у 'lawyer' всегда пуст, независимая
проверка на этот шаг не вешается.

Вход — вся накопленная карточка айтема из `ctx.data` (`summary`, `sanctions`,
`lifecycle`, `rules` — что уже успели положить предыдущие шаги STEP_ORDER;
частичный `rerun_item`, начатый не с начала, может не иметь части полей —
код читает их через `.get(...)` с безопасными дефолтами, не `AttributeError`,
тот же принцип, что `_map_item_from_ctx` в `steps_norm.py`). Ответ:
`{"verdict": str, "steps": [str, ...], "status_note": str|null}` ->
`ctx.data['lawyer_instruction'] = {"verdict", "steps"}`,
`ctx.data['status_note']` — отдельно.

### `status_note` — код детерминированно решает, обязателен ли он

`docs/miro-agent-flow.csv` (Assembler): «что успеть до даты X» кладётся в
detailed info, когда есть БЛИЖАЙШАЯ будущая дата. Код (не LLM) вычисляет
`_closest_future_lifecycle_date` по `ctx.data['lifecycle']['effective_from']`/
`['valid_to']` относительно "сегодня" (`today` — параметр конструктора для
детерминированных тестов, `date.today()` по умолчанию) и включает в промпт
явную инструкцию — заполнить `status_note` (если дата есть) либо вернуть
`status_note: null` (если дат нет). Ответ, который расходится с этим
требованием (непустой `status_note` без близкой даты, либо пустой/null
`status_note` при наличии близкой даты) — невалидный ответ, тот же путь
ретрая, что и обычный невалидный контракт: не позволяем LLM ни выдумать
несуществующий дедлайн, ни промолчать про реальный.

Невалидный ответ (любая из причин выше) -> один ретрай с указанием ошибки ->
всё ещё невалиден -> `StepResult(fail)` (тот же паттерн, что и у Rule-maker/
`ScopeStep` — единственный producer без Verifier).

## Почему шаги ловят исключения сами

Тот же принцип, что и во всех остальных шагах (`steps_sanctions.py`/
`steps_scope_lifecycle.py`): `Orchestrator._run_from` вызывает `step_fn(ctx)`
через `_call_step` (страховка на неожиданные исключения — последний рубеж, не
замена дисциплине самого шага). `AgentLLMError`/`ValueError` перехватываются
здесь и превращаются в обычный `StepResult(fail)`.

## Регистрация

Тот же паттерн отсрочки, что и у всех предыдущих шагов: `_default_llm_runner`
падает `NotImplementedError` только при РЕАЛЬНОМ вызове модели, живой
веб-поиск (`websearch.get_web_searcher()`, дефолт-бэкенд `live`) — тот же
принцип у `_LiveWebSearcher`. Живое подключение обоих — Задача 27.
"""
from __future__ import annotations

import json
from datetime import date

from importer.build.agents import (
    Classifier,
    ModelsConfig,
    Verdict,
    Verifier,
    load_models_config,
    verifier_model_for,
)
from importer.build.llm_client import AgentLLMClient, AgentLLMError, RunnerAgentLLM
from importer.build.profiles import Profile
from importer.build.steps import ItemContext, StepResult, register_step
from importer.build.websearch import WebSearcher, get_web_searcher

# ══════════════════════════════════════════════════════════════════════════
# 'samples'
# ══════════════════════════════════════════════════════════════════════════

# Форма запроса Template hunter'а — document_type судьи приклеивается ПОСЛЕ
# этого префикса (тот же приём, что и SANCTIONS_QUERY_PREFIX в steps_sanctions.py).
SAMPLES_QUERY_PREFIX = "образец документа:"

SAMPLES_JUDGE_PROFILE = Profile(
    name="samples",
    system_prompt=(
        "Ты решаешь, нужен ли для этого требования комплаенс-чеклиста "
        "образец/шаблон документа (например, форма заявления, бланк "
        "декларации). Если да — укажи тип документа (document_type) простым "
        "языком, по которому потом будет вестись веб-поиск шаблона. Если "
        "требование не подразумевает заполнение конкретной формы — "
        "needed=false, document_type=null."
    ),
    response_schema={
        "type": "object",
        "properties": {
            "needed": {"type": "boolean"},
            "document_type": {"type": ["string", "null"]},
        },
        "required": ["needed", "document_type"],
    },
    tier="mid",
)

SAMPLES_HUNTER_PROFILE = Profile(
    name="samples",
    system_prompt=(
        "Ты выбираешь из находок веб-поиска ЛУЧШИЙ образец/шаблон нужного "
        "документа — предпочитай официальные источники (гос. органы, "
        "профильные ведомства) более новым и точно подходящим по типу "
        'документа. Если ни одна находка не годится — верни {"found": false, '
        '"template": null}. Иначе — {"found": true, "template": {"name": '
        '"...", "source_url": "url находки", "note": "почему этот источник '
        'подходит"}}.'
    ),
    response_schema={
        "type": "object",
        "properties": {
            "found": {"type": "boolean"},
            "template": {
                "type": ["object", "null"],
                "properties": {
                    "name": {"type": "string"},
                    "source_url": {"type": "string"},
                    "note": {"type": ["string", "null"]},
                },
                "required": ["name", "source_url"],
            },
        },
        "required": ["found", "template"],
    },
    tier="mid",
)

SAMPLES_PROFILE = Profile(
    name="samples",
    system_prompt=(
        "Ты проверяешь качество и источник найденного шаблона документа: "
        "актуальность, официальность источника, соответствие искомому типу "
        "документа."
    ),
    response_schema={"type": "object"},
    tier="mid",
)


def _context_text(ctx: ItemContext) -> str:
    """Суть требования для судьи 'samples' — `summary` (шаг 'summary' уже
    отработал), иначе `norm_fragment.content` (партиальный прогон), иначе
    `expected_item` (крайний случай) — тот же приём, что и
    `steps_sanctions.py:SanctionsStep._context_text`."""
    summary = ctx.data.get("summary")
    if summary:
        return summary
    fragment = ctx.data.get("norm_fragment")
    if fragment is not None:
        return fragment.content
    return ctx.item.expected_item


def _validate_judge(data: object) -> dict | None:
    """Достаёт `{"needed", "document_type"}` из ответа судьи либо `None`,
    если ответ не проходит контракт — сигнал «невалидный ответ»."""
    if not isinstance(data, dict):
        return None
    needed = data.get("needed")
    if not isinstance(needed, bool):
        return None
    document_type = data.get("document_type")
    if document_type is not None and not isinstance(document_type, str):
        return None
    return {"needed": needed, "document_type": document_type}


def _validate_hunt(data: object) -> dict | None:
    """Достаёт `{"found", "template"}` из ответа Hunter'а либо `None`, если
    ответ не проходит контракт — сигнал «невалидный ответ». При `found=True`
    `template` обязан быть объектом с непустыми `name`/`source_url`."""
    if not isinstance(data, dict):
        return None
    found = data.get("found")
    if not isinstance(found, bool):
        return None
    if not found:
        return {"found": False, "template": None}
    template = data.get("template")
    if not isinstance(template, dict):
        return None
    name = template.get("name")
    source_url = template.get("source_url")
    if not isinstance(name, str) or not name:
        return None
    if not isinstance(source_url, str) or not source_url:
        return None
    note = template.get("note")
    if note is not None and not isinstance(note, str):
        return None
    return {"found": True, "template": {"name": name, "source_url": source_url, "note": note}}


class SamplesStep:
    """Шаговый callable 'samples' (см. докстринг модуля)."""

    def __init__(
        self,
        searcher: WebSearcher,
        llm: AgentLLMClient,
        *,
        models: ModelsConfig | None = None,
        profile: Profile = SAMPLES_PROFILE,
        judge_profile: Profile = SAMPLES_JUDGE_PROFILE,
        hunter_profile: Profile = SAMPLES_HUNTER_PROFILE,
    ):
        self._searcher = searcher
        self._llm = llm
        self._models = models or load_models_config()
        self._profile = profile
        self._judge_profile = judge_profile
        self._hunter_profile = hunter_profile
        self._classifier = Classifier(llm, self._models)

    def __call__(self, ctx: ItemContext) -> StepResult:
        try:
            return self._run(ctx)
        except (AgentLLMError, ValueError) as exc:
            return StepResult(status="fail", error=f"шаг 'samples': {exc}")

    def _run(self, ctx: ItemContext) -> StepResult:
        context_text = _context_text(ctx)

        judge_raw = self._classifier.run(context_text, self._judge_profile)
        judged = _validate_judge(judge_raw)
        if judged is None:
            raise ValueError(f"судья 'samples' вернул невалидный ответ: {judge_raw!r}")

        if not judged["needed"]:
            ctx.data["templates"] = None
            return StepResult(status="ok")

        document_type = judged["document_type"] or context_text
        query = f"{SAMPLES_QUERY_PREFIX} {document_type}"
        results = self._searcher.search(query)

        if not results:
            ctx.data["templates"] = []
            ctx.data["templates_not_found"] = True
            return StepResult(status="ok")

        hunt_raw = self._classifier.run(_results_text(results), self._hunter_profile)
        hunted = _validate_hunt(hunt_raw)
        if hunted is None:
            raise ValueError(f"Template hunter вернул невалидный ответ: {hunt_raw!r}")

        if not hunted["found"]:
            ctx.data["templates"] = []
            ctx.data["templates_not_found"] = True
            return StepResult(status="ok")

        template = hunted["template"]

        producer_model = self._models.tiers[self._profile.tier]
        verifier_model = verifier_model_for(producer_model, self._models)
        verifier = Verifier(llm=self._llm, model=verifier_model)
        verdict: Verdict = verifier.run(
            question="Шаблон качественный и из официального/актуального источника для этого типа документа?",
            fragment=json.dumps(template, ensure_ascii=False, sort_keys=True),
            source=_results_text(results),
            profile=self._profile,
        )

        if not verdict.passed:
            return StepResult(
                status="fail",
                verdicts=[verdict],
                error=verdict.reason or "шаг 'samples': верификатор не подтвердил шаблон",
            )

        ctx.data["templates"] = [template]
        return StepResult(status="ok", verdicts=[verdict])


def _results_text(results: list[dict]) -> str:
    return json.dumps(results, ensure_ascii=False)


# ══════════════════════════════════════════════════════════════════════════
# 'lawyer'
# ══════════════════════════════════════════════════════════════════════════

_LIFECYCLE_FUTURE_DATE_FIELDS = ("effective_from", "valid_to")

LAWYER_PROFILE = Profile(
    name="lawyer",  # вне ProfileName Literal в profiles.py — тот же прецедент,
    # что и 'scope'/'rule' в steps_scope_lifecycle.py/steps_rule.py.
    system_prompt=(
        "Ты — юрист-инхаус компании. По собранной карточке требования "
        "комплаенс-чеклиста (суть, санкции, жизненный цикл, машинные "
        'правила) сформулируй: verdict — короткий вывод о необходимости '
        'имплементации требования бизнесом, steps — непустой список '
        'конкретных шагов "что делать". Ничего не придумывай от себя: '
        "опирайся только на данные карточки."
    ),
    response_schema={
        "type": "object",
        "properties": {
            "verdict": {"type": "string"},
            "steps": {"type": "array", "items": {"type": "string"}, "minItems": 1},
            "status_note": {"type": ["string", "null"]},
        },
        "required": ["verdict", "steps", "status_note"],
    },
    tier="expensive",
)


def _closest_future_lifecycle_date(lifecycle: dict | None, today: date) -> tuple[str, date] | None:
    """Ближайшая БУДУЩАЯ дата среди `effective_from`/`valid_to` карточки
    жизненного цикла (`docstring` модуля — только эти два поля, не
    `transition_until`, решение контроллера задачи), либо `None`, если таких
    дат нет (лежат в прошлом, отсутствуют, либо `lifecycle` вообще не
    положен в `ctx` — партиальный `rerun_item` без шага 'lifecycle')."""
    if not lifecycle:
        return None
    candidates: list[tuple[str, date]] = []
    for field_name in _LIFECYCLE_FUTURE_DATE_FIELDS:
        raw = lifecycle.get(field_name)
        if not raw:
            continue
        try:
            parsed = date.fromisoformat(raw)
        except (TypeError, ValueError):
            continue
        if parsed > today:
            candidates.append((field_name, parsed))
    if not candidates:
        return None
    return min(candidates, key=lambda pair: pair[1])


def _validate_lawyer(data: object, *, requires_status_note: bool) -> dict | None:
    """Достаёт `{"verdict", "steps", "status_note"}` из ответа юриста либо
    `None`, если ответ не проходит контракт — сигнал «невалидный ответ»:
    базовый контракт (непустой `verdict`, непустой список строк `steps`), И
    `status_note` обязан соответствовать `requires_status_note` (код,
    посчитанный из `ctx.data['lifecycle']`, а не мнение LLM — докстринг
    модуля)."""
    if not isinstance(data, dict):
        return None
    verdict = data.get("verdict")
    if not isinstance(verdict, str) or not verdict:
        return None
    steps = data.get("steps")
    if not isinstance(steps, list) or len(steps) == 0:
        return None
    if not all(isinstance(step, str) and step for step in steps):
        return None
    status_note = data.get("status_note")
    if requires_status_note:
        if not isinstance(status_note, str) or not status_note:
            return None
    else:
        if status_note is not None:
            return None
    return {"verdict": verdict, "steps": steps, "status_note": status_note}


class LawyerStep:
    """Шаговый callable 'lawyer' (см. докстринг модуля)."""

    def __init__(
        self,
        llm: AgentLLMClient,
        *,
        models: ModelsConfig | None = None,
        profile: Profile = LAWYER_PROFILE,
        today: date | None = None,
    ):
        self._llm = llm
        self._models = models or load_models_config()
        self._profile = profile
        self._classifier = Classifier(llm, self._models)
        self._today = today  # инъекция "сегодня" — детерминированные тесты близкой даты

    def __call__(self, ctx: ItemContext) -> StepResult:
        try:
            return self._run(ctx)
        except (AgentLLMError, ValueError) as exc:
            return StepResult(status="fail", error=f"шаг 'lawyer': {exc}")

    def _run(self, ctx: ItemContext) -> StepResult:
        today = self._today or date.today()
        close_date = _closest_future_lifecycle_date(ctx.data.get("lifecycle"), today)
        requires_status_note = close_date is not None
        text = self._card_text(ctx)

        profile = self._make_profile(close_date)
        result = self._extract(text, profile, requires_status_note)
        if result is None:
            retry_profile = self._make_profile(
                close_date,
                error_message=(
                    "Предыдущий ответ был невалиден: верни СТРОГО JSON "
                    '{"verdict": str, "steps": [str, ...] (непустой список), '
                    '"status_note": str|null}; '
                    + (
                        "status_note ОБЯЗАН быть непустой строкой — что "
                        f"успеть сделать до {close_date[1].isoformat()}."
                        if requires_status_note
                        else "status_note ОБЯЗАН быть строго null — близких "
                        "будущих дат в карточке нет."
                    )
                ),
            )
            result = self._extract(text, retry_profile, requires_status_note)

        if result is None:
            return StepResult(
                status="fail",
                error=(
                    "шаг 'lawyer': дважды вернул невалидный ответ (не "
                    "соответствует контракту verdict/steps/status_note)"
                ),
            )

        ctx.data["lawyer_instruction"] = {"verdict": result["verdict"], "steps": result["steps"]}
        ctx.data["status_note"] = result["status_note"]
        return StepResult(status="ok")

    def _extract(self, text: str, profile: Profile, requires_status_note: bool) -> dict | None:
        try:
            result = self._classifier.run(text, profile)
        except AgentLLMError:
            # Мусорный (не-JSON) ответ — тоже "невалидный ответ" в терминах
            # ретрая, а не отдельный путь: тот же приём, что и
            # `RuleStep._make_rules` в steps_rule.py (в отличие от
            # `LifecycleStep._extract`, где невалидный формат даты — уже
            # валидный JSON, до `AgentLLMError` дело не доходит).
            return None
        return _validate_lawyer(result, requires_status_note=requires_status_note)

    def _make_profile(self, close_date: tuple[str, date] | None, error_message: str = "") -> Profile:
        system_prompt = self._profile.system_prompt
        if close_date is not None:
            field_name, when = close_date
            system_prompt += (
                f"\n\nВ карточке есть близкая БУДУЩАЯ дата жизненного цикла "
                f"({field_name} = {when.isoformat()}) — обязательно заполни "
                "status_note: что бизнесу успеть сделать до этой даты."
            )
        else:
            system_prompt += (
                "\n\nБлизких будущих дат жизненного цикла в карточке нет — "
                "status_note строго null."
            )
        if error_message:
            system_prompt = f"{system_prompt}\n\n{error_message}"
        return Profile(
            name=self._profile.name,
            system_prompt=system_prompt,
            response_schema=self._profile.response_schema,
            tier=self._profile.tier,
        )

    @staticmethod
    def _card_text(ctx: ItemContext) -> str:
        """Карточка требования в текст для юриста — то, что уже накопили
        предыдущие шаги STEP_ORDER (`ctx.data`), с безопасными дефолтами:
        партиальный `rerun_item`, начатый сразу с 'lawyer', может не иметь
        части полей (докстринг модуля)."""
        parts = [f"Требование: {ctx.item.expected_item}"]
        summary = ctx.data.get("summary")
        if summary:
            parts.append(f"Суть: {summary}")
        sanctions = ctx.data.get("sanctions")
        if sanctions:
            parts.append(f"Санкции: {json.dumps(sanctions, ensure_ascii=False)}")
        lifecycle = ctx.data.get("lifecycle")
        if lifecycle:
            parts.append(f"Жизненный цикл: {json.dumps(lifecycle, ensure_ascii=False)}")
        rules = ctx.data.get("rules")
        if rules:
            parts.append(f"Машинные правила: {json.dumps(rules, ensure_ascii=False)}")
        return "\n".join(parts)


# ══════════════════════════════════════════════════════════════════════════
# Регистрация (см. докстринг модуля)
# ══════════════════════════════════════════════════════════════════════════


def _default_llm_runner(prompt: str, model: str) -> str:
    """Заглушка runner'а для регистрации по умолчанию — падает только при
    РЕАЛЬНОМ вызове модели, не при импорте/регистрации шага."""
    raise NotImplementedError(
        "Живой LLM-runner для шагов 'samples'/'lawyer' ещё не подключён — "
        "заработает после пилотного прогона Задачи 27 (см. "
        "importer/build/llm_client.py:RunnerAgentLLM)"
    )


_default_llm = RunnerAgentLLM(_default_llm_runner)
register_step("samples", SamplesStep(get_web_searcher(), _default_llm))
register_step("lawyer", LawyerStep(_default_llm))
