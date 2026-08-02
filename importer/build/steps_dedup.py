"""Шаг 'dedup' Build-конвейера (Задача 25, ADR-0003 «Блок 2»).

## Компромисс: dedup работает над ПАЧКОЙ, а конвейер идёт per-item

`Orchestrator.run_group` (`orchestrator.py`) гонит `STEP_ORDER` строго
per-item: каждый айтем проходит ВЕСЬ конвейер (norm...coverage) целиком,
прежде чем начинается следующий (см. цикл `for item in items` в
`_run_from`). Полноценный дедуп — операция уровня прогона (сравнить N
айтемов друг с другом), но 'dedup' обязан остаться ОДНИМ шагом STEP_ORDER
(список шагов — код брифа Задачи 14, не решение этой задачи).

Решение контроллера (task-25 brief): раз конвейер обрабатывает айтемы
последовательно один за другим, к моменту, когда шаг 'dedup' айтема N
выполняется, айтемы 1..N-1 ЭТОГО ЖЕ прогона уже полностью прошли конвейер
(терминальный статус — published/no_norm/needs_attention) и видны в
`BuildStore.list_run_item_texts(run_id)`. Поэтому 'dedup' сравнивает текущий
айтем ТОЛЬКО с уже обработанными айтемами — не с айтемами, которые ещё
впереди по очереди (их обработка ещё не началась, сравнивать не с чем).
Отдельная run-level функция `deduplicate_run(...)` не заводится — она не
вписывается в per-item модель `Orchestrator` без отдельного прохода после
`run_group`, а самый дешёвый и честный шаг сейчас — детекция дублей внутри
уже существующего per-item цикла.

## Что делает шаг

1. Берёт текст текущего айтема: `ctx.data['summary']`, если шаг 'summary'
   уже отработал, иначе `ctx.item.expected_item` (входной текст из карты).
2. Читает тексты уже обработанных айтемов ТЕКУЩЕГО прогона —
   `store.list_run_item_texts(ctx.item.run_id)` — за вычетом самого себя.
3. Для каждого кандидата считает косинусную близость эмбеддингов
   (`embeddings.py`, без LLM):
   - `score >= DUP_THRESHOLD_HIGH` -> дубль сразу, без обращения к LLM;
   - `score < DUP_THRESHOLD_LOW` -> явно не дубль, кандидат пропускается;
   - иначе (спорная пара) -> `Classifier` (cheap-тир, профиль `DEDUP_PROFILE`)
     решает `{"is_duplicate": bool}`; `true` -> дубль, `false` -> не дубль,
     сравнение идёт со следующим кандидатом.
4. Останавливается на первом найденном дубле (кто раньше в списке
   кандидатов — тот и канонический item_id; порядок кандидатов задаёт стор).

Пороги — СТАРТОВЫЕ значения (см. `DUP_THRESHOLD_HIGH`/`DUP_THRESHOLD_LOW`
ниже), калибровка — по трейсингу `pipeline.llm_calls`/`pipeline.verdicts`
живых прогонов (Задача 27+), не по этой задаче.

## Результат — ctx.data['dedup'], НЕ статус айтема

Шаг всегда завершается `StepResult(status='ok')` (сама детекция дубля — не
повод ретраить/эскалировать айтем) и ВСЕГДА пишет `ctx.data['dedup']`:
- дубль не найден: `{"duplicate_of": None}`;
- дубль найден: `{"duplicate_of": <item_id кандидата>, "score": <float>}`.

Статус `pipeline.items.status` намеренно НЕ получает значение вроде
'merged' — такого статуса нет в check-constraint таблицы (миграция
`20260803170000_pipeline_schema.sql`: только pending/in_progress/
draft_loaded/published/needs_attention/no_norm), а менять constraint ради
одного шага — решение вне этой задачи. Айтем идёт по обычному циклу дальше
(assemble/load/coverage) и получит обычный терминальный статус. Что шаг
'load' (Задача 26) обязан СДЕЛАТЬ с `ctx.data['dedup']['duplicate_of']` (не
создавать дубль-requirement, а смержить источники/scope в существующий,
как `importer/dedup.py:merge_requirement` делает для уже опубликованных
строк) — это follow-up контракт Задачи 26, здесь только детекция.

## Почему не переиспользован `importer/dedup.py`

См. докстринг `embeddings.py` — другой слой (уже опубликованные
`requirements`, точный ключ acт+пункт, без эмбеддингов), общего кода нет.
"""
from __future__ import annotations

