"""Шаг 'translate' Build-конвейера (Задача 24, Блок 2): перевод ИИ-текстов
с верификацией.

Переводятся ТОЛЬКО ИИ-тексты (summary, lawyer_instruction.steps[]/verdict,
status_note, sanctions[].measure) — поля из ctx.data. Verbatim-тексты
(norm_fragment.content из LegalX) НЕ переводятся повторно.

Целевой язык задаётся конструктором TranslateStep(target_lang='uz' | 'en' | ...).
- 'uz': перевод на узбекский;
- 'en': перевод на английский;
- иные: пропуск (контент не требует перевода или уже на целевом языке).

Verifier (профиль 'translation', mid-модель по CSV 27) проверяет эквивалентность
переведённого текста исходному и корректность терминов → pass/fail.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date

import pytest

from importer.build.agents import load_models_config, verifier_model_for
from importer.build.legalx import NormFragment
from importer.build.steps import ItemContext, ItemRecord
from importer.build.steps_translate import TranslateStep


# ── Мок LLM для скриптовки ответов ───────────────────────────────────────────


@dataclass
class ScriptedLLM:
    """Инжектируемый мок: отдаёт ответы по очереди, фиксирует все (prompt, model)."""

    responses: list[str]
    calls: list[tuple[str, str]] = field(default_factory=list)

    def complete(self, prompt: str, model: str) -> str:
        self.calls.append((prompt, model))
        if not self.responses:
            raise AssertionError(
                "ScriptedLLM: запросили ответ сверх скрипта — лишний вызов LLM"
            )
        return self.responses.pop(0)


# ── Вспомогательные функции ──────────────────────────────────────────────────


def item_ctx(
    *,
    summary: str | None = "Требуется сертификат соответствия перед вводом",
    lawyer_instruction: dict | None = None,
    status_note: str | None = None,
    sanctions: list[dict] | None = None,
    with_norm_fragment: bool = False,
    jurisdiction: str = "UZ",
) -> ItemContext:
    """Создаёт ItemContext с начальными данными."""
    item = ItemRecord(
        id="item-1",
        run_id="run-1",
        expected_item="сертификат соответствия на партию сигарет",
        category_slug="marking",
    )
    ctx = ItemContext(item=item)
    ctx.data["jurisdiction"] = jurisdiction

    if summary is not None:
        ctx.data["summary"] = summary

    if lawyer_instruction is not None:
        ctx.data["lawyer_instruction"] = lawyer_instruction
    else:
        # default: instruction с шагами, вердиктом и санкциями
        ctx.data["lawyer_instruction"] = {
            "steps": [
                "Проверить сертификат перед вводом",
                "Хранить в защищённом месте",
            ],
            "verdict": "Требование обязательно к соблюдению",
        }

    if status_note is not None:
        ctx.data["status_note"] = status_note

    if sanctions is not None:
        ctx.data["sanctions"] = sanctions
    else:
        ctx.data["sanctions"] = [
            {
                "article": "ст. 204 КоАО",
                "fine": {"amount": 50, "unit": "БРВ"},
                "measure": "Штраф за отсутствие сертификата",
            }
        ]

    if with_norm_fragment:
        ctx.data["norm_fragment"] = NormFragment(
            fragment_id="frag-1",
            act_id="act-1",
            act_title="ПКМ-43",
            article_ref="прил. 4",
            anchor="#a4",
            content="содержимое цитаты из нормы — НЕ должно переводиться",
            act_status="active",
            valid_from=date(2020, 1, 1),
            valid_to=None,
            score=1.0,
        )

    return ctx


def verdict_json(passed: bool, reason: str = "") -> str:
    """Возвращает JSON-ответ Verifier'а."""
    return json.dumps({"passed": passed, "reason": reason}, ensure_ascii=False)


def translation_json(uz_summary: str = "", uz_steps: list[str] | None = None) -> str:
    """Возвращает JSON-ответ Translator'а."""
    if uz_steps is None:
        uz_steps = [
            "Узбекская версия шага 1",
            "Узбекская версия шага 2",
        ]
    return json.dumps(
        {
            "summary": uz_summary,
            "lawyer_instruction": {
                "steps": uz_steps,
                "verdict": "Узбекский вердикт",
            },
            "status_note": "Узбекская заметка о статусе",
            "sanctions_measures": [
                "Узбекский перевод санкции",
            ],
        },
        ensure_ascii=False,
    )


# ── Пин-тест: verbatim не переводится ────────────────────────────────────────


