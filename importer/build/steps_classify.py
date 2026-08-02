"""Шаг 'category' Build-конвейера (Задача 18, ADR-0003, «Блок 2»).

Классификатор (cheap) выбирает `category_slug` из справочника `requirement_categories`
по тексту требования (обычно `summary`, если он уже создан), а независимый
Verifier (expensive) проверяет, что классификация корректна.

Невалидный слаг → ретрай с указанием ошибки; снова невалидный → fail.
Verifier fail → fail. Успех: category_slug в item_ctx.data, вердикт в StepResult.
"""
from __future__ import annotations

from importer.build.agents import (
    Classifier,
    ModelsConfig,
    Verdict,
    Verifier,
    load_models_config,
    verifier_model_for,
)
from importer.build.llm_client import AgentLLMClient, AgentLLMError
from importer.build.orchestrator import BuildStore
from importer.build.profiles import Profile
from importer.build.steps import ItemContext, StepResult, register_step

CLASSIFY_PROFILE = Profile(
    name="label",
    system_prompt=(
        "Ты классифицируешь требование комплаенс-чеклиста по типу нетарифного "
        "барьера (NTM): какая из 8 категорий (SPS, TBT, маркировка, лицензии, "
        "налоги, валюта, таможня, происхождение) охватывает это требование."
    ),
    response_schema={
        "type": "object",
        "properties": {
            "category_slug": {
                "type": "string",
                "description": "Код категории из справочника",
            }
        },
        "required": ["category_slug"],
    },
    tier="cheap",
)


class ClassifyStep:
    """Шаговый callable 'category' (см. докстринг модуля)."""

    def __init__(self, llm: AgentLLMClient, store: BuildStore, models: ModelsConfig | None = None):
        self._llm = llm
        self._store = store
        self._models = models or load_models_config()
        self._classifier = Classifier(llm, self._models)
        self._valid_slugs = store.list_category_slugs()

    def __call__(self, ctx: ItemContext) -> StepResult:
        # Проверяем, есть ли в контексте текст для классификации
        summary = ctx.data.get("summary")
        if summary is None:
            return StepResult(
                status="fail",
                error=(
                    "шаг 'category': в item_ctx нет 'summary' — шаг 'summary' "
                    "ещё не отработал"
                ),
            )

        try:
            return self._run(ctx, summary)
        except (AgentLLMError, ValueError) as exc:
            return StepResult(status="fail", error=f"шаг 'category': {exc}")

    def _run(self, ctx: ItemContext, summary: str) -> StepResult:
        # Создаём профиль с актуальным списком слагов в промпте
        profile = self._make_profile()

        # Первая попытка классификации
        result = self._classifier.run(summary, profile)
        category_slug = result.get("category_slug", "")

        # Проверяем валидность слага
        if category_slug not in self._valid_slugs:
            # Ретрай с сообщением об ошибке
            retry_profile = self._make_profile(
                error_message=(
                    f"Предыдущий ответ '{category_slug}' не входит в справочник. "
                    f"Используй ТОЛЬКО один из этих кодов."
                )
            )
            result = self._classifier.run(summary, retry_profile)
            category_slug = result.get("category_slug", "")

        # Проверяем валидность после ретрая
        if category_slug not in self._valid_slugs:
            return StepResult(
                status="fail",
                error=(
                    f"шаг 'category': классификатор вернул невалидный слаг "
                    f"'{category_slug}' (не в справочнике {self._valid_slugs})"
                ),
            )

        # Верификация классификации
        producer_model = self._models.tiers[profile.tier]
        verifier_model = verifier_model_for(producer_model, self._models)
        verifier = Verifier(llm=self._llm, model=verifier_model)

        verdict = verifier.run(
            question=(
                f"Является ли '{category_slug}' правильной классификацией "
                "для этого требования?"
            ),
            fragment=summary,
            source="category schema",
            profile=profile,
        )

        if not verdict.passed:
            return StepResult(
                status="fail",
                verdicts=[verdict],
                error=verdict.reason or "шаг 'category': верификатор не подтвердил классификацию",
            )

        ctx.data["category_slug"] = category_slug
        return StepResult(status="ok", verdicts=[verdict])

    def _make_profile(self, error_message: str = "") -> Profile:
        """Создаёт профиль с актуальным списком слагов в системном промпте."""
        valid_slugs_str = ", ".join(self._valid_slugs)
        system_prompt = CLASSIFY_PROFILE.system_prompt

        if error_message:
            system_prompt = f"{system_prompt}\n\n{error_message}"

        system_prompt += f"\n\nДоступные коды категорий: {valid_slugs_str}"

        return Profile(
            name=CLASSIFY_PROFILE.name,
            system_prompt=system_prompt,
            response_schema=CLASSIFY_PROFILE.response_schema,
            tier=CLASSIFY_PROFILE.tier,
        )


def _default_llm_runner(prompt: str, model: str) -> str:
    """Заглушка runner'а для регистрации по умолчанию (см. docstring steps_norm.py)
    — тот же паттерн отсрочки: падает только при РЕАЛЬНОМ вызове модели, не при
    импорте/регистрации шага."""
    raise NotImplementedError(
        "Живой LLM-runner для шага 'category' ещё не подключён — "
        "заработает после пилотного прогона Задачи 27 (см. "
        "importer/build/llm_client.py:RunnerAgentLLM)"
    )


# Регистрация шага (заглушка BuildStore для регистрации)
class _DummyStore:
    """Заглушка BuildStore для регистрации без живого хранилища."""
    def list_category_slugs(self) -> list[str]:
        return ["sps", "tbt", "marking", "licensing", "fiscal", "currency", "customs", "origin"]


from importer.build.llm_client import RunnerAgentLLM  # noqa: E402
_default_llm = RunnerAgentLLM(_default_llm_runner)
register_step("category", ClassifyStep(_default_llm, _DummyStore()))
