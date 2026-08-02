"""Шаги 'norm' и 'summary' Build-конвейера (Задача 17, ADR-0003, «Блок 2»).

Оба шага используют generic-агентов `agents.py` (Retriever/Verifier/
Summarizer) через профиль конкретного шага. Профили шагов — здесь: докстринг
`profiles.py` явно оставляет их на "Задачи 17+" ("конкретные профили шагов
(norm, label, sanctions, cases, samples, translation) в этой задаче не
создаются — их вводят Задачи 17+"), а сам `register_profile`/`get_profile`
— опциональный хелпер, не обязательный контракт; здесь профили — простые
модульные константы, реестр `profiles.py` не трогаем.

## 'norm' (первый шаг STEP_ORDER)

`question_writer.write_questions` генерирует уточняющие вопросы по MapItem
айтема -> на каждый вопрос `Retriever` (профиль `norm`, тир `mid`) ищет
норму в LegalX -> найденный фрагмент проверяет независимый `Verifier` (тир
`expensive` — `verifier_model_for('mid') == 'expensive'`, правило Блока 2).

Агрегация исходов по всем вопросам айтема (решение контроллера задачи,
`task-17-brief.md`):
- хотя бы один вопрос дал `found` + `Verdict.passed=True` -> `StepResult(ok)`,
  найденный фрагмент и его реквизиты кладутся в `ItemContext.data` (ключи
  `norm_*`) для следующего шага ('summary' ниже, и потенциально других шагов
  STEP_ORDER, которым тоже нужен исходный фрагмент);
- ВСЕ вопросы дали `no_norm` -> `StepResult(no_norm)` — терминальный
  валидный исход (легален только от шага 'norm', см. `orchestrator.py`);
- иначе (есть `not_found`, или фрагмент нашёлся, но `Verifier` не пропустил
  ни один вопрос) -> `StepResult(fail)`. Это и есть механика брифовского
  "not_found -> needs_attention": сам шаг лишь возвращает `fail`, а
  `needs_attention` после `MAX_STEP_RETRIES` подряд — обычный путь
  `Orchestrator._run_from` (`orchestrator.py`), шаг про это ничего не знает.

## 'summary' (второй шаг STEP_ORDER, сразу после 'norm')

Читает `ItemContext.data['norm_fragment']`, который положил туда шаг 'norm'
ЭТОГО ЖЕ прогона (`ItemContext.data` — только in-memory scratch одного
прогона, см. докстринг `steps.py`) -> `Summarizer` (тир `cheap`) сжимает
фрагмент простым языком -> независимый `Verifier`
(`verifier_model_for('cheap') == 'expensive'`) проверяет, что саммари не
искажает норму и ничего не добавляет от себя — тем же приёмом, что и у
'norm': саммари передаётся `Verifier`'у как `fragment`, а оригинальный текст
нормы — как `source` (независимая проверка соответствия источнику, а не
рассуждения producer'а, которых `Verifier.run` физически не принимает).
`passed` -> саммари в `ItemContext.data['summary']`, `StepResult(ok)`;
`passed=False` -> `StepResult(fail)`. Если 'norm' не положил фрагмент в
контекст (шаг вызван не по порядку — например, `rerun_item` начиная сразу с
'summary') — тоже `StepResult(fail)`, а не `AttributeError`.

## Почему шаги ловят исключения сами, а не дают им всплыть

`Orchestrator._run_from` (`orchestrator.py`) вызывает `step_fn(ctx)` БЕЗ
try/except вокруг вызова — необработанное исключение прервало бы весь
`run_group` (все айтемы прогона), а не только текущий айтем. Поэтому
`AgentLLMError`/`ValueError` (`question_writer` после исчерпанных ретраев,
"мусорный" ответ LLM у Retriever/Verifier/Summarizer — все они сигналят
именно этими типами, см. `agents.py`/`question_writer.py`) здесь
перехватываются и превращаются в `StepResult(status='fail', error=...)` —
обычный путь retry/эскалации, как и любой другой fail.

## Регистрация в реестре `steps.py`

На уровне ИМПОРТА модуля — тот же паттерн, что описан в докстринге
`steps.py` ("конкретные функции регистрируют себя через register_step в
своих модулях"). Живой LLM-бэкенд для этой регистрации по умолчанию ещё не
подключён — тот же принцип отсрочки, что и `Cartographer` в `importer/cli.py`
(`_cartographer_llm_runner`): `_default_llm_runner` ниже падает
`NotImplementedError` только при РЕАЛЬНОМ вызове модели, не при импорте
модуля/регистрации; живое подключение — Задача 27 (пилотный прогон).
`LegalXClient` по умолчанию — `legalx.get_client()` (mock, если
`LEGALX_BACKEND` не задан — тот же дефолт, что и везде в проекте).

Тесты этого модуля (`test_steps_norm.py`) регистрацию по умолчанию не
используют — конструируют `NormStep`/`SummaryStep` напрямую со
скриптованными `AgentLLMClient`/`LegalXClient` (тот же паттерн, что
`test_agents.py`/`test_cartographer.py`), реестр не трогают напрямую (кроме
отдельного теста самого факта регистрации).
"""
from __future__ import annotations

