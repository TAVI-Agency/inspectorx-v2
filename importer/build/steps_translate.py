"""Шаг 'translate' Build-конвейера (Задача 24, ADR-0003 «Блок 2»,
`docs/TARGET_FORMAT.md` §4 «Перевод ИИ-текстов»).

Один шаг STEP_ORDER, внутри — две фазы (task-24-brief.md, уточнения
контроллера):

## 1) Translator (профиль 'translation', тир зависит от контекста)

Переводит ИИ-генерируемые тексты (summary, lawyer_instruction.steps/verdict,
status_note, sanctions[].measure) на целевой язык (uz/en/...). Verbatim-тексты
из LegalX (norm_fragment.content) НЕ переводятся повторно — они уже в промпт
переводчика не попадают.

Результат: `ctx.data['translations']` = {
  'lang': 'uz' | 'en' | ...,
  'summary': str,
  'lawyer_instruction': {'steps': [str, ...], 'verdict': str},
  'status_note': str | None,
  'sanctions_measures': [str, ...],
}

## 2) Verifier (профиль 'translation', СПЕЦИАЛЬНЫЙ СЛУЧАЙ: всегда mid-модель)

Проверяет независимо: «узбекский текст эквивалентен исходному на русском,
термины корректны, смысл сохранён». Если `passed=False` → `StepResult(fail)`.

## Условия пропуска

- Нет summary → fail (summary обязателен по STEP_ORDER);
- target_lang=None или неподдерживаемый → пропуск, StepResult(ok), без translations.

## Целевые языки

- 'uz': перевод на узбекский (UZ-юрисдикция);
- 'en': перевод на английский (AE-юрисдикция);
- иные: пропуск, контент не требует перевода (КЗ: content уже ru, перевода не нужен).

## Почему нет фильтра translation_origin='machine'

Все поля, перечисленные в payload (summary, lawyer_instruction, status_note,
sanctions[].measure), являются ИИ-текстами **по построению** — их произвели
наши агенты в шагах STEP_ORDER ПЕРЕД шагом 'translate'. Verbatim-тексты
(norm_fragment.content из LegalX) структурно не входят в payload и не
переводятся, что гарантируется на уровне _build_payload() и доказывается
пин-тестом `test_translate_step_verbatim_not_in_prompt`.

Маркер `translation_origin='machine'` выставляет шаг 'load' (Задача 26) при
записи строк uz/en из ctx.data['translations'] в таблицу requirement_contents.
Фильтра в ctx.data здесь быть не должно — он артефакт БД, а не контракт
конвейера.
"""
from __future__ import annotations

import json
from typing import TYPE_CHECKING, Literal

from importer.build.agents import (
    ModelsConfig,
    Verdict,
    Verifier,
    # _trace_llm_call — приватный хелпер agents.py, импортируется явно (не
    # export API модуля), чтобы шаг 'translate' считал токены/cost_usd ТЕМ
    # ЖЕ способом, что и generic-агенты (Retriever/Verifier/Classifier/
    # Summarizer) — см. докстринг `TranslateStep._translate` (гейт живого
    # прогона, LAUNCH_CHECKLIST.md, пункт 3).
    _trace_llm_call,
    load_models_config,
)
from importer.build.llm_client import AgentLLMClient, AgentLLMError, RunnerAgentLLM
from importer.build.profiles import Profile
from importer.build.steps import ItemContext, StepResult, register_step
from importer.build.steps_norm import DEFAULT_JURISDICTION

if TYPE_CHECKING:  # только тип — импорт по значению создал бы цикл steps_translate<->trace
    from importer.build.trace import Tracer

TRANSLATION_PROFILE = Profile(
    name="translation",
    system_prompt=(
        "Ты переводчик юридических текстов с русского на узбекский/английский. "
        "Переводи ИИ-генерируемые тексты (сущность, инструкция, пояснения санкций) "
        "точно и ясно, сохраняя юридический смысл и терминологию. "
        "Не переводи юридические цитаты из нормативных актов — их уже переведены. "
        "Ответь СТРОГО JSON без пояснений."
    ),
    response_schema={"type": "object"},
    tier="mid",  # tier здесь используется только для структуры профиля
)