def test_translate_step_verbatim_not_in_prompt():
    """Пин-тест: norm_fragment.content НЕ попадает в промпт переводчика."""
    llm = ScriptedLLM([
        translation_json("Переведённая сущность"),
        verdict_json(True),
    ])
    step = TranslateStep(llm, target_lang="uz")
    ctx = item_ctx(with_norm_fragment=True)

    result = step(ctx)

    assert result.status == "ok"
    # Проверяем, что в промптах нет содержимого norm_fragment
    assert len(llm.calls) == 2
    translator_prompt = llm.calls[0][0]
    verifier_prompt = llm.calls[1][0]

    # Verbatim-текст из нормы не должен быть в переводчике
    assert "содержимое цитаты из нормы" not in translator_prompt
    # Verifier получает только переведённый текст, не исходный verbatim
    assert "содержимое цитаты из нормы" not in verifier_prompt


# ── Happy path: uz перевод summary+instruction+note+measures ───────────────────


def test_translate_step_happy_path_uz():
    """Happy path: все поля переведены, структура зеркальна uz."""
    llm = ScriptedLLM([
        translation_json(
            uz_summary="Узбекский перевод сущности",
            uz_steps=["Узбекский шаг 1", "Узбекский шаг 2"],
        ),
        verdict_json(True, "Перевод эквивалентен исходному"),
    ])
    step = TranslateStep(llm, target_lang="uz")
    ctx = item_ctx()

    result = step(ctx)

    assert result.status == "ok"
    assert len(result.verdicts) == 1
    assert result.verdicts[0].passed is True

    # Проверяем структуру переводов
    assert "translations" in ctx.data
    translations = ctx.data["translations"]
    assert translations["lang"] == "uz"
    assert translations["summary"] == "Узбекский перевод сущности"
    assert translations["lawyer_instruction"]["steps"] == [
        "Узбекский шаг 1",
        "Узбекский шаг 2",
    ]
    assert translations["lawyer_instruction"]["verdict"] == "Узбекский вердикт"
    assert translations["status_note"] == "Узбекская заметка о статусе"
    assert len(translations["sanctions_measures"]) == 1
    assert translations["sanctions_measures"][0] == "Узбекский перевод санкции"


# ── Целевой язык: 'en' ──────────────────────────────────────────────────────


def test_translate_step_target_lang_en():
    """Перевод на английский (target_lang='en')."""
    llm = ScriptedLLM([
        json.dumps(
            {
                "summary": "English translation",
                "lawyer_instruction": {
                    "steps": ["English step 1", "English step 2"],
                    "verdict": "English verdict",
                },
                "status_note": "English status note",
                "sanctions_measures": ["English sanction"],
            },
            ensure_ascii=False,
        ),
        verdict_json(True),
    ])
    step = TranslateStep(llm, target_lang="en")
    ctx = item_ctx()

    result = step(ctx)

    assert result.status == "ok"
    translations = ctx.data["translations"]
    assert translations["lang"] == "en"
    assert translations["summary"] == "English translation"


# ── Verifier fail → fail ─────────────────────────────────────────────────────


def test_translate_step_verifier_fail():
    """Verifier отклонил перевод → StepResult(fail)."""
    llm = ScriptedLLM([
        translation_json("Переведённый текст"),
        verdict_json(False, "Терминология некорректна"),
    ])
    step = TranslateStep(llm, target_lang="uz")
    ctx = item_ctx()

    result = step(ctx)

    assert result.status == "fail"
    assert "translations" not in ctx.data
    assert len(result.verdicts) == 1
    assert result.verdicts[0].passed is False


# ── Нет summary → fail ──────────────────────────────────────────────────────


def test_translate_step_no_summary_fails():
    """Без summary → StepResult(fail)."""
    llm = ScriptedLLM([])  # не должно быть вызовов
    step = TranslateStep(llm, target_lang="uz")
    ctx = item_ctx(summary=None)

    result = step(ctx)

    assert result.status == "fail"
    assert "translations" not in ctx.data
    assert llm.calls == []


# ── Пустые поля: переводится что есть ────────────────────────────────────────


def test_translate_step_partial_fields_no_instruction():
    """Без lawyer_instruction → переводится только summary."""
    llm = ScriptedLLM([
        json.dumps(
            {
                "summary": "Translated summary",
                "lawyer_instruction": None,
                "status_note": None,
                "sanctions_measures": [],
            },
            ensure_ascii=False,
        ),
        verdict_json(True),
    ])
    step = TranslateStep(llm, target_lang="uz")
    ctx = item_ctx(lawyer_instruction=None)

    result = step(ctx)

    assert result.status == "ok"
    translations = ctx.data["translations"]
    assert translations["summary"] == "Translated summary"
    assert translations["lawyer_instruction"] is None