from importer.build.agents import (
    ModelsConfig,
    Retriever,
    Summarizer,
    Verdict,
    Verifier,
    load_models_config,
    verifier_model_for,
)
from importer.build.legalx import LegalXClient, NormFragment, get_client
from importer.build.llm_client import AgentLLMClient, AgentLLMError, RunnerAgentLLM
from importer.build.orchestrator import BuildStore
from importer.build.profiles import Profile
from importer.build.question_writer import MapItem, write_questions
from importer.build.steps import ItemContext, StepResult, register_step

# УЗ — единственная юрисдикция с реальными фикстурами LegalX сейчас
# (`legalx_mock.py`) и primary market проекта (docs/adr/0002). `NormStep`
# принимает `jurisdiction` явным параметром конструктора: ни `ItemRecord`,
# ни `ItemContext.data` её сейчас не несут — Cartographer кладёт
# `jurisdiction` только в `MapRecord`, а `BuildStore.create_items` в
# `pipeline.items` её не переносит (тот же пробел, что и с
# `rationale`/`benchmark_countries` MapItem — см. `_map_item_from_ctx`
# ниже). Устранение этого пробела — вне рамок этой задачи.
DEFAULT_JURISDICTION = "UZ"

NORM_PROFILE = Profile(
    name="norm",
    system_prompt=(
        "Ты ищешь нормы права, которые подтверждают конкретное требование "
        "комплаенс-чеклиста, отвечая на уточняющий вопрос."
    ),
    response_schema={"type": "object"},
    tier="mid",
)

SUMMARY_PROFILE = Profile(
    name="summary",
    system_prompt=(
        "Ты сжимаешь фрагмент нормы права в саммари простым языком для "
        "нестрого-юридической аудитории — не добавляя ничего от себя и не "
        "искажая смысл нормы."
    ),
    response_schema={"type": "object"},
    tier="cheap",
)


def _map_item_from_ctx(ctx: ItemContext) -> MapItem:
    """`MapItem` для `question_writer` из `ItemContext`.

    `rationale`/`benchmark_countries` Cartographer кладёт только в payload
    карты (`MapRecord.payload`) — `BuildStore.create_items` (Задача 14) их в
    `pipeline.items` не переносит, значит их нет и в `ItemRecord`. Пока это
    не устранено отдельной задачей — дефолт пустая строка/пустой список
    (`question_writer` работает и с ними, просто с меньшим контекстом в
    промпте: `expected_item`/`category_slug` остаются основным сигналом)."""
    item = ctx.item
    return MapItem(
        expected_item=item.expected_item,
        category_slug=item.category_slug or "",
        rationale=str(ctx.data.get("rationale", "")),
        benchmark_countries=list(ctx.data.get("benchmark_countries", [])),
    )


class NormStep:
    """Шаговый callable 'norm' (см. докстринг модуля)."""

    def __init__(
        self,
        legalx: LegalXClient,
        llm: AgentLLMClient,
        *,
        jurisdiction: str = DEFAULT_JURISDICTION,
        models: ModelsConfig | None = None,
        profile: Profile = NORM_PROFILE,
    ):
        self._llm = llm
        self._jurisdiction = jurisdiction
        self._models = models or load_models_config()
        self._profile = profile
        self._retriever = Retriever(legalx, llm, self._models)

    def __call__(self, ctx: ItemContext) -> StepResult:
        try:
            return self._run(ctx)
        except (AgentLLMError, ValueError) as exc:
            return StepResult(status="fail", error=f"шаг 'norm': {exc}")

    def _run(self, ctx: ItemContext) -> StepResult:
        item = _map_item_from_ctx(ctx)
        questions = write_questions(item, llm=self._llm)

        producer_model = self._models.tiers[self._profile.tier]
        verifier_model = verifier_model_for(producer_model, self._models)
        verifier = Verifier(llm=self._llm, model=verifier_model)

        verdicts: list[Verdict] = []
        outcomes: list[str] = []

        for question in questions:
            result = self._retriever.run(question.text, self._jurisdiction, self._profile)
            outcomes.append(result.outcome)
            if result.outcome != "found":
                continue

            fragment: NormFragment = result.fragments[0]
            verdict = verifier.run(
                question=question.text,
                fragment=fragment.content,
                source=fragment.act_title,
                profile=self._profile,
            )
            verdicts.append(verdict)
            if verdict.passed:
                ctx.data["norm_fragment"] = fragment
                ctx.data["norm_fragments"] = result.fragments
                ctx.data["norm_question"] = question.text
                ctx.data["norm_source"] = fragment.act_title
                return StepResult(status="ok", verdicts=verdicts)

        if outcomes and all(outcome == "no_norm" for outcome in outcomes):
            return StepResult(status="no_norm", verdicts=verdicts)

        return StepResult(
            status="fail",
            verdicts=verdicts,
            error=(
                f"шаг 'norm': ни один из {len(questions)} вопросов не дал "
                "найденный и подтверждённый верификатором фрагмент нормы"
            ),
        )


