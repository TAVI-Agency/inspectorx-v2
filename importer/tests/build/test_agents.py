"""Generic-агенты Build (Задача 13): Retriever/Verifier/Classifier/Summarizer.

Сценарии из брифа Задачи 13:
- Retriever с мок-LLM и мок-LegalX делает до 2 переформулировок при пустом
  результате поиска и возвращает outcome='not_found' только после
  исчерпания попыток;
- явный сигнал LLM "нормы в этой юрисдикции нет" даёт outcome='no_norm',
  отдельно от not_found, без исчерпания оставшихся попыток;
- Verifier получает модель, отличную от модели producer-шага
  (verifier_model_for) — проверяется по вызовам мок-LLM;
- Verifier НЕ получает в промпт рассуждения Retriever — гарантия на уровне
  сигнатуры run(question, fragment, source, profile).

LLM в тестах — только инжектируемый скрипт ответов (тот же паттерн, что и
`importer/tests/test_llm.py` / `test_translator.py`: runner подставляется в
конструктор, сети нет).
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date

import pytest

from importer.build.agents import (
    Classifier,
    ModelsConfig,
    Retriever,
    RetrieverResult,
    Summarizer,
    Verdict,
    Verifier,
    load_models_config,
    verifier_model_for,
)
from importer.build.legalx import NormFragment
from importer.build.llm_client import AgentLLMError, RunnerAgentLLM
from importer.build.profiles import Profile


# ── тестовые дублёры ────────────────────────────────────────────────────

@dataclass
class FakeLegalX:
    """Мок LegalXClient: на i-й вызов search_norms отдаёт responses[i]
    (последний элемент повторяется, если вызовов больше, чем ответов)."""

    responses: list[list[NormFragment]]
    calls: list[tuple[str, str]] = field(default_factory=list)

    def search_norms(self, query, jurisdiction, domains=None, limit=10):
        self.calls.append((query, jurisdiction))
        idx = min(len(self.calls) - 1, len(self.responses) - 1)
        return self.responses[idx]

    def search_cases(self, article, topic=None, limit=5):
        raise NotImplementedError("Retriever не должен вызывать search_cases")


class ScriptedLLM:
    """Мок AgentLLMClient: отдаёт ответы по очереди, фиксирует все (prompt, model)."""

    def __init__(self, responses: list[str]):
        self._responses = list(responses)
        self.calls: list[tuple[str, str]] = []

    def complete(self, prompt: str, model: str) -> str:
        self.calls.append((prompt, model))
        if not self._responses:
            raise AssertionError("ScriptedLLM: запросили ответ сверх скрипта — лишний вызов LLM")
        return self._responses.pop(0)


def fragment(**over) -> NormFragment:
    base = dict(
        fragment_id="frag-1", act_id="act-1", act_title="ПКМ-290",
        article_ref="п. 5", anchor="#p5", content="текст фрагмента нормы",
        act_status="active", valid_from=date(2020, 1, 1), valid_to=None, score=1.0,
    )
    return NormFragment(**{**base, **over})


def norm_profile(tier: str = "cheap") -> Profile:
    return Profile(
        name="norm",
        system_prompt="Ты ищешь нормы права по требованию.",
        response_schema={"type": "object"},
        tier=tier,
    )


# ── Retriever: переформулировки и outcome ───────────────────────────────

def test_retriever_found_immediately_makes_no_llm_calls():
    legalx = FakeLegalX(responses=[[fragment()]])
    llm = ScriptedLLM([])
    result = Retriever(legalx, llm).run("акцизная марка", "UZ", norm_profile())

    assert result.outcome == "found"
    assert result.fragments == [fragment()]
    assert result.queries_tried == ["акцизная марка"]
    assert llm.calls == []


def test_retriever_found_after_one_reformulation():
    legalx = FakeLegalX(responses=[[], [fragment()]])
    llm = ScriptedLLM([json.dumps({"reformulated_query": "уточнённый запрос"})])
    result = Retriever(legalx, llm).run("исходный запрос", "UZ", norm_profile())

    assert result.outcome == "found"
    assert result.fragments == [fragment()]
    assert result.queries_tried == ["исходный запрос", "уточнённый запрос"]
    assert legalx.calls == [("исходный запрос", "UZ"), ("уточнённый запрос", "UZ")]
    assert len(llm.calls) == 1


def test_retriever_exhausts_two_reformulations_then_not_found():
    legalx = FakeLegalX(responses=[[], [], []])  # всегда пусто
    llm = ScriptedLLM([
        json.dumps({"reformulated_query": "переформулировка 1"}),
        json.dumps({"reformulated_query": "переформулировка 2"}),
    ])
    result = Retriever(legalx, llm).run("исходный запрос", "UZ", norm_profile())

    assert result.outcome == "not_found"
    assert result.fragments == []
    assert result.queries_tried == ["исходный запрос", "переформулировка 1", "переформулировка 2"]
    assert legalx.calls == [
        ("исходный запрос", "UZ"),
        ("переформулировка 1", "UZ"),
        ("переформулировка 2", "UZ"),
    ]
    # ровно 2 переформулировки — не больше и не меньше
    assert len(llm.calls) == 2


def test_retriever_not_found_only_after_exhausting_attempts_not_earlier():
    """Если бы Retriever сдавался раньше срока, здесь он вернул бы not_found
    уже после первого пустого поиска — но третий поиск (после второй
    переформулировки) находит фрагмент, и это обязано быть 'found'."""
    legalx = FakeLegalX(responses=[[], [], [fragment()]])
    llm = ScriptedLLM([
        json.dumps({"reformulated_query": "переформулировка 1"}),
        json.dumps({"reformulated_query": "переформулировка 2"}),
    ])
    result = Retriever(legalx, llm).run("q", "UZ", norm_profile())

    assert result.outcome == "found"
    assert result.fragments == [fragment()]
    assert len(llm.calls) == 2


def test_retriever_no_norm_signal_short_circuits_without_exhausting_attempts():
    legalx = FakeLegalX(responses=[[]])
    llm = ScriptedLLM([json.dumps({"no_norm": True})])
    result = Retriever(legalx, llm).run("q", "AE", norm_profile())

    assert result.outcome == "no_norm"
    assert result.fragments == []
    assert result.queries_tried == ["q"]
    # после сигнала no_norm поиск больше не повторяется
    assert legalx.calls == [("q", "AE")]
    assert len(llm.calls) == 1


def test_retriever_no_norm_signal_after_one_reformulation():
    legalx = FakeLegalX(responses=[[], []])
    llm = ScriptedLLM([
        json.dumps({"reformulated_query": "переформулировка 1"}),
        json.dumps({"no_norm": True}),
    ])
    result = Retriever(legalx, llm).run("q", "AE", norm_profile())

    assert result.outcome == "no_norm"
    assert result.queries_tried == ["q", "переформулировка 1"]
    assert len(llm.calls) == 2


def test_retriever_uses_model_from_profile_tier():
    legalx = FakeLegalX(responses=[[], []])
    llm = ScriptedLLM([json.dumps({"no_norm": True})])
    config = load_models_config()
    Retriever(legalx, llm).run("q", "UZ", norm_profile(tier="mid"))

    assert llm.calls[0][1] == config.tiers["mid"]


def test_retriever_garbage_llm_answer_raises():
    legalx = FakeLegalX(responses=[[]])
    llm = ScriptedLLM(["это не JSON"])
    with pytest.raises(AgentLLMError):
        Retriever(legalx, llm).run("q", "UZ", norm_profile())


# ── Verifier: модель другого тира, независимость от producer ───────────

def test_verifier_prompt_built_only_from_signature_args_not_producer_reasoning():
    llm = ScriptedLLM([json.dumps({"passed": True, "reason": "фрагмент отвечает на вопрос"})])
    verifier = Verifier(llm=llm, model="gpt-5-high-reasoning")

    verdict = verifier.run(
        question="Нужна ли маркировка табака акцизной маркой?",
        fragment="текст фрагмента нормы",
        source="ПКМ-290, п. 5",
        profile=norm_profile(),
    )

    assert verdict == Verdict(passed=True, reason="фрагмент отвечает на вопрос", model="gpt-5-high-reasoning")
    assert len(llm.calls) == 1
    prompt, model = llm.calls[0]
    assert model == "gpt-5-high-reasoning"
    assert "текст фрагмента нормы" in prompt
    assert "ПКМ-290, п. 5" in prompt
    # Verifier.run не принимает поле для рассуждений producer'а вообще —
    # значит в промпте не может быть ничего, кроме question/fragment/source/
    # system_prompt профиля. Явно проверяем отсутствие типичного "мусора"
    # рассуждений, который мог бы просочиться при неверной реализации.
    assert "queries_tried" not in prompt and "reformulated" not in prompt


def test_verifier_model_for_producer_cheap_or_mid_is_expensive():
    config = load_models_config()
    assert verifier_model_for(config.tiers["cheap"]) == config.tiers["expensive"]
    assert verifier_model_for(config.tiers["mid"]) == config.tiers["expensive"]


def test_verifier_model_for_producer_expensive_is_mid():
    config = load_models_config()
    assert verifier_model_for(config.tiers["expensive"]) == config.tiers["mid"]


def test_verifier_model_for_unknown_model_raises():
    with pytest.raises(ValueError):
        verifier_model_for("совершенно неизвестная модель")


def test_verifier_gets_model_different_from_producer_end_to_end():
    """Сквозной сценарий брифа: Retriever как producer работает на тире
    cheap, Verifier проверяет его результат — модель verifier'а должна
    отличаться от модели producer'а (проверяем по вызовам мок-LLM)."""
    profile = norm_profile(tier="cheap")
    legalx = FakeLegalX(responses=[[fragment()]])
    retriever_llm = ScriptedLLM([])
    result = Retriever(legalx, retriever_llm).run("акцизная марка", "UZ", profile)

    config = load_models_config()
    producer_model = config.tiers[profile.tier]
    verifier_model = verifier_model_for(producer_model)
    assert verifier_model != producer_model

    verifier_llm = ScriptedLLM([json.dumps({"passed": True, "reason": "ok"})])
    verdict = Verifier(llm=verifier_llm, model=verifier_model).run(
        question="вопрос", fragment=result.fragments[0].content,
        source=result.fragments[0].act_title, profile=profile,
    )

    assert verdict.model == verifier_model
    assert verifier_llm.calls[0][1] != producer_model
    assert verifier_llm.calls[0][1] == verifier_model


