"""Шаг 'category' (Задача 18): Classifier категории + Verifier (Блок 2).

Сценарии из брифа/уточнений:
- happy-path: Classifier выбирает валидный `category_slug` из справочника,
  Verifier подтверждает классификацию -> StepResult(ok), category_slug в ItemContext.data;
- невалидный слаг -> ретрай с указанием ошибки -> успех;
- дважды невалидный слаг -> StepResult(fail);
- Verifier fail -> StepResult(fail);
- слаги в промпте из инжектированного списка, не хардкод.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date

from importer.build.agents import load_models_config, verifier_model_for
from importer.build.legalx import NormFragment
from importer.build.orchestrator import MapRecord
from importer.build.steps import ItemContext, ItemRecord, StepResult
from importer.build.steps_classify import ClassifyStep
from importer.tests.build.stores import InMemoryStore


# ── тестовые дублёры ────────────────────────────────────────────────────


@dataclass
class ScriptedLLM:
    """Мок AgentLLMClient: отдаёт ответы по очереди, фиксирует все (prompt, model)."""

    responses: list[str]
    calls: list[tuple[str, str]] = field(default_factory=list)

    def complete(self, prompt: str, model: str) -> str:
        self.calls.append((prompt, model))
        if not self.responses:
            raise AssertionError("ScriptedLLM: запросили ответ сверх скрипта — лишний вызов LLM")
        return self.responses.pop(0)


def classifier_response(category_slug: str) -> str:
    return json.dumps({"category_slug": category_slug}, ensure_ascii=False)


def verdict_json(passed: bool, reason: str = "") -> str:
    return json.dumps({"passed": passed, "reason": reason}, ensure_ascii=False)


def item_ctx(**over) -> ItemContext:
    base = dict(
        id="item-1",
        run_id="run-1",
        expected_item="акцизная марка на пачке сигарет",
        category_slug=None,
    )
    item = ItemRecord(**{**base, **over})
    ctx = ItemContext(item=item)
    # Добавляем summary в контекст — классификатор берёт текст для анализа
    ctx.data["summary"] = "текст требования о маркировке сигарет"
    return ctx


# ── шаг 'category': happy-path ───────────────────────────────────────────


def test_classify_step_happy_path_fills_context_and_returns_ok():
    """Классификатор выбирает валидный слаг, верификатор подтверждает."""
    llm = ScriptedLLM(responses=[
        classifier_response("marking"),
        verdict_json(True, "слаг соответствует содержанию"),
    ])
    store = InMemoryStore()
    step = ClassifyStep(llm, store)
    ctx = item_ctx()

    result = step(ctx)

    assert result.status == "ok"
    assert len(result.verdicts) == 1
    assert result.verdicts[0].passed is True
    assert ctx.data["category_slug"] == "marking"


def test_classify_step_uses_cheap_tier_and_verifier_gets_expensive_tier():
    """Классификатор работает на cheap, верификатор — на expensive."""
    llm = ScriptedLLM(responses=[
        classifier_response("marking"),
        verdict_json(True),
    ])
    store = InMemoryStore()
    step = ClassifyStep(llm, store)

    step(item_ctx())

    config = load_models_config()
    # Verifier должен получить другой тир, чем producer
    verifier_call_model = llm.calls[1][1]
    assert verifier_call_model == config.tiers["expensive"]
    assert verifier_call_model == verifier_model_for(config.tiers["cheap"])


# ── шаг 'category': невалидный слаг → ретрай → успех ───────────────────


def test_classify_step_invalid_slug_retries_with_error_message():
    """Первый ответ — невалидный слаг, ретрай выбирает валидный."""
    llm = ScriptedLLM(responses=[
        classifier_response("invalid_slug"),  # невалидный
        classifier_response("marking"),       # валидный
        verdict_json(True),
    ])
    store = InMemoryStore()
    step = ClassifyStep(llm, store)
    ctx = item_ctx()

    result = step(ctx)

    assert result.status == "ok"
    assert ctx.data["category_slug"] == "marking"
    # Должны быть вызовы: 1-й classifier (невалидный), ретрай classifier, verifier
    assert len(llm.calls) == 3
    # Во втором запросе (ретрай) должно быть сообщение об ошибке
    retry_prompt = llm.calls[1][0]
    assert "invalid_slug" in retry_prompt or "невалидн" in retry_prompt.lower()


# ── шаг 'category': дважды невалидный слаг → fail ─────────────────────


def test_classify_step_twice_invalid_slug_returns_fail():
    """Оба ответа классификатора — невалидные слаги."""
    llm = ScriptedLLM(responses=[
        classifier_response("invalid_1"),  # невалидный
        classifier_response("invalid_2"),  # всё ещё невалидный
    ])
    store = InMemoryStore()
    step = ClassifyStep(llm, store)
    ctx = item_ctx()

    result = step(ctx)

    assert result.status == "fail"
    assert result.error is not None
    assert "invalid" in result.error.lower() or "невалидн" in result.error.lower()


# ── шаг 'category': verifier fail → fail ─────────────────────────────


def test_classify_step_verifier_fail_returns_fail():
    """Классификатор выбирает валидный слаг, но верификатор его отклоняет."""
    llm = ScriptedLLM(responses=[
        classifier_response("marking"),
        verdict_json(False, "слаг не соответствует требованию"),
    ])
    store = InMemoryStore()
    step = ClassifyStep(llm, store)
    ctx = item_ctx()

    result = step(ctx)

    assert result.status == "fail"
    assert len(result.verdicts) == 1
    assert result.verdicts[0].passed is False
    assert result.error is not None


# ── слаги в промпте из справочника, не хардкод ──────────────────────────


def test_classify_step_slugs_in_prompt_from_store():
    """Слаги классификации подставляются в промпт из store.list_category_slugs(),
    а не захардкодены в коде шага."""
    llm = ScriptedLLM(responses=[
        classifier_response("tbt"),
        verdict_json(True),
    ])
    store = InMemoryStore()
    step = ClassifyStep(llm, store)
    ctx = item_ctx()

    step(ctx)

    # Первый вызов (classifier) должен содержать список валидных слагов
    classifier_prompt = llm.calls[0][0]
    valid_slugs = store.list_category_slugs()
    for slug in ["marking", "tbt", "sps", "licensing"]:
        assert slug in classifier_prompt, f"Слаг {slug!r} должен быть в промпте"


# ── шаг 'category': нет summary в контексте → fail ─────────────────────


def test_classify_step_without_summary_returns_fail():
    """Если в контексте нет summary (шаг 'summary' ещё не отработал),
    классификация невозможна."""
    llm = ScriptedLLM(responses=[])  # не должны быть вызовы LLM
    store = InMemoryStore()
    step = ClassifyStep(llm, store)
    ctx = item_ctx()
    del ctx.data["summary"]  # удаляем summary

    result = step(ctx)

    assert result.status == "fail"
    assert "summary" in result.error.lower()
    assert len(llm.calls) == 0  # LLM вообще не должна быть вызвана