class SummaryStep:
    """Шаговый callable 'summary' (см. докстринг модуля).

    `store` (Задача 27, фикс-раунд ревью, Important №3) — шаг персистит
    саммари через `BuildStore.set_item_summary` сразу после успешной
    верификации: `pipeline.items` раньше не хранил `summary` вообще, из-за
    чего шаг 'dedup' (`steps_dedup.py`) сравнивал текущий айтем по
    `summary`, а кандидатов — по `expected_item` (асимметрично, срывало
    дедуп парафразов). См. докстринг `BuildStore.list_run_item_texts`
    (`orchestrator.py`)."""

    def __init__(
        self,
        llm: AgentLLMClient,
        store: BuildStore,
        *,
        models: ModelsConfig | None = None,
        profile: Profile = SUMMARY_PROFILE,
    ):
        self._llm = llm
        self._store = store
        self._models = models or load_models_config()
        self._profile = profile
        self._summarizer = Summarizer(llm, self._models)

    def __call__(self, ctx: ItemContext) -> StepResult:
        fragment = ctx.data.get("norm_fragment")
        if fragment is None:
            return StepResult(
                status="fail",
                error=(
                    "шаг 'summary': в item_ctx нет 'norm_fragment' — шаг "
                    "'norm' ещё не отработал"
                ),
            )
        try:
            return self._run(ctx, fragment)
        except (AgentLLMError, ValueError) as exc:
            return StepResult(status="fail", error=f"шаг 'summary': {exc}")

    def _run(self, ctx: ItemContext, fragment: NormFragment) -> StepResult:
        summary_text = self._summarizer.run(fragment.content, self._profile)

        producer_model = self._models.tiers[self._profile.tier]
        verifier_model = verifier_model_for(producer_model, self._models)
        verifier = Verifier(llm=self._llm, model=verifier_model)
        verdict = verifier.run(
            question="Саммари точно передаёт норму и не добавляет ничего от себя?",
            fragment=summary_text,
            source=fragment.content,
            profile=self._profile,
        )

        if not verdict.passed:
            return StepResult(
                status="fail",
                verdicts=[verdict],
                error=verdict.reason or "шаг 'summary': верификатор не подтвердил саммари",
            )

        ctx.data["summary"] = summary_text
        self._store.set_item_summary(ctx.item.id, summary_text)
        return StepResult(status="ok", verdicts=[verdict])


def _default_llm_runner(prompt: str, model: str) -> str:
    """Заглушка runner'а для регистрации по умолчанию (см. докстринг
    модуля) — тот же паттерн отсрочки, что и `_cartographer_llm_runner` в
    `importer/cli.py`: падает только при РЕАЛЬНОМ вызове модели, не при
    импорте/регистрации шага."""
    raise NotImplementedError(
        "Живой LLM-runner для шагов 'norm'/'summary' ещё не подключён — "
        "заработает после пилотного прогона Задачи 27 (см. "
        "importer/build/llm_client.py:RunnerAgentLLM, тот же паттерн, что и "
        "Cartographer в importer/cli.py:_cartographer_llm_runner)"
    )


class _DummyStore:
    """Заглушка BuildStore для регистрации 'summary' по умолчанию — падает
    только при РЕАЛЬНОМ вызове `set_item_summary`, не при импорте/
    регистрации шага (тот же паттерн, что и `_DummyStore` в
    `steps_classify.py`/`steps_scope_lifecycle.py`/`steps_dedup.py`)."""

    def set_item_summary(self, item_id: str, summary: str) -> None:
        raise NotImplementedError(
            "Живой BuildStore для шага 'summary' ещё не подключён — "
            "заработает после инъекции через build_step_registry (Задача 27)"
        )


_default_llm = RunnerAgentLLM(_default_llm_runner)
register_step("norm", NormStep(get_client(), _default_llm))
register_step("summary", SummaryStep(_default_llm, _DummyStore()))