def test_verifier_garbage_llm_answer_raises():
    llm = ScriptedLLM(["не могу ответить"])
    with pytest.raises(AgentLLMError):
        Verifier(llm=llm, model="gpt-5").run("q", "f", "s", norm_profile())


def test_verifier_missing_passed_field_raises():
    llm = ScriptedLLM([json.dumps({"reason": "без passed"})])
    with pytest.raises(AgentLLMError):
        Verifier(llm=llm, model="gpt-5").run("q", "f", "s", norm_profile())


# ── Classifier / Summarizer ──────────────────────────────────────────────

def test_classifier_returns_parsed_json_using_tier_model():
    llm = ScriptedLLM([json.dumps({"category": "sanctions"})])
    profile = Profile(name="label", system_prompt="классифицируй", response_schema={"type": "object"}, tier="mid")
    result = Classifier(llm).run("текст требования", profile)

    config = load_models_config()
    assert result == {"category": "sanctions"}
    assert llm.calls[0][1] == config.tiers["mid"]
    assert "текст требования" in llm.calls[0][0]


def test_classifier_garbage_llm_answer_raises():
    llm = ScriptedLLM(["мусор"])
    profile = Profile(name="label", system_prompt="p", response_schema={}, tier="cheap")
    with pytest.raises(AgentLLMError):
        Classifier(llm).run("текст", profile)