def test_translate_step_partial_fields_no_status_note():
    """Без status_note → переводится summary и instruction."""
    llm = ScriptedLLM([
        json.dumps(
            {
                "summary": "Translated",
                "lawyer_instruction": {
                    "steps": ["Step 1", "Step 2"],
                    "verdict": "Verdict",
                },
                "status_note": None,
                "sanctions_measures": [],
            },
            ensure_ascii=False,
        ),
        verdict_json(True),
    ])
    step = TranslateStep(llm, target_lang="uz")
    ctx = item_ctx(status_note=None)

    result = step(ctx)

    assert result.status == "ok"
    translations = ctx.data["translations"]
    assert translations["status_note"] is None


def test_translate_step_partial_fields_no_sanctions_measures():
    """Без sanctions с measure → sanctions_measures пусто."""
    llm = ScriptedLLM([
        json.dumps(
            {
                "summary": "Translated",
                "lawyer_instruction": {
                    "steps": ["Step 1"],
                    "verdict": "Verdict",
                },
                "status_note": "Note",
                "sanctions_measures": [],
            },
            ensure_ascii=False,
        ),
        verdict_json(True),
    ])
    step = TranslateStep(llm, target_lang="uz")
    ctx = item_ctx(sanctions=[])

    result = step(ctx)

    assert result.status == "ok"
    translations = ctx.data["translations"]
    assert translations["sanctions_measures"] == []


# ── Пропуск при целевом языке None или неизвестном ──────────────────────────


def test_translate_step_target_lang_none_returns_ok_no_translation():
    """target_lang=None → пропуск, StepResult(ok), без translations."""
    llm = ScriptedLLM([])  # не должно быть вызовов
    step = TranslateStep(llm, target_lang=None)
    ctx = item_ctx()

    result = step(ctx)

    assert result.status == "ok"
    assert "translations" not in ctx.data
    assert llm.calls == []


# ── Verifier модель: mid ─────────────────────────────────────────────────────


def test_translate_step_verifier_uses_mid_model():
    """Verifier использует mid-модель (особый случай CSV 27)."""
    llm = ScriptedLLM([
        translation_json("Перевод"),
        verdict_json(True),
    ])
    step = TranslateStep(llm, target_lang="uz")
    ctx = item_ctx()

    result = step(ctx)

    assert result.status == "ok"
    # Проверяем, что verifier вызывался с mid-моделью
    models = load_models_config()
    mid_model = models.tiers["mid"]

    assert len(llm.calls) == 2
    verifier_call_model = llm.calls[1][1]
    assert verifier_call_model == mid_model


# ── LLM ошибка → fail ────────────────────────────────────────────────────────


def test_translate_step_translator_error_returns_fail():
    """Ошибка Translator'а → fail."""
    class ErrorLLM:
        def complete(self, prompt: str, model: str) -> str:
            raise Exception("LLM error")

    llm = ErrorLLM()
    step = TranslateStep(llm, target_lang="uz")
    ctx = item_ctx()

    result = step(ctx)

    assert result.status == "fail"
    assert "translations" not in ctx.data


def test_translate_step_verifier_error_returns_fail():
    """Ошибка Verifier'а (невалидный JSON) → fail."""
    llm = ScriptedLLM([
        translation_json("Перевод"),
        "Not a JSON response",  # Verifier получит невалидный JSON
    ])
    step = TranslateStep(llm, target_lang="uz")
    ctx = item_ctx()

    result = step(ctx)

    assert result.status == "fail"


# ── Структура результата ────────────────────────────────────────────────────


def test_translate_step_result_structure_complete():
    """Структура результата зеркальна структуре входящих данных."""
    llm = ScriptedLLM([
        json.dumps(
            {
                "summary": "Uz summary",
                "lawyer_instruction": {
                    "steps": ["Uz step 1", "Uz step 2", "Uz step 3"],
                    "verdict": "Uz verdict",
                },
                "status_note": "Uz status",
                "sanctions_measures": ["Uz sanction 1", "Uz sanction 2"],
            },
            ensure_ascii=False,
        ),
        verdict_json(True),
    ])
    step = TranslateStep(llm, target_lang="uz")
    ctx = item_ctx(
        sanctions=[
            {
                "article": "ст. 204",
                "measure": "Штраф 1",
            },
            {
                "article": "ст. 205",
                "measure": "Штраф 2",
            },
        ]
    )

    result = step(ctx)

    assert result.status == "ok"
    translations = ctx.data["translations"]

    # Проверяем, что все поля на месте
    assert "lang" in translations
    assert "summary" in translations
    assert "lawyer_instruction" in translations
    assert "status_note" in translations
    assert "sanctions_measures" in translations

    # Проверяем структуру lawyer_instruction
    assert "steps" in translations["lawyer_instruction"]
    assert "verdict" in translations["lawyer_instruction"]
    assert len(translations["lawyer_instruction"]["steps"]) == 3
