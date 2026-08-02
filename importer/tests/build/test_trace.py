"""Трейсинг LLM-вызовов и стоимость по ролям (Задача 29, `trace.py`).

Сценарии брифа:
- `Tracer.record` считает `cost_usd` по прайсу `models.yaml` (вход+выход) и
  пишет строку через `store.save_llm_call`;
- токены оцениваются `len(...)//4`, когда клиент не отдаёт реальный usage
  (скриптованный LLM тестов, `RunnerAgentLLM` со str-раннером);
- реальный `usage`-словарь берётся, когда `RunnerAgentLLM`-раннер вернул
  `(text, usage)`;
- generic-агент (Retriever/Verifier/Classifier/Summarizer) с `tracer=`
  пишет вызов под своей ролью; без `tracer=` — ничего не пишет;
- `trace.cost_report` агрегирует `pipeline.llm_calls` по роли — вход CLI
  `build cost --run <id>`.

`InMemoryStore` (`importer/tests/build/stores.py`) — тот же дублёр `BuildStore`,
что и у `test_orchestrator.py`/`test_cartographer.py` (Задача 29 добавила ему
`save_llm_call`/`list_llm_calls`)."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date

import pytest

from importer.build.agents import (
    Classifier,
    ModelsConfig,
    Retriever,
    Summarizer,
    Verifier,
)
from importer.build.legalx import NormFragment
from importer.build.llm_client import RunnerAgentLLM
from importer.build.profiles import Profile
from importer.build.trace import Tracer, cost_report
from importer.tests.build.stores import InMemoryStore

RUN_ID = "run-1"

TEST_MODELS = ModelsConfig(
    tiers={"cheap": "model-cheap", "mid": "model-mid", "expensive": "model-expensive"},
    pricing={
        "model-cheap": {"input_per_1m_usd": 1.0, "output_per_1m_usd": 2.0},
        "model-mid": {"input_per_1m_usd": 4.0, "output_per_1m_usd": 8.0},
        "model-expensive": {"input_per_1m_usd": 10.0, "output_per_1m_usd": 20.0},
    },
)


class ScriptedLLM:
    """Тот же мок `AgentLLMClient`, что и `test_agents.py`: отдаёт ответы по
    очереди, БЕЗ атрибута `last_usage` — заставляет трейсящий агент оценить
    токены самому (`agents.py: _trace_llm_call`)."""

    def __init__(self, responses: list[str]):
        self._responses = list(responses)
        self.calls: list[tuple[str, str]] = []

    def complete(self, prompt: str, model: str) -> str:
        self.calls.append((prompt, model))
        return self._responses.pop(0)


@dataclass
class FakeLegalX:
    responses: list[list[NormFragment]]
    calls: list[tuple[str, str]] = field(default_factory=list)

    def search_norms(self, query, jurisdiction, domains=None, limit=10):
        self.calls.append((query, jurisdiction))
        idx = min(len(self.calls) - 1, len(self.responses) - 1)
        return self.responses[idx]

    def search_cases(self, article, topic=None, limit=5):
        raise NotImplementedError


def fragment(**over) -> NormFragment:
    base = dict(
        fragment_id="frag-1", act_id="act-1", act_title="ПКМ-290",
        article_ref="п. 5", anchor="#p5", content="текст фрагмента нормы",
        act_status="active", valid_from=date(2020, 1, 1), valid_to=None, score=1.0,
    )
    return NormFragment(**{**base, **over})


def profile(tier: str = "cheap") -> Profile:
    return Profile(
        name="norm", system_prompt="Ты ищешь нормы права.",
        response_schema={"type": "object"}, tier=tier,
    )


# ── Tracer.record: cost по прайсу ────────────────────────────────────────

def test_tracer_record_computes_cost_from_pricing_and_saves_to_store():
    store = InMemoryStore()
    tracer = Tracer(store, RUN_ID, models=TEST_MODELS)

    # model-cheap: input 1.0$/1M, output 2.0$/1M -> 1_000_000 in + 500_000 out
    # = 1.0 + 1.0 = 2.0$
    tracer.record("retriever", "model-cheap", input_tokens=1_000_000, output_tokens=500_000)

    calls = store.list_llm_calls(RUN_ID)
    assert len(calls) == 1
    call = calls[0]
    assert call["role"] == "retriever"
    assert call["model"] == "model-cheap"
    assert call["input_tokens"] == 1_000_000
    assert call["output_tokens"] == 500_000
    assert call["cost_usd"] == pytest.approx(2.0)
    assert call["item_id"] is None


def test_tracer_record_passes_item_id_through():
    store = InMemoryStore()
    Tracer(store, RUN_ID, models=TEST_MODELS).record(
        "verifier", "model-mid", 100, 50, item_id="item-7"
    )
    assert store.list_llm_calls(RUN_ID)[0]["item_id"] == "item-7"


def test_tracer_record_unknown_model_raises():
    store = InMemoryStore()
    tracer = Tracer(store, RUN_ID, models=TEST_MODELS)
    with pytest.raises(ValueError):
        tracer.record("retriever", "совершенно неизвестная модель", 10, 10)


def test_tracer_only_writes_to_its_own_run():
    store = InMemoryStore()
    Tracer(store, "run-a", models=TEST_MODELS).record("classifier", "model-cheap", 10, 10)
    Tracer(store, "run-b", models=TEST_MODELS).record("classifier", "model-cheap", 10, 10)
    assert len(store.list_llm_calls("run-a")) == 1
    assert len(store.list_llm_calls("run-b")) == 1


# ── RunnerAgentLLM.last_usage: реальные токены vs оценка ─────────────────

def test_runner_agent_llm_last_usage_estimated_for_str_runner():
    llm = RunnerAgentLLM(lambda prompt, model: "0123456789ABCDEF")  # 16 chars -> 4 tokens
    text = llm.complete("промпт из 20 символов", "model-cheap")

    assert text == "0123456789ABCDEF"
    assert llm.last_usage == {
        "input_tokens": len("промпт из 20 символов") // 4,
        "output_tokens": len("0123456789ABCDEF") // 4,
        "estimated": True,
    }


def test_runner_agent_llm_last_usage_real_when_runner_returns_tuple():
    llm = RunnerAgentLLM(
        lambda prompt, model: ("ответ", {"input_tokens": 123, "output_tokens": 45})
    )
    text = llm.complete("промпт", "model-cheap")

    assert text == "ответ"
    assert llm.last_usage == {"input_tokens": 123, "output_tokens": 45, "estimated": False}


# ── агенты + tracer: роль, оценка/реальные токены, «без tracer — ничего» ──

def test_retriever_with_tracer_records_call_under_retriever_role_estimated_tokens():
    store = InMemoryStore()
    tracer = Tracer(store, RUN_ID, models=TEST_MODELS)
    legalx = FakeLegalX(responses=[[], []])
    answer = json.dumps({"no_norm": True})
    llm = ScriptedLLM([answer])

    Retriever(legalx, llm, TEST_MODELS, tracer=tracer).run("q", "UZ", profile(tier="cheap"))

    calls = store.list_llm_calls(RUN_ID)
    assert len(calls) == 1
    assert calls[0]["role"] == "retriever"
    assert calls[0]["model"] == "model-cheap"
    prompt, _ = llm.calls[0]
    assert calls[0]["input_tokens"] == len(prompt) // 4
    assert calls[0]["output_tokens"] == len(answer) // 4
    assert calls[0]["cost_usd"] > 0


def test_retriever_without_tracer_records_nothing():
    store = InMemoryStore()
    legalx = FakeLegalX(responses=[[], []])
    llm = ScriptedLLM([json.dumps({"no_norm": True})])

    Retriever(legalx, llm, TEST_MODELS).run("q", "UZ", profile(tier="cheap"))

    assert store.list_llm_calls(RUN_ID) == []


def test_verifier_with_tracer_records_call_under_verifier_role():
    store = InMemoryStore()
    tracer = Tracer(store, RUN_ID, models=TEST_MODELS)
    llm = ScriptedLLM([json.dumps({"passed": True, "reason": "ok"})])

    Verifier(llm=llm, model="model-expensive", tracer=tracer).run(
        question="вопрос", fragment="фрагмент", source="источник", profile=profile(),
    )

    calls = store.list_llm_calls(RUN_ID)
    assert len(calls) == 1
    assert calls[0]["role"] == "verifier"
    assert calls[0]["model"] == "model-expensive"


def test_classifier_with_tracer_records_call_under_classifier_role():
    store = InMemoryStore()
    tracer = Tracer(store, RUN_ID, models=TEST_MODELS)
    llm = ScriptedLLM([json.dumps({"category": "sanctions"})])
    p = Profile(name="label", system_prompt="классифицируй", response_schema={}, tier="mid")

    Classifier(llm, TEST_MODELS, tracer=tracer).run("текст требования", p)

    calls = store.list_llm_calls(RUN_ID)
    assert len(calls) == 1
    assert calls[0]["role"] == "classifier"
    assert calls[0]["model"] == "model-mid"


def test_summarizer_with_tracer_records_call_under_summarizer_role():
    store = InMemoryStore()
    tracer = Tracer(store, RUN_ID, models=TEST_MODELS)
    llm = ScriptedLLM(["  краткое резюме  "])
    p = Profile(name="samples", system_prompt="сожми", response_schema={}, tier="expensive")

    result = Summarizer(llm, TEST_MODELS, tracer=tracer).run("длинный фрагмент", p)

    assert result == "краткое резюме"
    calls = store.list_llm_calls(RUN_ID)
    assert len(calls) == 1
    assert calls[0]["role"] == "summarizer"
    assert calls[0]["model"] == "model-expensive"


def test_classifier_without_tracer_records_nothing():
    store = InMemoryStore()
    llm = ScriptedLLM([json.dumps({"category": "sanctions"})])
    p = Profile(name="label", system_prompt="p", response_schema={}, tier="mid")

    Classifier(llm, TEST_MODELS).run("текст", p)

    assert store.list_llm_calls(RUN_ID) == []


def test_agent_with_tracer_uses_real_usage_from_runner_agent_llm():
    """Через `RunnerAgentLLM`, чей раннер отдаёт `(text, usage)` — реальные
    токены бэкенда должны попасть в `pipeline.llm_calls` НЕ оценкой
    `len(...)//4`, а как есть."""
    store = InMemoryStore()
    tracer = Tracer(store, RUN_ID, models=TEST_MODELS)
    runner_llm = RunnerAgentLLM(
        lambda prompt, model: (
            json.dumps({"category": "sanctions"}),
            {"input_tokens": 777, "output_tokens": 33},
        )
    )
    p = Profile(name="label", system_prompt="классифицируй", response_schema={}, tier="cheap")

    Classifier(runner_llm, TEST_MODELS, tracer=tracer).run("текст", p)

    calls = store.list_llm_calls(RUN_ID)
    assert len(calls) == 1
    assert calls[0]["input_tokens"] == 777
    assert calls[0]["output_tokens"] == 33


def test_agent_custom_role_overrides_default():
    store = InMemoryStore()
    tracer = Tracer(store, RUN_ID, models=TEST_MODELS)
    llm = ScriptedLLM([json.dumps({"category": "sanctions"})])
    p = Profile(name="label", system_prompt="p", response_schema={}, tier="cheap")

    Classifier(llm, TEST_MODELS, tracer=tracer, role="lifecycle-classifier").run("текст", p)

    assert store.list_llm_calls(RUN_ID)[0]["role"] == "lifecycle-classifier"


# ── cost_report: агрегация по роли для CLI `build cost --run <id>` ───────

def test_cost_report_aggregates_calls_by_role_with_totals():
    store = InMemoryStore()
    tracer = Tracer(store, RUN_ID, models=TEST_MODELS)
    tracer.record("retriever", "model-cheap", 1_000_000, 0)  # 1.0$
    tracer.record("retriever", "model-cheap", 1_000_000, 0)  # 1.0$
    tracer.record("verifier", "model-expensive", 1_000_000, 1_000_000)  # 30.0$

    report = cost_report(store, RUN_ID)

    assert report.run_id == RUN_ID
    by_role = {row.role: row for row in report.rows}
    assert by_role["retriever"].calls == 2
    assert by_role["retriever"].input_tokens == 2_000_000
    assert by_role["retriever"].cost_usd == pytest.approx(2.0)
    assert by_role["verifier"].calls == 1
    assert by_role["verifier"].cost_usd == pytest.approx(30.0)
    assert report.total_calls == 3
    assert report.total_cost_usd == pytest.approx(32.0)
    assert "retriever" in report.markdown
    assert "verifier" in report.markdown
    assert "итого" in report.markdown


def test_cost_report_empty_run_has_no_rows_but_valid_markdown():
    store = InMemoryStore()
    report = cost_report(store, "run-without-calls")

    assert report.rows == []
    assert report.total_calls == 0
    assert report.total_cost_usd == 0.0
    assert "итого" in report.markdown


def test_cost_report_only_includes_calls_of_requested_run():
    store = InMemoryStore()
    Tracer(store, "run-a", models=TEST_MODELS).record("retriever", "model-cheap", 100, 100)
    Tracer(store, "run-b", models=TEST_MODELS).record("retriever", "model-cheap", 100, 100)

    report = cost_report(store, "run-a")

    assert report.total_calls == 1