def test_summarizer_returns_stripped_text_using_tier_model():
    llm = ScriptedLLM(["  краткое резюме фрагмента  "])
    profile = Profile(name="samples", system_prompt="сожми", response_schema={}, tier="expensive")
    result = Summarizer(llm).run("длинный фрагмент нормы", profile)

    config = load_models_config()
    assert result == "краткое резюме фрагмента"
    assert llm.calls[0][1] == config.tiers["expensive"]
    assert "длинный фрагмент нормы" in llm.calls[0][0]


# ── models.yaml / ModelsConfig ───────────────────────────────────────────

def test_load_models_config_has_three_tiers_with_pricing():
    config = load_models_config()
    assert isinstance(config, ModelsConfig)
    assert set(config.tiers) == {"cheap", "mid", "expensive"}
    for tier_model in config.tiers.values():
        assert tier_model in config.pricing
        assert config.pricing[tier_model]["input_per_1m_usd"] > 0
        assert config.pricing[tier_model]["output_per_1m_usd"] > 0


# ── RunnerAgentLLM (адаптер над паттерном importer.llm) ─────────────────

def test_runner_agent_llm_passes_prompt_and_model_to_runner():
    seen = []

    def runner(prompt: str, model: str) -> str:
        seen.append((prompt, model))
        return "ответ"

    client = RunnerAgentLLM(runner)
    assert client.complete("промпт", "gpt-5") == "ответ"
    assert seen == [("промпт", "gpt-5")]