class TranslateStep:
    """Шаговый callable 'translate' (см. докстринг модуля)."""

    def __init__(
        self,
        llm: AgentLLMClient,
        *,
        target_lang: Literal["uz", "en"] | None = "uz",
        models: ModelsConfig | None = None,
        profile: Profile = TRANSLATION_PROFILE,
        tracer: "Tracer | None" = None,
    ):
        self._llm = llm
        self._target_lang = target_lang
        self._models = models or load_models_config()
        self._profile = profile
        self._tracer = tracer

    def __call__(self, ctx: ItemContext) -> StepResult:
        try:
            return self._run(ctx)
        except (AgentLLMError, ValueError, json.JSONDecodeError, KeyError, Exception) as exc:
            return StepResult(status="fail", error=f"шаг 'translate': {exc}")

    def _run(self, ctx: ItemContext) -> StepResult:
        # Проверка: summary обязателен к этому шагу по STEP_ORDER
        if not ctx.data.get("summary"):
            return StepResult(status="fail", error="шаг 'translate': нет summary")

        # Пропуск: целевой язык не задан или не поддерживается
        if not self._target_lang:
            return StepResult(status="ok")

        # Собираем данные для перевода (только ИИ-тексты, не verbatim из LegalX)
        payload = self._build_payload(ctx)

        # Фаза 1: Translator (выбираем mid-модель явно)
        translator_model = self._models.tiers["mid"]
        translation_json_str = self._translate(payload, translator_model)

        try:
            translation_data = json.loads(translation_json_str)
        except json.JSONDecodeError as exc:
            raise AgentLLMError(
                f"Translator вернула не-JSON: {translation_json_str!r}"
            ) from exc

        # Фаза 2: Verifier (СПЕЦИАЛЬНЫЙ СЛУЧАЙ: всегда mid-модель по CSV 27)
        verifier_model = self._models.tiers["mid"]
        verifier = Verifier(llm=self._llm, model=verifier_model, tracer=self._tracer)

        # Собираем кратко переведённый текст для Verifier'а
        translated_brief = self._build_verifier_fragment(translation_data)

        verdict: Verdict = verifier.run(
            question=f"Переведённый текст эквивалентен исходному на {self._target_lang}?",
            fragment=translated_brief,
            source=payload["summary"],
            profile=self._profile,
        )

        if not verdict.passed:
            return StepResult(
                status="fail",
                verdicts=[verdict],
                error=verdict.reason or "шаг 'translate': верификатор не подтвердил перевод",
            )

        # Успех: сохраняем результат
        result_translations = {
            "lang": self._target_lang,
            "summary": translation_data.get("summary"),
            "lawyer_instruction": translation_data.get("lawyer_instruction"),
            "status_note": translation_data.get("status_note"),
            "sanctions_measures": translation_data.get("sanctions_measures") or [],
        }

        ctx.data["translations"] = result_translations
        return StepResult(status="ok", verdicts=[verdict])

    def _build_payload(self, ctx: ItemContext) -> dict:
        """Собирает данные для перевода: только ИИ-тексты, не verbatim.

        Все перечисленные поля (summary, lawyer_instruction, status_note,
        sanctions[].measure) являются ИИ-генерируемыми текстами ПО ПОСТРОЕНИЮ
        (произведены нашими агентами перед этим шагом). Verbatim-тексты из
        LegalX (norm_fragment.content) структурно не входят в payload.
        translation_origin='machine' будет выставлен шагом 'load' при записи в БД."""
        payload = {
            "summary": ctx.data.get("summary", ""),
            "lawyer_instruction": ctx.data.get("lawyer_instruction"),
            "status_note": ctx.data.get("status_note"),
            "sanctions_measures": [],
        }

        # Собираем measure'ы из sanctions (только текстовые пояснения)
        sanctions = ctx.data.get("sanctions", [])
        for sanction in sanctions:
            if isinstance(sanction, dict) and "measure" in sanction:
                measure = sanction.get("measure")
                if measure:
                    payload["sanctions_measures"].append(measure)

        return payload

    def _translate(self, payload: dict, model: str) -> str:
        """Вызывает LLM-транслятор с профилем.

        Гейт живого прогона (LAUNCH_CHECKLIST.md, пункт 3): раньше вызов шёл
        `self._llm.complete(...)` мимо `agents.py` целиком — `self._tracer`
        конструктор получал ТОЛЬКО ради `Verifier` (см. `_run`), сам перевод
        в `pipeline.llm_calls` не попадал, хотя `build cost --run <id>`
        (`trace.py:cost_report`) заявляет покрытие по ролям — дыра ровно на
        переводах. Трейсим ТЕМ ЖЕ хелпером `_trace_llm_call`, что и
        generic-агенты (`agents.py`) — одинаковая оценка токенов
        (`llm.last_usage`, иначе `len(...)//4` фолбэк) и тот же no-op при
        `tracer=None` (обратная совместимость вызовов без tracer). Роль —
        `'translator'`, отдельная от `'verifier'` (та же функция ниже уже
        трейсит Verifier под своей ролью) — разные строки cost-отчёта."""
        prompt = (
            f"{self._profile.system_prompt}\n\n"
            f"Целевой язык: {self._target_lang}\n\n"
            f"Переведи следующие ИИ-тексты (НЕ переводи юридические цитаты).\n\n"
            f"Исходные данные (JSON):\n{json.dumps(payload, ensure_ascii=False)}\n\n"
            f"Ответь ТОЛЬКО JSON без пояснений — зеркальная структура со всеми ключами, "
            f"как в исходных данных (null оставляй null, списки сохраняй такой же длины)."
        )

        answer = self._llm.complete(prompt, model)
        _trace_llm_call(self._tracer, "translator", self._llm, model, prompt, answer)
        return answer

    def _build_verifier_fragment(self, translation_data: dict) -> str:
        """Собирает кратко переведённый текст для проверки Verifier'ом."""
        parts = []

        if translation_data.get("summary"):
            parts.append(f"Summary: {translation_data['summary']}")

        instr = translation_data.get("lawyer_instruction")
        if instr:
            if instr.get("steps"):
                parts.append(f"Steps: {'; '.join(instr['steps'])}")
            if instr.get("verdict"):
                parts.append(f"Verdict: {instr['verdict']}")

        if translation_data.get("status_note"):
            parts.append(f"Status note: {translation_data['status_note']}")

        if translation_data.get("sanctions_measures"):
            parts.append(f"Sanctions: {'; '.join(translation_data['sanctions_measures'])}")

        return "\n".join(parts) if parts else "Перевод пуст"


def _default_llm_runner(prompt: str, model: str) -> str:
    """Заглушка runner'а для регистрации по умолчанию (см. докстринг
    модуля) — падает только при РЕАЛЬНОМ вызове модели, не при
    импорте/регистрации шага."""
    raise NotImplementedError(
        "Живой LLM-runner для шага 'translate' ещё не подключён — заработает "
        "после пилотного прогона Задачи 27 (см. "
        "importer/build/llm_client.py:RunnerAgentLLM)"
    )


_default_llm = RunnerAgentLLM(_default_llm_runner)
register_step("translate", TranslateStep(_default_llm))
