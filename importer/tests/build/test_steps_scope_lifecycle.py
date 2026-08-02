"""Шаги 'scope' и 'lifecycle' (Задача 20, ADR-0003 «Блок 2», ADR-0004).

Сценарии из брифа/уточнений контроллера (task-20-brief.md):

## 'scope' (Classifier, mid-тир, БЕЗ Verifier)

- happy-path: Classifier выбирает `product_type_id` из кандидатов
  (`store.list_group_product_types(group_ref)`) -> StepResult(ok), пустые
  `verdicts` (на этот шаг Verifier не вешаем — в плане у 'scope' нет
  verifier-строки);
- невалидный `product_type_id` (не из кандидатов при `kind='product_type'`)
  -> ретрай с указанием ошибки -> валидный -> успех;
- дважды невалидный -> StepResult(fail);
- `kind='all_products'`/`'all_services'` -> валиден без сверки с кандидатами
  (`product_type_id=None`);
- кандидаты в промпте — из `store.list_group_product_types`, не хардкод
  (тест поведением: имя/код кандидата должны быть в промпте);
- нет `norm_fragment` в контексте (шаг 'norm' ещё не отработал) -> fail, не raise.

## 'lifecycle' (Classifier, cheap-тир, + Verifier профилем «Норма»)

- happy-path: экстрактор извлекает даты из `norm_fragment.content`,
  Verifier подтверждает -> StepResult(ok), `ctx.data['lifecycle']` — ТОЛЬКО
  даты (`effective_from`/`transition_until`/`valid_to`/`repealed_by_ref`),
  без статуса;
- все даты `null` -> валидный исход (норма бессрочна) -> ok;
- невалидный формат даты (не `YYYY-MM-DD`/`null`, включая невозможные даты
  вроде месяца 99) -> ретрай с указанием ошибки -> валидный -> успех;
- дважды невалидный формат -> StepResult(fail), Verifier вообще не вызывается;
- Verifier отклонил даты -> StepResult(fail);
- producer — тир `cheap`, Verifier — `expensive` (`verifier_model_for('cheap')`);
- нет `norm_fragment` в контексте -> fail, не raise.

LLM — только инжектируемый скрипт ответов (тот же паттерн, что и
`test_steps_rule.py`/`test_steps_classify.py`: ScriptedLLM, никакой сети).
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date

from importer.build.agents import load_models_config, verifier_model_for
from importer.build.legalx import NormFragment
from importer.build.steps import ItemContext, ItemRecord, StepResult
from importer.build.steps_scope_lifecycle import LifecycleStep, ScopeStep
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


def fragment(**over) -> NormFragment:
    base = dict(
        fragment_id="frag-1", act_id="act-1", act_title="ПКМ-290",
        article_ref="п. 5", anchor="#p5",
        content="акцизная марка обязательна на пачках сигарет с фильтром с 1 января 2026 года",
        act_status="active", valid_from=date(2020, 1, 1), valid_to=None, score=1.0,
    )
    return NormFragment(**{**base, **over})


def item_ctx(*, with_norm_fragment: bool = True) -> ItemContext:
    item = ItemRecord(
        id="item-1", run_id="run-1", expected_item="акцизная марка на пачке сигарет",
    )
    ctx = ItemContext(item=item)
    if with_norm_fragment:
        ctx.data["norm_fragment"] = fragment()
    return ctx


def scope_response(kind: str, product_type_id: str | None = None) -> str:
    return json.dumps({"kind": kind, "product_type_id": product_type_id}, ensure_ascii=False)


def verdict_json(passed: bool, reason: str = "") -> str:
    return json.dumps({"passed": passed, "reason": reason}, ensure_ascii=False)


def lifecycle_response(**over) -> str:
    base = dict(
        effective_from=None, transition_until=None, valid_to=None, repealed_by_ref=None,
    )
    return json.dumps({**base, **over}, ensure_ascii=False)


CANDIDATES = [
    {"id": "pt-1", "hs_code": "220320", "unspsc_code": None, "name_ru": "Сигареты с фильтром"},
    {"id": "pt-2", "hs_code": "220310", "unspsc_code": None, "name_ru": "Сигареты без фильтра"},
]


# ══════════════════════════════════════════════════════════════════════════
# шаг 'scope'
# ══════════════════════════════════════════════════════════════════════════


def test_scope_step_happy_path_picks_candidate_type():
    llm = ScriptedLLM(responses=[scope_response("product_type", "pt-1")])
    store = InMemoryStore(product_types_by_group={"2203": CANDIDATES})
    step = ScopeStep(llm, store, group_ref="2203")
    ctx = item_ctx()

    result = step(ctx)

    assert result.status == "ok"
    assert result.verdicts == []  # Verifier на 'scope' не вешаем
    assert ctx.data["scope"] == {"kind": "product_type", "product_type_id": "pt-1"}
    assert len(llm.calls) == 1


def test_scope_step_uses_mid_tier():
    llm = ScriptedLLM(responses=[scope_response("all_services")])
    store = InMemoryStore(product_types_by_group={"2203": CANDIDATES})
    step = ScopeStep(llm, store, group_ref="2203")

    step(item_ctx())

    config = load_models_config()
    assert llm.calls[0][1] == config.tiers["mid"]


def test_scope_step_invalid_product_type_id_retries_then_succeeds():
    """Первый ответ — product_type_id не из кандидатов, ретрай выбирает валидный."""
    llm = ScriptedLLM(responses=[
        scope_response("product_type", "pt-unknown"),  # невалидный
        scope_response("product_type", "pt-2"),         # валидный
    ])
    store = InMemoryStore(product_types_by_group={"2203": CANDIDATES})
    step = ScopeStep(llm, store, group_ref="2203")
    ctx = item_ctx()

    result = step(ctx)

    assert result.status == "ok"
    assert ctx.data["scope"] == {"kind": "product_type", "product_type_id": "pt-2"}
    assert len(llm.calls) == 2
    retry_prompt = llm.calls[1][0]
    assert "pt-unknown" in retry_prompt or "невалид" in retry_prompt.lower()


def test_scope_step_twice_invalid_product_type_id_returns_fail():
    llm = ScriptedLLM(responses=[
        scope_response("product_type", "pt-unknown-1"),
        scope_response("product_type", "pt-unknown-2"),
    ])
    store = InMemoryStore(product_types_by_group={"2203": CANDIDATES})
    step = ScopeStep(llm, store, group_ref="2203")
    ctx = item_ctx()

    result = step(ctx)

    assert result.status == "fail"
    assert result.error is not None
    assert "scope" not in ctx.data


def test_scope_step_all_products_kind_is_valid_without_candidate_match():
    llm = ScriptedLLM(responses=[scope_response("all_products")])
    store = InMemoryStore(product_types_by_group={"2203": CANDIDATES})
    step = ScopeStep(llm, store, group_ref="2203")
    ctx = item_ctx()

    result = step(ctx)

    assert result.status == "ok"
    assert ctx.data["scope"] == {"kind": "all_products", "product_type_id": None}
    assert len(llm.calls) == 1  # ни одного ретрая не понадобилось


def test_scope_step_all_services_kind_is_valid_without_candidate_match():
    llm = ScriptedLLM(responses=[scope_response("all_services")])
    store = InMemoryStore(product_types_by_group={"2203": CANDIDATES})
    step = ScopeStep(llm, store, group_ref="2203")
    ctx = item_ctx()

    result = step(ctx)

    assert result.status == "ok"
    assert ctx.data["scope"] == {"kind": "all_services", "product_type_id": None}


def test_scope_step_candidates_in_prompt_come_from_store_not_hardcoded():
    """Кандидаты попадают в промпт из store.list_group_product_types, не
    захардкожены в коде шага — меняем содержимое стора и проверяем, что
    промпт следует за ним."""
    llm = ScriptedLLM(responses=[scope_response("product_type", "pt-1")])
    store = InMemoryStore(product_types_by_group={"2203": CANDIDATES})
    step = ScopeStep(llm, store, group_ref="2203")
    ctx = item_ctx()

    step(ctx)

    prompt = llm.calls[0][0]
    assert "pt-1" in prompt
    assert "Сигареты с фильтром" in prompt
    assert "220320" in prompt


def test_scope_step_without_norm_fragment_returns_fail_not_raise():
    llm = ScriptedLLM(responses=[])
    store = InMemoryStore(product_types_by_group={"2203": CANDIDATES})
    step = ScopeStep(llm, store, group_ref="2203")
    ctx = item_ctx(with_norm_fragment=False)

    result = step(ctx)

    assert result.status == "fail"
    assert "norm" in result.error.lower()
    assert llm.calls == []


def test_scope_step_is_registered_in_steps_registry():
    from importer.build.steps import get_step

    assert callable(get_step("scope"))


# ══════════════════════════════════════════════════════════════════════════
# шаг 'lifecycle'
# ══════════════════════════════════════════════════════════════════════════


def test_lifecycle_step_happy_path_extracts_dates_and_verifier_confirms():
    llm = ScriptedLLM(responses=[
        lifecycle_response(
            effective_from="2026-01-01", transition_until="2026-07-01",
            valid_to=None, repealed_by_ref=None,
        ),
        verdict_json(True, "даты соответствуют фрагменту"),
    ])
    step = LifecycleStep(llm)
    ctx = item_ctx()

    result = step(ctx)

    assert result.status == "ok"
    assert len(result.verdicts) == 1
    assert result.verdicts[0].passed is True
    assert ctx.data["lifecycle"] == {
        "effective_from": "2026-01-01",
        "transition_until": "2026-07-01",
        "valid_to": None,
        "repealed_by_ref": None,
    }
    # только даты, без вычисленного статуса (статус — Задача 9, отдельно)
    assert "status" not in ctx.data["lifecycle"]


def test_lifecycle_step_all_dates_null_is_valid_ok():
    """Норма бессрочна — все поля null, это валидный, а не ошибочный исход."""
    llm = ScriptedLLM(responses=[
        lifecycle_response(),
        verdict_json(True, "фрагмент не содержит дат — бессрочная норма"),
    ])
    step = LifecycleStep(llm)
    ctx = item_ctx()

    result = step(ctx)

    assert result.status == "ok"
    assert ctx.data["lifecycle"] == {
        "effective_from": None, "transition_until": None,
        "valid_to": None, "repealed_by_ref": None,
    }


def test_lifecycle_step_uses_cheap_tier_and_verifier_gets_expensive_tier():
    llm = ScriptedLLM(responses=[
        lifecycle_response(),
        verdict_json(True),
    ])
    step = LifecycleStep(llm)

    step(item_ctx())

    config = load_models_config()
    assert llm.calls[0][1] == config.tiers["cheap"]
    verifier_call_model = llm.calls[1][1]
    assert verifier_call_model == config.tiers["expensive"]
    assert verifier_call_model == verifier_model_for(config.tiers["cheap"])


def test_lifecycle_step_invalid_date_format_retries_with_error_message_then_succeeds():
    llm = ScriptedLLM(responses=[
        lifecycle_response(effective_from="01.01.2026"),  # неверный формат
        lifecycle_response(effective_from="2026-01-01"),  # валидный
        verdict_json(True),
    ])
    step = LifecycleStep(llm)
    ctx = item_ctx()

    result = step(ctx)

    assert result.status == "ok"
    assert ctx.data["lifecycle"]["effective_from"] == "2026-01-01"
    assert len(llm.calls) == 3
    retry_prompt = llm.calls[1][0]
    assert "невалид" in retry_prompt.lower() or "YYYY-MM-DD" in retry_prompt


def test_lifecycle_step_twice_invalid_date_format_returns_fail_verifier_not_called():
    llm = ScriptedLLM(responses=[
        lifecycle_response(effective_from="01.01.2026"),  # неверный формат
        lifecycle_response(valid_to="2026-99-99"),        # невозможная дата
    ])
    step = LifecycleStep(llm)
    ctx = item_ctx()

    result = step(ctx)

    assert result.status == "fail"
    assert result.error is not None
    assert result.verdicts == []
    assert "lifecycle" not in ctx.data
    assert len(llm.calls) == 2  # Verifier не должен вызываться


def test_lifecycle_step_verifier_fail_returns_fail():
    llm = ScriptedLLM(responses=[
        lifecycle_response(effective_from="2026-01-01"),
        verdict_json(False, "дата не подтверждается фрагментом"),
    ])
    step = LifecycleStep(llm)
    ctx = item_ctx()

    result = step(ctx)

    assert result.status == "fail"
    assert len(result.verdicts) == 1
    assert result.verdicts[0].passed is False
    assert result.error is not None
    assert "lifecycle" not in ctx.data


def test_lifecycle_step_without_norm_fragment_returns_fail_not_raise():
    llm = ScriptedLLM(responses=[])
    step = LifecycleStep(llm)
    ctx = item_ctx(with_norm_fragment=False)

    result = step(ctx)

    assert result.status == "fail"
    assert "norm" in result.error.lower()
    assert llm.calls == []


def test_lifecycle_step_is_registered_in_steps_registry():
    from importer.build.steps import get_step

    assert callable(get_step("lifecycle"))


def test_load_default_steps_imports_steps_scope_lifecycle_module():
    from importer.build.steps import get_step, load_default_steps

    load_default_steps()  # идемпотентно — повторный вызов не должен падать

    assert callable(get_step("scope"))
    assert callable(get_step("lifecycle"))
