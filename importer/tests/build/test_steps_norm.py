"""Шаги 'norm' и 'summary' (Задача 17): Retriever+Verifier по норме,
Summarizer+Verifier по саммари — обе пары с независимой верификацией
(«Блок 2»).

Сценарии из брифа/уточнений контроллера (task-17-brief.md):
- 'norm' happy-path: LegalX отдаёт фрагмент по одному из вопросов ->
  Verifier pass -> StepResult(ok), фрагмент и его реквизиты попадают в
  ItemContext.data;
- 'norm' not_found (все вопросы исчерпали переформулировки без сигнала
  no_norm) -> StepResult(fail) — обычный retry/эскалация Orchestrator'а
  (needs_attention после N=3 подряд, не отдельная ветка в самом шаге);
- 'norm' no_norm (ВСЕ вопросы дали сигнал no_norm) -> StepResult(no_norm) —
  терминальный валидный исход;
- 'norm' verifier fail (фрагмент нашёлся, но Verifier не пропустил ни один
  вопрос) -> StepResult(fail), ItemContext не наполняется;
- 'norm' деградация question_writer (ретраи исчерпаны) -> StepResult(fail),
  а не необработанное исключение;
- 'summary' happy-path: Summarizer сжимает найденный шагом 'norm' фрагмент
  -> Verifier pass -> StepResult(ok), саммари в ItemContext.data;
- 'summary' verifier fail -> StepResult(fail), саммари в контекст не идёт;
- 'summary' без предварительного 'norm' (нет norm_fragment в контексте) ->
  StepResult(fail), не AttributeError, LLM вообще не вызывается;
- вердикты попадают в StepResult.verdicts, а атрибуция по шагу ('norm' vs
  'summary') — на стороне Orchestrator'а (save_verdicts(item_id, step,
  verdicts) вызывается с именем ТЕКУЩЕГО шага STEP_ORDER, см.
  orchestrator.py:_run_from) — проверяется интеграционным прогоном через
  InMemoryStore/Orchestrator на РЕАЛЬНЫХ NormStep/SummaryStep, не на
  фейковых ScriptedStep, как в test_orchestrator.py.

LLM/LegalX — только инжектируемые скрипты ответов (тот же паттерн, что и
test_agents.py/test_cartographer.py: ScriptedLLM/FakeLegalX, никакой сети).
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date

from importer.build.agents import load_models_config, verifier_model_for
from importer.build.legalx import NormFragment
from importer.build.orchestrator import MapRecord, Orchestrator
from importer.build.steps import STEP_ORDER, ItemContext, ItemRecord, StepResult
from importer.build.steps_norm import NormStep, SummaryStep
from importer.tests.build.stores import InMemoryStore


# ── тестовые дублёры ────────────────────────────────────────────────────


@dataclass
class FakeLegalX:
    """Мок LegalXClient: на i-й вызов search_norms отдаёт responses[i]
    (последний элемент повторяется, если вызовов больше, чем ответов) — та
    же семантика, что у FakeLegalX из test_agents.py."""

    responses: list[list[NormFragment]]
    calls: list[tuple[str, str]] = field(default_factory=list)

    def search_norms(self, query, jurisdiction, domains=None, limit=10):
        self.calls.append((query, jurisdiction))
        idx = min(len(self.calls) - 1, len(self.responses) - 1)
        return self.responses[idx]

    def search_cases(self, article, topic=None, limit=5):
        raise NotImplementedError("шаг 'norm' не должен вызывать search_cases")


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


class SpySummaryStore:
    """Минимальный BuildStore-дублёр для изолированных юнит-тестов
    'summary' (Задача 27, фикс-раунд ревью) — эти тесты не гоняют
    Orchestrator/полноценный InMemoryStore (айтем никогда не был бы
    `create_items`-нут), нужен только `set_item_summary`."""

    def __init__(self):
        self.summaries: dict[str, str] = {}

    def set_item_summary(self, item_id: str, summary: str) -> None:
        self.summaries[item_id] = summary


def fragment(**over) -> NormFragment:
    base = dict(
        fragment_id="frag-1", act_id="act-1", act_title="ПКМ-290",
        article_ref="п. 5", anchor="#p5", content="текст фрагмента нормы",
        act_status="active", valid_from=date(2020, 1, 1), valid_to=None, score=1.0,
    )
    return NormFragment(**{**base, **over})


def item_ctx(**over) -> ItemContext:
    base = dict(
        id="item-1", run_id="run-1",
        expected_item="акцизная марка на пачке сигарет", category_slug="marking",
    )
    return ItemContext(item=ItemRecord(**{**base, **over}))


def two_questions_answer(
    text0: str = "вопрос про акцизную марку", text1: str = "вопрос про маркировку"
) -> str:
    return json.dumps(
        [
            {"text": text0, "expected_schema": {"type": "object"}},
            {"text": text1, "expected_schema": {"type": "object"}},
        ],
        ensure_ascii=False,
    )


def reformulate(text: str) -> str:
    return json.dumps({"reformulated_query": text})


def no_norm_signal() -> str:
    return json.dumps({"no_norm": True})


def verdict_json(passed: bool, reason: str = "") -> str:
    return json.dumps({"passed": passed, "reason": reason})


def approved_map(**over) -> MapRecord:
    base = dict(
        id="map-1", group_ref="2203", jurisdiction="UZ", status="approved",
        payload=[{"expected_item": "акцизная марка на пачке сигарет", "category_slug": "marking"}],
    )
    return MapRecord(**{**base, **over})


# ── шаг 'norm': happy-path ───────────────────────────────────────────────


def test_norm_step_happy_path_fills_context_and_returns_ok():
    legalx = FakeLegalX(responses=[[fragment()]])
    llm = ScriptedLLM([
        two_questions_answer(),
        verdict_json(True, "фрагмент отвечает на вопрос"),
    ])
    step = NormStep(legalx, llm, jurisdiction="UZ")
    ctx = item_ctx()

    result = step(ctx)

    assert result.status == "ok"
    assert len(result.verdicts) == 1
    assert result.verdicts[0].passed is True
    assert ctx.data["norm_fragment"] == fragment()
    assert ctx.data["norm_fragments"] == [fragment()]
    assert ctx.data["norm_source"] == "ПКМ-290"
    assert ctx.data["norm_question"] == "вопрос про акцизную марку"
    # найдено и подтверждено уже по первому вопросу — второй не понадобился
    assert len(legalx.calls) == 1


def test_norm_step_uses_mid_tier_and_verifier_gets_expensive_tier():
    legalx = FakeLegalX(responses=[[fragment()]])
    llm = ScriptedLLM([
        two_questions_answer(),
        verdict_json(True),
    ])
    step = NormStep(legalx, llm)

    step(item_ctx())

    config = load_models_config()
    # 1-й вызов LLM — write_questions (cheap), 2-й — Verifier
    verifier_call_model = llm.calls[1][1]
    assert verifier_call_model == config.tiers["expensive"]
    assert verifier_call_model == verifier_model_for(config.tiers["mid"])


# ── шаг 'norm': not_found → fail ─────────────────────────────────────────


def test_norm_step_not_found_for_all_questions_returns_fail():
    legalx = FakeLegalX(responses=[[]])  # всегда пусто, ни разу не находит
    llm = ScriptedLLM([
        two_questions_answer(),
        reformulate("q0 переформулировка 1"), reformulate("q0 переформулировка 2"),
        reformulate("q1 переформулировка 1"), reformulate("q1 переформулировка 2"),
    ])
    step = NormStep(legalx, llm)

    result = step(item_ctx())

    assert result.status == "fail"
    assert result.verdicts == []  # ни разу не дошли до Verifier — фрагментов не было
    assert result.error is not None


# ── шаг 'norm': no_norm для ВСЕХ вопросов → StepResult(no_norm) ─────────


def test_norm_step_no_norm_for_all_questions_returns_no_norm():
    legalx = FakeLegalX(responses=[[]])
    llm = ScriptedLLM([
        two_questions_answer(),
        no_norm_signal(),
        no_norm_signal(),
    ])
    step = NormStep(legalx, llm)

    result = step(item_ctx())

    assert result.status == "no_norm"
    assert result.verdicts == []


# ── шаг 'norm': смешанные исходы → fail, НЕ no_norm ──────────────────────
#
# Пин-тесты фикс-раунда ревью Задачи 17 (Important): предыдущие тесты
# покрывали только ОДНОРОДНЫЕ наборы исходов («все no_norm», «все
# not_found») — регрессия агрегации `all(outcome == "no_norm" ...)` ->
# `any(outcome == "no_norm" ...)` в steps_norm.py прошла бы мимо них
# незамеченной (для набора из одних no_norm `any` и `all` дают одинаковый
# результат). Эти тесты специально смешивают no_norm с другим исходом —
# только смешанный набор различает `all` от `any`.


def test_norm_step_mixed_no_norm_and_not_found_returns_fail_not_no_norm():
    legalx = FakeLegalX(responses=[[]])  # всегда пусто — оба вопроса ищут вслепую
    llm = ScriptedLLM([
        two_questions_answer(),
        no_norm_signal(),  # q0 -> no_norm (сигнал сразу, без реформулировок)
        reformulate("q1 переформулировка 1"), reformulate("q1 переформулировка 2"),  # q1 -> not_found
    ])
    step = NormStep(legalx, llm)

    result = step(item_ctx())

    assert result.status == "fail"
    assert result.status != "no_norm"
    assert result.verdicts == []


def test_norm_step_mixed_no_norm_and_verifier_fail_returns_fail_not_no_norm():
    legalx = FakeLegalX(responses=[[], [fragment()]])  # q0 пусто, q1 находит
    llm = ScriptedLLM([
        two_questions_answer(),
        no_norm_signal(),  # q0 -> no_norm
        verdict_json(False, "фрагмент не отвечает на вопрос"),  # q1 -> found, но verifier отклонил
    ])
    step = NormStep(legalx, llm)

    result = step(item_ctx())

    assert result.status == "fail"
    assert result.status != "no_norm"
    assert len(result.verdicts) == 1
    assert result.verdicts[0].passed is False


# ── шаг 'norm': фрагмент нашёлся, но Verifier не пропустил ни один ──────


def test_norm_step_verifier_rejects_all_found_fragments_returns_fail():
    legalx = FakeLegalX(responses=[[fragment()], [fragment(fragment_id="frag-2")]])
    llm = ScriptedLLM([
        two_questions_answer(),
        verdict_json(False, "фрагмент не отвечает на вопрос"),
        verdict_json(False, "фрагмент тоже не отвечает"),
    ])
    step = NormStep(legalx, llm)
    ctx = item_ctx()

    result = step(ctx)

    assert result.status == "fail"
    assert len(result.verdicts) == 2
    assert all(not v.passed for v in result.verdicts)
    assert "norm_fragment" not in ctx.data


# ── шаг 'norm': деградация LLM (write_questions исчерпал ретраи) ────────


def test_norm_step_question_writer_exhausted_returns_fail_not_raise():
    legalx = FakeLegalX(responses=[[]])
    llm = ScriptedLLM(["не JSON", "тоже не JSON"])
    step = NormStep(legalx, llm)

    result = step(item_ctx())

    assert result.status == "fail"
    assert result.error is not None


# ── шаг 'summary': happy-path ────────────────────────────────────────────


def test_summary_step_happy_path_fills_context_and_returns_ok():
    llm = ScriptedLLM([
        "простыми словами: нужна акцизная марка",
        verdict_json(True, "саммари точное"),
    ])
    store = SpySummaryStore()
    step = SummaryStep(llm, store)
    ctx = item_ctx()
    ctx.data["norm_fragment"] = fragment()

    result = step(ctx)

    assert result.status == "ok"
    assert ctx.data["summary"] == "простыми словами: нужна акцизная марка"
    assert len(result.verdicts) == 1
    assert result.verdicts[0].passed is True
    # Задача 27, фикс-раунд ревью: саммари персистится через set_item_summary
    assert store.summaries[ctx.item.id] == "простыми словами: нужна акцизная марка"


def test_summary_step_uses_cheap_tier_and_verifier_gets_expensive_tier():
    llm = ScriptedLLM([
        "саммари",
        verdict_json(True),
    ])
    step = SummaryStep(llm, SpySummaryStore())
    ctx = item_ctx()
    ctx.data["norm_fragment"] = fragment()

    step(ctx)

    config = load_models_config()
    assert llm.calls[0][1] == config.tiers["cheap"]
    assert llm.calls[1][1] == config.tiers["expensive"]


# ── шаг 'summary': verifier fail ─────────────────────────────────────────


def test_summary_step_verifier_fail_returns_fail_and_does_not_populate_summary():
    llm = ScriptedLLM([
        "саммари, которое искажает норму",
        verdict_json(False, "саммари добавляет то, чего нет в норме"),
    ])
    store = SpySummaryStore()
    step = SummaryStep(llm, store)
    ctx = item_ctx()
    ctx.data["norm_fragment"] = fragment()

    result = step(ctx)

    assert result.status == "fail"
    assert len(result.verdicts) == 1
    assert result.verdicts[0].passed is False
    assert "summary" not in ctx.data
    # Verifier отклонил — set_item_summary НЕ вызван (нечего персистить)
    assert store.summaries == {}


# ── шаг 'summary': без предварительного 'norm' ───────────────────────────


def test_summary_step_without_norm_fragment_returns_fail_not_raise():
    llm = ScriptedLLM([])
    step = SummaryStep(llm, SpySummaryStore())

    result = step(item_ctx())

    assert result.status == "fail"
    assert llm.calls == []  # контракт проверен до единого вызова LLM


# ── интеграция: Orchestrator + InMemoryStore — вердикты с атрибуцией шага ─


def test_norm_and_summary_steps_integrate_with_orchestrator_verdict_attribution():
    """Orchestrator сам приписывает верный шаг при save_verdicts (по имени
    ТЕКУЩЕГО шага STEP_ORDER, см. orchestrator.py:_run_from) — здесь это
    проверяется на РЕАЛЬНЫХ NormStep/SummaryStep, а не на фейковых
    ScriptedStep, как в test_orchestrator.py."""
    store = InMemoryStore()
    store.maps["map-1"] = approved_map()

    legalx = FakeLegalX(responses=[[fragment()]])
    llm = ScriptedLLM([
        two_questions_answer(),
        verdict_json(True, "норма подтверждена"),
        "простыми словами: нужна акцизная марка",
        verdict_json(True, "саммари точное"),
    ])
    norm_step = NormStep(legalx, llm)
    summary_step = SummaryStep(llm, store)

    steps = {name: (lambda ctx: StepResult(status="ok")) for name in STEP_ORDER}
    steps["norm"] = norm_step
    steps["summary"] = summary_step

    report = Orchestrator(store, steps=steps).run_group("map-1")

    assert report.published == 1
    step_names = {step_name for (_id, step_name, _verdicts) in store.verdicts}
    assert step_names == {"norm", "summary"}
    norm_verdicts = next(v for (_id, s, v) in store.verdicts if s == "norm")
    summary_verdicts = next(v for (_id, s, v) in store.verdicts if s == "summary")
    assert norm_verdicts[0].passed is True
    assert summary_verdicts[0].passed is True
    # Задача 27, фикс-раунд ревью: саммари персистится в pipeline.items.summary_text
    item = next(iter(store.items.values()))
    assert item.summary_text == "простыми словами: нужна акцизная марка"


def test_norm_step_not_found_escalates_to_needs_attention_via_orchestrator():
    """not_found -> StepResult(fail) -> обычный retry Orchestrator'а; после
    N=3 подряд — needs_attention (брифовское "not_found -> needs_attention"
    реализовано на стороне Orchestrator'а, не отдельной веткой в шаге)."""
    store = InMemoryStore()
    store.maps["map-1"] = approved_map()

    legalx = FakeLegalX(responses=[[]])
    one_attempt = [
        two_questions_answer(),
        reformulate("r1"), reformulate("r2"),
        reformulate("r3"), reformulate("r4"),
    ]
    llm = ScriptedLLM(one_attempt * 3)  # MAX_STEP_RETRIES=3 попытки шага подряд
    norm_step = NormStep(legalx, llm)

    steps = {name: (lambda ctx: StepResult(status="ok")) for name in STEP_ORDER}
    steps["norm"] = norm_step

    report = Orchestrator(store, steps=steps).run_group("map-1")

    assert report.needs_attention == 1
    assert report.published == 0
    item = next(iter(store.items.values()))
    assert item.status == "needs_attention"


# ── регистрация в реестре steps.py ───────────────────────────────────────


def test_norm_and_summary_steps_are_registered_in_steps_registry():
    """Импорт steps_norm — уже сам по себе регистрация (см. докстринг
    модуля): к моменту выполнения этого теста 'norm'/'summary' уже
    зарегистрированы в глобальном реестре steps.py (модуль импортирован
    выше, на уровне файла)."""
    from importer.build.steps import get_step

    assert callable(get_step("norm"))
    assert callable(get_step("summary"))


def test_load_default_steps_imports_steps_norm_module():
    from importer.build.steps import get_step, load_default_steps

    load_default_steps()  # идемпотентно — повторный вызов не должен падать

    assert callable(get_step("norm"))
    assert callable(get_step("summary"))
