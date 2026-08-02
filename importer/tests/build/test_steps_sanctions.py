"""Шаг 'sanctions' (Задача 21): Retriever + Verifier + структуризатор —
три фазы одного шага (task-21-brief.md, уточнения контроллера).

Сценарии из брифа/уточнений контроллера:
- happy-path: запрос строится из ctx.data['summary'] в форме «ответственность
  за нарушение …» -> LegalX находит фрагмент -> Verifier подтверждает, что
  фрагмент реально об ответственности -> структуризатор (Classifier, cheap)
  превращает текст фрагмента в JSON-массив
  `[{article, fine: {amount, unit}, measure}]` -> StepResult(ok);
- запрос строится из ctx.data['norm_fragment'], когда summary ещё нет
  (партиальный прогон);
- unit — поле из ответа структуризатора, НЕ хардкод: второй кейс с
  unit='МРП' проверяет, что значение взято из LLM, а не подставлено кодом;
- Retriever — тир 'mid', структуризатор — тир 'cheap' (Блок 2);
- not_found -> StepResult(ok) с ПУСТЫМИ sanctions и флагом
  ctx.data['sanctions_not_found']=True — санкция может быть не установлена,
  это валидный исход TARGET_FORMAT §4 уровня 0 («санкция не установлена»),
  НЕ fail;
- no_norm -> тоже ok+пусто (для санкций различие с not_found не критично,
  уточнение контроллера);
- Verifier fail (фрагмент нашёлся, но не об ответственности по этому
  требованию) -> StepResult(fail) — обычный retry Orchestrator'а, структуризатор
  вообще не вызывается;
- невалидный вывод структуризатора (не JSON / не массив / пустой массив) ->
  один ретрай с указанием ошибки -> валидный вывод -> успех;
- дважды невалидный вывод структуризатора -> StepResult(fail), вердикт
  Verifier'а (уже полученный до структуризации) сохраняется в результате;
- исключения (мусорный ответ LLM у Retriever/Verifier) -> StepResult(fail),
  а не необработанное исключение — шаг сам ловит AgentLLMError/ValueError
  (см. steps_norm.py/steps_rule.py — тот же паттерн; страховка
  Orchestrator._call_step, Задача 20, тут не участвует, шаг ловит сам).

LLM/LegalX — только инжектируемые скрипты ответов (тот же паттерн, что и
test_steps_norm.py/test_steps_rule.py: ScriptedLLM/FakeLegalX, никакой сети).
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date

from importer.build.agents import load_models_config, verifier_model_for
from importer.build.legalx import NormFragment
from importer.build.steps import ItemContext, ItemRecord
from importer.build.steps_sanctions import SanctionsStep

# ── тестовые дублёры (тот же паттерн, что test_steps_norm.py) ──────────────


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
        raise NotImplementedError("шаг 'sanctions' не должен вызывать search_cases")


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
        fragment_id="frag-1", act_id="act-1", act_title="КоАО РУз",
        article_ref="ст. 204", anchor="#a204",
        content="нарушение правил маркировки табачных изделий влечёт штраф",
        act_status="active", valid_from=date(2020, 1, 1), valid_to=None, score=1.0,
    )
    return NormFragment(**{**base, **over})


def item_ctx(*, summary: str | None = "нужна акцизная марка на пачке", with_norm_fragment: bool = False) -> ItemContext:
    item = ItemRecord(
        id="item-1", run_id="run-1",
        expected_item="акцизная марка на пачке сигарет", category_slug="marking",
    )
    ctx = ItemContext(item=item)
    if summary is not None:
        ctx.data["summary"] = summary
    if with_norm_fragment:
        ctx.data["norm_fragment"] = fragment(content="текст нормы про акцизную марку")
    return ctx


def verdict_json(passed: bool, reason: str = "") -> str:
    return json.dumps({"passed": passed, "reason": reason}, ensure_ascii=False)


def reformulate(text: str) -> str:
    return json.dumps({"reformulated_query": text}, ensure_ascii=False)


def no_norm_signal() -> str:
    return json.dumps({"no_norm": True})


def sanctions_response(*sanctions: dict) -> str:
    return json.dumps({"sanctions": list(sanctions)}, ensure_ascii=False)


# ── happy-path ───────────────────────────────────────────────────────────


def test_sanctions_step_happy_path_returns_structured_sanctions_with_unit_brv():
    legalx = FakeLegalX(responses=[[fragment()]])
    llm = ScriptedLLM([
        verdict_json(True, "фрагмент об ответственности за это требование"),
        sanctions_response(
            {"article": "ст. 204 КоАО", "fine": {"amount": 50, "unit": "БРВ"}, "measure": "конфискация"}
        ),
    ])
    step = SanctionsStep(legalx, llm)
    ctx = item_ctx()

    result = step(ctx)

    assert result.status == "ok"
    assert ctx.data["sanctions"] == [
        {"article": "ст. 204 КоАО", "fine": {"amount": 50, "unit": "БРВ"}, "measure": "конфискация"}
    ]
    assert len(result.verdicts) == 1
    assert result.verdicts[0].passed is True
    assert "sanctions_not_found" not in ctx.data


def test_sanctions_step_unit_taken_from_structurer_output_not_hardcoded():
    """Второй кейс с ДРУГОЙ единицей (МРП вместо БРВ) — регрессия захардкоженного
    'БРВ' в коде шага не прошла бы этот тест."""
    legalx = FakeLegalX(responses=[[fragment()]])
    llm = ScriptedLLM([
        verdict_json(True),
        sanctions_response(
            {"article": "ст. 205 КоАП РК", "fine": {"amount": 20, "unit": "МРП"}, "measure": None}
        ),
    ])
    step = SanctionsStep(legalx, llm)
    ctx = item_ctx()

    result = step(ctx)

    assert result.status == "ok"
    assert ctx.data["sanctions"][0]["fine"]["unit"] == "МРП"
    assert ctx.data["sanctions"][0]["fine"]["amount"] == 20
    assert ctx.data["sanctions"][0]["measure"] is None


def test_sanctions_step_query_built_from_summary_in_expected_form():
    legalx = FakeLegalX(responses=[[fragment()]])
    llm = ScriptedLLM([
        verdict_json(True),
        sanctions_response({"article": "ст. 204", "fine": {"amount": 1, "unit": "БРВ"}, "measure": None}),
    ])
    step = SanctionsStep(legalx, llm)
    ctx = item_ctx(summary="нужна акцизная марка на пачке")

    step(ctx)

    query = legalx.calls[0][0]
    assert "ответственность за нарушение" in query
    assert "нужна акцизная марка на пачке" in query


def test_sanctions_step_query_built_from_norm_fragment_when_no_summary():
    legalx = FakeLegalX(responses=[[fragment()]])
    llm = ScriptedLLM([
        verdict_json(True),
        sanctions_response({"article": "ст. 204", "fine": {"amount": 1, "unit": "БРВ"}, "measure": None}),
    ])
    step = SanctionsStep(legalx, llm)
    ctx = item_ctx(summary=None, with_norm_fragment=True)

    step(ctx)

    query = legalx.calls[0][0]
    assert "ответственность за нарушение" in query
    assert "текст нормы про акцизную марку" in query


def test_sanctions_step_uses_mid_tier_retriever_and_structurer_gets_cheap_tier():
    legalx = FakeLegalX(responses=[[fragment()]])
    llm = ScriptedLLM([
        verdict_json(True),
        sanctions_response({"article": "ст. 204", "fine": {"amount": 1, "unit": "БРВ"}, "measure": None}),
    ])
    step = SanctionsStep(legalx, llm)

    step(item_ctx())

    config = load_models_config()
    # найден сразу (без переформулировки) -> 1-й вызов LLM — Verifier
    verifier_call_model = llm.calls[0][1]
    assert verifier_call_model == verifier_model_for(config.tiers["mid"])
    structurer_call_model = llm.calls[1][1]
    assert structurer_call_model == config.tiers["cheap"]


# ── not_found / no_norm -> ok + пусто + флаг ────────────────────────────


def test_sanctions_step_not_found_returns_ok_with_empty_sanctions_and_flag():
    legalx = FakeLegalX(responses=[[]])  # всегда пусто
    llm = ScriptedLLM([
        reformulate("переформулировка 1"),
        reformulate("переформулировка 2"),
    ])
    step = SanctionsStep(legalx, llm)
    ctx = item_ctx()

    result = step(ctx)

    assert result.status == "ok"
    assert ctx.data["sanctions"] == []
    assert ctx.data["sanctions_not_found"] is True
    assert result.verdicts == []  # до Verifier не дошли — фрагмента не было


def test_sanctions_step_no_norm_returns_ok_with_empty_sanctions_too():
    legalx = FakeLegalX(responses=[[]])
    llm = ScriptedLLM([no_norm_signal()])
    step = SanctionsStep(legalx, llm)
    ctx = item_ctx()

    result = step(ctx)

    assert result.status == "ok"
    assert ctx.data["sanctions"] == []
    assert result.verdicts == []


# ── Verifier fail -> StepResult(fail), структуризатор не вызывается ────


def test_sanctions_step_verifier_fail_returns_fail_and_skips_structurer():
    legalx = FakeLegalX(responses=[[fragment()]])
    llm = ScriptedLLM([
        verdict_json(False, "фрагмент не об этом требовании"),
    ])
    step = SanctionsStep(legalx, llm)
    ctx = item_ctx()

    result = step(ctx)

    assert result.status == "fail"
    assert len(result.verdicts) == 1
    assert result.verdicts[0].passed is False
    assert "sanctions" not in ctx.data
    assert len(llm.calls) == 1  # структуризатор ни разу не позван


# ── невалидный вывод структуризатора -> ретрай -> успех ─────────────────


def test_sanctions_step_invalid_structurer_output_retries_then_succeeds():
    legalx = FakeLegalX(responses=[[fragment()]])
    llm = ScriptedLLM([
        verdict_json(True),
        "это вообще не JSON",
        sanctions_response({"article": "ст. 204", "fine": {"amount": 30, "unit": "БРВ"}, "measure": None}),
    ])
    step = SanctionsStep(legalx, llm)
    ctx = item_ctx()

    result = step(ctx)

    assert result.status == "ok"
    assert ctx.data["sanctions"] == [
        {"article": "ст. 204", "fine": {"amount": 30, "unit": "БРВ"}, "measure": None}
    ]
    assert len(llm.calls) == 3
    retry_prompt = llm.calls[2][0]
    assert "невалид" in retry_prompt.lower()


def test_sanctions_step_empty_structurer_array_is_invalid_and_retries():
    legalx = FakeLegalX(responses=[[fragment()]])
    llm = ScriptedLLM([
        verdict_json(True),
        json.dumps({"sanctions": []}),
        sanctions_response({"article": "ст. 204", "fine": {"amount": 30, "unit": "БРВ"}, "measure": None}),
    ])
    step = SanctionsStep(legalx, llm)
    ctx = item_ctx()

    result = step(ctx)

    assert result.status == "ok"
    assert ctx.data["sanctions"] == [
        {"article": "ст. 204", "fine": {"amount": 30, "unit": "БРВ"}, "measure": None}
    ]


# ── дважды невалидный вывод структуризатора -> fail ─────────────────────


def test_sanctions_step_twice_invalid_structurer_output_returns_fail():
    legalx = FakeLegalX(responses=[[fragment()]])
    llm = ScriptedLLM([
        verdict_json(True, "фрагмент об ответственности"),
        "мусор",
        "снова не JSON",
    ])
    step = SanctionsStep(legalx, llm)
    ctx = item_ctx()

    result = step(ctx)

    assert result.status == "fail"
    assert result.error is not None
    assert "sanctions" not in ctx.data
    # вердикт Verifier'а (уже полученный до структуризации) не теряется
    assert len(result.verdicts) == 1
    assert result.verdicts[0].passed is True


# ── исключения -> fail, не raise ─────────────────────────────────────────


def test_sanctions_step_verifier_garbage_answer_returns_fail_not_raise():
    legalx = FakeLegalX(responses=[[fragment()]])
    llm = ScriptedLLM(["это не JSON и не пройдёт парсинг Verifier'ом"])
    step = SanctionsStep(legalx, llm)

    result = step(item_ctx())

    assert result.status == "fail"
    assert result.error is not None


def test_sanctions_step_retriever_reformulation_garbage_returns_fail_not_raise():
    legalx = FakeLegalX(responses=[[]])
    llm = ScriptedLLM(["мусорный ответ, не JSON и не reformulated_query"])
    step = SanctionsStep(legalx, llm)

    result = step(item_ctx())

    assert result.status == "fail"
    assert result.error is not None


# ── регистрация в реестре steps.py ───────────────────────────────────────


def test_sanctions_step_is_registered_in_steps_registry():
    from importer.build.steps import get_step

    assert callable(get_step("sanctions"))


def test_load_default_steps_imports_steps_sanctions_module():
    from importer.build.steps import get_step, load_default_steps

    load_default_steps()  # идемпотентно — повторный вызов не должен падать

    assert callable(get_step("sanctions"))
