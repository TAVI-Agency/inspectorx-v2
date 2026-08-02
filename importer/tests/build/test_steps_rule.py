"""Шаг 'rule' (Задача 19): Rule-maker (Classifier в роли producer'а) +
Verifier — «критическая точка» ADR-0003 решение 5.

Сценарии из брифа/уточнений контроллера (task-19-brief.md):
- happy-path: Rule-maker выдаёт ≥1 правило, Verifier подтверждает КАЖДОЕ
  отдельным вызовом -> StepResult(ok), `ctx.data['rules']` — только
  подтверждённые правила с `verified=True`;
- Rule-maker/producer — тир `mid`, Verifier каждого правила — `expensive`
  (`verifier_model_for('mid') == 'expensive'`, ADR-0003 решение 9);
- невалидный вывод Rule-maker'а (не JSON / не массив / пустой массив) ->
  ретрай с указанием ошибки -> валидный вывод -> успех;
- дважды невалидный вывод -> StepResult(fail), Verifier вообще не вызывается;
- Verifier отклонил хотя бы одно правило из набора -> StepResult(fail) со
  ВСЕМИ вердиктами (и pass, и fail) в результате, `ctx.data` не наполняется
  ключом 'rules' (консервативная политика «критической точки»: частично
  подтверждённый набор — не публикуем);
- мутационный пин-тест: смешанный набор (не все правила отклонены) должен
  давать fail — отличает `any(rejected)` от `all(rejected)`, тот же приём,
  что и пин-тесты 'norm' в test_steps_norm.py;
- шаг применяется не ко всем категориям: `category_slug != 'marking'`
  (включая отсутствие ключа вовсе) -> StepResult(ok), пустой список правил,
  `ctx.data['skipped_rule_step'] = True`, ноль обращений к LLM — это НЕ fail
  (у требования вне маркировки/упаковки нет машинного правила этикетки);
- 'marking' без предварительного 'norm' (нет `norm_fragment` в контексте) ->
  StepResult(fail), не AttributeError, LLM вообще не вызывается;
- verifier-фейл x3 (MAX_STEP_RETRIES) -> needs_attention всего айтема через
  обычный путь Orchestrator'а (тот же паттерн, что not_found у 'norm');
- регистрация в реестре steps.py.

LLM — только инжектируемый скрипт ответов (тот же паттерн, что и
test_steps_norm.py/test_steps_classify.py: ScriptedLLM, никакой сети).
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date

from importer.build.agents import load_models_config, verifier_model_for
from importer.build.legalx import NormFragment
from importer.build.orchestrator import MapRecord, Orchestrator
from importer.build.steps import STEP_ORDER, ItemContext, ItemRecord, StepResult
from importer.build.steps_rule import RuleStep
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


def rule_maker_response(*rules: dict) -> str:
    return json.dumps({"rules": list(rules)}, ensure_ascii=False)


def verdict_json(passed: bool, reason: str = "") -> str:
    return json.dumps({"passed": passed, "reason": reason}, ensure_ascii=False)


def fragment(**over) -> NormFragment:
    base = dict(
        fragment_id="frag-1", act_id="act-1", act_title="ПКМ-290",
        article_ref="п. 5", anchor="#p5",
        content="на потребительской упаковке обязательны состав на узбекском и штрих-код EAN-13",
        act_status="active", valid_from=date(2020, 1, 1), valid_to=None, score=1.0,
    )
    return NormFragment(**{**base, **over})


def item_ctx(*, category_slug: str | None = "marking", with_norm_fragment: bool = True) -> ItemContext:
    item = ItemRecord(
        id="item-1", run_id="run-1",
        expected_item="акцизная марка на пачке сигарет", category_slug=None,
    )
    ctx = ItemContext(item=item)
    if with_norm_fragment:
        ctx.data["norm_fragment"] = fragment()
    if category_slug is not None:
        ctx.data["category_slug"] = category_slug
    return ctx


def approved_map(**over) -> MapRecord:
    base = dict(
        id="map-1", group_ref="2203", jurisdiction="UZ", status="approved",
        payload=[{"expected_item": "акцизная марка на пачке сигарет", "category_slug": "marking"}],
    )
    return MapRecord(**{**base, **over})


# ── шаг 'rule': не-marking категория -> ok + пусто + skip, без LLM ─────


def test_rule_step_non_marking_category_skips_with_empty_rules_and_flag():
    llm = ScriptedLLM(responses=[])
    step = RuleStep(llm)
    ctx = item_ctx(category_slug="sps")

    result = step(ctx)

    assert result.status == "ok"
    assert ctx.data["rules"] == []
    assert ctx.data["skipped_rule_step"] is True
    assert llm.calls == []


def test_rule_step_missing_category_slug_in_ctx_also_skips():
    """category_slug ещё не положен шагом 'category' (например, партиальный
    rerun не с начала) — трактуется так же, как «не marking», не как fail."""
    llm = ScriptedLLM(responses=[])
    step = RuleStep(llm)
    ctx = item_ctx(category_slug=None)
    assert "category_slug" not in ctx.data

    result = step(ctx)

    assert result.status == "ok"
    assert ctx.data["rules"] == []
    assert ctx.data["skipped_rule_step"] is True
    assert llm.calls == []


# ── шаг 'rule': marking, но нет norm_fragment -> fail, не raise ────────


def test_rule_step_marking_without_norm_fragment_returns_fail_not_raise():
    llm = ScriptedLLM(responses=[])
    step = RuleStep(llm)
    ctx = item_ctx(with_norm_fragment=False)

    result = step(ctx)

    assert result.status == "fail"
    assert "norm_fragment" in result.error.lower() or "norm" in result.error.lower()
    assert llm.calls == []


# ── шаг 'rule': happy-path — 2 правила, оба подтверждены ────────────────


def test_rule_step_happy_path_two_rules_both_verified_returns_ok():
    llm = ScriptedLLM([
        rule_maker_response(
            {"field": "состав", "lang": "uz", "required": True},
            {"barcode": "EAN-13"},
        ),
        verdict_json(True, "правило 1 соответствует норме"),
        verdict_json(True, "правило 2 соответствует норме"),
    ])
    step = RuleStep(llm)
    ctx = item_ctx()

    result = step(ctx)

    assert result.status == "ok"
    assert len(result.verdicts) == 2
    assert all(v.passed for v in result.verdicts)
    assert ctx.data["rules"] == [
        {"rule": {"field": "состав", "lang": "uz", "required": True}, "verified": True},
        {"rule": {"barcode": "EAN-13"}, "verified": True},
    ]


def test_rule_step_uses_mid_tier_and_verifier_gets_expensive_tier():
    llm = ScriptedLLM([
        rule_maker_response({"barcode": "EAN-13"}),
        verdict_json(True),
    ])
    step = RuleStep(llm)

    step(item_ctx())

    config = load_models_config()
    assert llm.calls[0][1] == config.tiers["mid"]
    verifier_call_model = llm.calls[1][1]
    assert verifier_call_model == config.tiers["expensive"]
    assert verifier_call_model == verifier_model_for(config.tiers["mid"])


# ── шаг 'rule': невалидный вывод Rule-maker'а -> ретрай -> успех ────────


def test_rule_step_invalid_maker_output_retries_with_error_message_then_succeeds():
    llm = ScriptedLLM([
        "это вообще не JSON",
        rule_maker_response({"barcode": "EAN-13"}),
        verdict_json(True),
    ])
    step = RuleStep(llm)
    ctx = item_ctx()

    result = step(ctx)

    assert result.status == "ok"
    assert ctx.data["rules"] == [{"rule": {"barcode": "EAN-13"}, "verified": True}]
    assert len(llm.calls) == 3
    retry_prompt = llm.calls[1][0]
    assert "невалид" in retry_prompt.lower()


def test_rule_step_empty_rules_array_is_treated_as_invalid_and_retries():
    """Пустой массив формально валидный JSON, но брифом требуется ≥1
    правило — пустой список так же уходит в ретрай, как невалидный JSON."""
    llm = ScriptedLLM([
        json.dumps({"rules": []}),
        rule_maker_response({"barcode": "EAN-13"}),
        verdict_json(True),
    ])
    step = RuleStep(llm)
    ctx = item_ctx()

    result = step(ctx)

    assert result.status == "ok"
    assert ctx.data["rules"] == [{"rule": {"barcode": "EAN-13"}, "verified": True}]


# ── шаг 'rule': дважды невалидный вывод -> fail ─────────────────────────


def test_rule_step_twice_invalid_maker_output_returns_fail():
    llm = ScriptedLLM([
        "мусор",
        "снова не JSON",
    ])
    step = RuleStep(llm)
    ctx = item_ctx()

    result = step(ctx)

    assert result.status == "fail"
    assert result.error is not None
    assert result.verdicts == []
    assert "rules" not in ctx.data


# ── шаг 'rule': Verifier отклонил хотя бы одно правило -> fail ──────────


def test_rule_step_one_of_two_rules_rejected_by_verifier_returns_fail():
    llm = ScriptedLLM([
        rule_maker_response(
            {"field": "состав", "lang": "uz", "required": True},
            {"barcode": "EAN-13"},
        ),
        verdict_json(True, "первое ок"),
        verdict_json(False, "второе не упомянуто в норме"),
    ])
    step = RuleStep(llm)
    ctx = item_ctx()

    result = step(ctx)

    assert result.status == "fail"
    assert len(result.verdicts) == 2
    assert result.verdicts[0].passed is True
    assert result.verdicts[1].passed is False
    assert "rules" not in ctx.data


def test_rule_step_any_rejected_not_all_rejected_causes_fail_mutation_pin():
    """Пин-тест политики «исключено ХОТЯ БЫ одно -> fail всего набора», не
    «отклонены ВСЕ -> fail»: 3 правила, отклонено только одно из трёх. Если
    бы реализация ошибочно проверяла `all(rejected)` вместо `any(rejected)`,
    этот тест поймал бы регрессию — на однородном наборе (все pass или все
    fail) `any`/`all` дают одинаковый результат, различает их только
    смешанный набор (тот же приём, что и пин-тесты 'norm' в
    test_steps_norm.py: test_norm_step_mixed_no_norm_and_not_found_...)."""
    llm = ScriptedLLM([
        rule_maker_response(
            {"field": "состав", "lang": "uz", "required": True},
            {"barcode": "EAN-13"},
            {"field": "срок годности", "lang": "ru", "required": True},
        ),
        verdict_json(True),
        verdict_json(False, "штрих-код не упомянут в норме"),
        verdict_json(True),
    ])
    step = RuleStep(llm)
    ctx = item_ctx()

    result = step(ctx)

    assert result.status == "fail"
    assert len(result.verdicts) == 3
    assert [v.passed for v in result.verdicts] == [True, False, True]
    assert "rules" not in ctx.data


# ── интеграция: Orchestrator — verifier-фейл x3 -> needs_attention ──────


def test_rule_step_verifier_fail_x3_escalates_to_needs_attention_via_orchestrator():
    """Консервативная политика «критической точки» (ADR-0003 р.5, «кривое
    правило = кривой фото-чек»): ретраит ЦЕЛЫЙ шаг оркестратор, не сам шаг;
    после MAX_STEP_RETRIES=3 подряд провалов — needs_attention."""
    store = InMemoryStore()
    store.maps["map-1"] = approved_map()

    one_attempt = [
        rule_maker_response({"barcode": "EAN-13"}),
        verdict_json(False, "правило не соответствует норме"),
    ]
    llm = ScriptedLLM(one_attempt * 3)
    rule_step = RuleStep(llm)

    def norm_stub(ctx: ItemContext) -> StepResult:
        ctx.data["norm_fragment"] = fragment()
        return StepResult(status="ok")

    def category_stub(ctx: ItemContext) -> StepResult:
        ctx.data["category_slug"] = "marking"
        return StepResult(status="ok")

    steps = {name: (lambda ctx: StepResult(status="ok")) for name in STEP_ORDER}
    steps["norm"] = norm_stub
    steps["category"] = category_stub
    steps["rule"] = rule_step

    report = Orchestrator(store, steps=steps).run_group("map-1")

    assert report.needs_attention == 1
    assert report.published == 0
    item = next(iter(store.items.values()))
    assert item.status == "needs_attention"


# ── регистрация в реестре steps.py ───────────────────────────────────────


def test_rule_step_is_registered_in_steps_registry():
    from importer.build.steps import get_step

    assert callable(get_step("rule"))


def test_load_default_steps_imports_steps_rule_module():
    from importer.build.steps import get_step, load_default_steps

    load_default_steps()  # идемпотентно — повторный вызов не должен падать

    assert callable(get_step("rule"))