from importer.build.agents import Classifier, ModelsConfig, load_models_config
from importer.build.embeddings import Embedder, LiveEmbedder, cosine_similarity
from importer.build.llm_client import AgentLLMClient, AgentLLMError, RunnerAgentLLM
from importer.build.orchestrator import BuildStore
from importer.build.profiles import Profile
from importer.build.steps import ItemContext, StepResult, register_step

# Стартовые пороги (см. докстринг модуля) — калибровка по трейсингу, не в этой задаче.
DUP_THRESHOLD_HIGH = 0.9  # >= этого — дубль без обращения к LLM
DUP_THRESHOLD_LOW = 0.75  # < этого — явно не дубль без обращения к LLM

DEDUP_PROFILE = Profile(
    name="dedup",  # вне ProfileName Literal — тот же прецедент, что и
    # 'scope'/'lifecycle'/'rule' в соседних шаговых модулях (реестр профилей
    # опционален, Literal в profiles.py в рантайме не проверяется).
    system_prompt=(
        "Ты решаешь спорную пару требований комплаенс-чеклиста: являются ли "
        "они ОДНИМ И ТЕМ ЖЕ требованием (просто иначе сформулированным), "
        "или это два РАЗНЫХ требования, лишь похожих по теме/формулировке. "
        "Ответь СТРОГО JSON {\"is_duplicate\": true|false}."
    ),
    response_schema={
        "type": "object",
        "properties": {"is_duplicate": {"type": "boolean"}},
        "required": ["is_duplicate"],
    },
    tier="cheap",
)


class DedupStep:
    """Шаговый callable 'dedup' (см. докстринг модуля)."""

    def __init__(
        self,
        llm: AgentLLMClient,
        store: BuildStore,
        embedder: Embedder,
        *,
        models: ModelsConfig | None = None,
        profile: Profile = DEDUP_PROFILE,
    ):
        self._llm = llm
        self._store = store
        self._embedder = embedder
        self._models = models or load_models_config()
        self._classifier = Classifier(llm, self._models)
        self._profile = profile

    def __call__(self, ctx: ItemContext) -> StepResult:
        try:
            return self._run(ctx)
        except (AgentLLMError, ValueError) as exc:
            return StepResult(status="fail", error=f"шаг 'dedup': {exc}")

    def _run(self, ctx: ItemContext) -> StepResult:
        text = ctx.data.get("summary") or ctx.item.expected_item
        current_vec = self._embedder.embed(text)

        candidates = [
            candidate
            for candidate in self._store.list_run_item_texts(ctx.item.run_id)
            if candidate["item_id"] != ctx.item.id
        ]

        for candidate in candidates:
            score = cosine_similarity(current_vec, self._embedder.embed(candidate["text"]))

            if score >= DUP_THRESHOLD_HIGH:
                ctx.data["dedup"] = {"duplicate_of": candidate["item_id"], "score": score}
                return StepResult(status="ok")

            if score < DUP_THRESHOLD_LOW:
                continue  # явно не дубль — сравниваем со следующим кандидатом

            # спорная пара (между порогами) — решает Classifier
            if self._classify_pair(text, candidate["text"]):
                ctx.data["dedup"] = {"duplicate_of": candidate["item_id"], "score": score}
                return StepResult(status="ok")

        ctx.data["dedup"] = {"duplicate_of": None}
        return StepResult(status="ok")

    def _classify_pair(self, text_a: str, text_b: str) -> bool:
        prompt_text = f"Требование А: {text_a}\nТребование Б: {text_b}"
        result = self._classifier.run(prompt_text, self._profile)
        return bool(result.get("is_duplicate", False))


def _default_llm_runner(prompt: str, model: str) -> str:
    """Заглушка runner'а для регистрации по умолчанию (см. докстринг
    `steps_norm.py`) — падает только при РЕАЛЬНОМ вызове модели, не при
    импорте/регистрации шага."""
    raise NotImplementedError(
        "Живой LLM-runner для шага 'dedup' ещё не подключён — заработает "
        "после пилотного прогона Задачи 27 (см. "
        "importer/build/llm_client.py:RunnerAgentLLM)"
    )


class _DummyStore:
    """Заглушка BuildStore для регистрации 'dedup' без живого хранилища —
    пустой реестр текстов прогона (тот же паттерн, что `_DummyStore` в
    `steps_classify.py`/`steps_scope_lifecycle.py`)."""

    def list_run_item_texts(self, run_id: str) -> list[dict]:
        return []


_default_llm = RunnerAgentLLM(_default_llm_runner)
register_step("dedup", DedupStep(_default_llm, _DummyStore(), LiveEmbedder()))
