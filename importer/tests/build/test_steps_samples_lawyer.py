"""Шаги 'samples' и 'lawyer' (Задача 23): Samples judge + Template hunter +
Verifier (три фазы одного шага 'samples'), и In-house lawyer (шаг 'lawyer',
без Verifier) — task-23-brief.md, уточнения контроллера.

Сценарии из брифа/уточнений контроллера:

## 'samples'

- Samples judge (Classifier, mid) решает needed/document_type по контексту
  требования (summary/norm_fragment/expected_item, тот же приём, что и
  `steps_sanctions.py:_context_text`);
- `needed=False` -> StepResult(ok), ctx.data['templates']=None, Hunter вообще
  не вызывается (шаблоны для этого требования не нужны — это НЕ то же самое,
  что «нужны, но не нашли»);
- `needed=True` + пустой веб-поиск -> StepResult(ok), ctx.data['templates']=[]
  + ctx.data['templates_not_found']=True (сигнал менеджеру — витрина покажет
  «Данных пока нет»), Hunter/Verifier LLM не вызываются на пустом поиске;
- Hunter (Classifier, mid) не нашёл среди находок подходящего шаблона
  (`found=False`) -> та же ветка not_found+флаг, Verifier не вызывается;
- Hunter нашёл -> Verifier (профиль 'samples', verifier_model_for(mid) ==
  'expensive') проверяет качество/источник шаблона -> passed ->
  ctx.data['templates'] = [{"name", "source_url", "note"}], StepResult(ok);
- Verifier отклонил -> StepResult(fail);
- запрос веб-поиска строится из document_type, который вернул judge;
- исключения (мусорный ответ LLM) -> StepResult(fail), не raise.

## 'lawyer'

- Вход — вся накопленная карточка айтема (`summary`/`sanctions`/`lifecycle`/
  `rules` из ctx.data, с безопасными дефолтами при частичном rerun_item);
- happy-path без близкой даты ЖЦ -> ctx.data['lawyer_instruction'] =
  {"verdict", "steps"}, ctx.data['status_note'] is None, verdicts пуст (на
  'lawyer' Verifier не вешаем — в CSV мастер-плана у него нет отдельной
  Verifier-строки);
- в ctx.data['lifecycle'] есть БЛИЖАЙШАЯ будущая дата (effective_from ИЛИ
  valid_to позже "сегодня") -> ctx.data['status_note'] заполняется ответом
  LLM (непустая строка обязательна — иначе невалидный ответ);
- lifecycle без будущих дат (пуст/все даты в прошлом/отсутствует вовсе) ->
  ctx.data['status_note'] is None, а НЕПУСТОЙ status_note от LLM в этом
  случае — невалидный ответ (расхождение с фактическими датами);
- невалидный ответ (не тот контракт, либо status_note не соответствует
  наличию/отсутствию близкой даты) -> один ретрай с указанием ошибки -> всё
  ещё невалиден -> StepResult(fail);
- модель — тир 'expensive' (CSV мастер-плана: «дорогой LLM»).

LLM/веб-поиск — только инжектируемые скрипты ответов (тот же паттерн, что и
test_steps_sanctions.py/test_steps_scope_lifecycle.py: ScriptedLLM/
FakeWebSearcher, никакой сети).
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date

import pytest

from importer.build.agents import load_models_config, verifier_model_for
from importer.build.legalx import NormFragment
from importer.build.steps import ItemContext, ItemRecord
from importer.build.steps_samples_lawyer import LawyerStep, SamplesStep
from importer.build.websearch import WebSearcher, get_web_searcher

# ── тестовые дублёры (тот же паттерн, что test_steps_sanctions.py) ─────────


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


@dataclass
class FakeWebSearcher:
    """Мок WebSearcher: на i-й вызов search отдаёт responses[i] (последний
    элемент повторяется, если вызовов больше, чем ответов)."""

    responses: list[list[dict]]
    calls: list[str] = field(default_factory=list)

    def search(self, query: str) -> list[dict]:
        self.calls.append(query)
        idx = min(len(self.calls) - 1, len(self.responses) - 1)
        return self.responses[idx]


def item_ctx(
    *,
    summary: str | None = "нужен сертификат соответствия перед вводом в оборот",
    with_norm_fragment: bool = False,
    sanctions: list[dict] | None = None,
    lifecycle: dict | None = None,
    rules: list[dict] | None = None,
) -> ItemContext:
    item = ItemRecord(
        id="item-1", run_id="run-1",
        expected_item="сертификат соответствия на партию сигарет", category_slug="marking",
    )
    ctx = ItemContext(item=item)
    if summary is not None:
        ctx.data["summary"] = summary
    if with_norm_fragment:
        ctx.data["norm_fragment"] = NormFragment(
            fragment_id="frag-1", act_id="act-1", act_title="ПКМ-43",
            article_ref="прил. 4", anchor="#a4",
            content="сертификация партии сигарет обязательна перед вводом в оборот",
            act_status="active", valid_from=date(2020, 1, 1), valid_to=None, score=1.0,
        )
    if sanctions is not None:
        ctx.data["sanctions"] = sanctions
    if lifecycle is not None:
        ctx.data["lifecycle"] = lifecycle
    if rules is not None:
        ctx.data["rules"] = rules
    return ctx


def judge_response(needed: bool, document_type: str | None = None) -> str:
    return json.dumps({"needed": needed, "document_type": document_type}, ensure_ascii=False)


def hunt_response(found: bool, template: dict | None = None) -> str:
    return json.dumps({"found": found, "template": template}, ensure_ascii=False)


def verdict_json(passed: bool, reason: str = "") -> str:
    return json.dumps({"passed": passed, "reason": reason}, ensure_ascii=False)


def lawyer_response(verdict: str, steps: list[str], status_note: str | None = None) -> str:
    return json.dumps(
        {"verdict": verdict, "steps": steps, "status_note": status_note}, ensure_ascii=False
    )


TEMPLATE = {
    "name": "Заявление на сертификат соответствия (форма №3)",
    "source_url": "https://cert.uz/forms/3",
    "note": "официальная форма органа сертификации",
}


# ══════════════════════════════════════════════════════════════════════════
# шаг 'samples'
# ══════════════════════════════════════════════════════════════════════════


def test_samples_step_not_needed_returns_ok_with_none_templates():
    llm = ScriptedLLM([judge_response(False, None)])
    searcher = FakeWebSearcher(responses=[[]])
    step = SamplesStep(searcher, llm)
    ctx = item_ctx()

    result = step(ctx)

    assert result.status == "ok"
    assert ctx.data["templates"] is None
    assert "templates_not_found" not in ctx.data
    assert searcher.calls == []  # Hunter вообще не вызывается
    assert len(llm.calls) == 1  # только судья


def test_samples_step_needed_found_and_verified_returns_ok_with_template():
    llm = ScriptedLLM([
        judge_response(True, "заявление на сертификат соответствия"),
        hunt_response(True, TEMPLATE),
        verdict_json(True, "официальный источник, форма актуальна"),
    ])
    searcher = FakeWebSearcher(responses=[[
        {"title": "Форма №3 — cert.uz", "url": "https://cert.uz/forms/3", "snippet": "..."}
    ]])
    step = SamplesStep(searcher, llm)
    ctx = item_ctx()

    result = step(ctx)

    assert result.status == "ok"
    assert ctx.data["templates"] == [TEMPLATE]
    assert "templates_not_found" not in ctx.data
    assert len(result.verdicts) == 1
    assert result.verdicts[0].passed is True


def test_samples_step_empty_search_result_returns_ok_empty_with_flag_and_skips_llm():
    llm = ScriptedLLM([judge_response(True, "форма заявления")])
    searcher = FakeWebSearcher(responses=[[]])
    step = SamplesStep(searcher, llm)
    ctx = item_ctx()

    result = step(ctx)

    assert result.status == "ok"
    assert ctx.data["templates"] == []
    assert ctx.data["templates_not_found"] is True
    assert len(llm.calls) == 1  # Hunter/Verifier ни разу не позваны
    assert result.verdicts == []


def test_samples_step_hunter_found_false_returns_ok_empty_with_flag():
    llm = ScriptedLLM([
        judge_response(True, "форма заявления"),
        hunt_response(False, None),
    ])
    searcher = FakeWebSearcher(responses=[[
        {"title": "что-то не по теме", "url": "https://example.com", "snippet": "..."}
    ]])
    step = SamplesStep(searcher, llm)
    ctx = item_ctx()

    result = step(ctx)

    assert result.status == "ok"
    assert ctx.data["templates"] == []
    assert ctx.data["templates_not_found"] is True
    assert len(llm.calls) == 2  # Verifier не вызывается
    assert result.verdicts == []


def test_samples_step_verifier_fail_returns_fail():
    llm = ScriptedLLM([
        judge_response(True, "форма заявления"),
        hunt_response(True, TEMPLATE),
        verdict_json(False, "источник неофициальный, дата не указана"),
    ])
    searcher = FakeWebSearcher(responses=[[
        {"title": "Форма №3", "url": "https://random-blog.example/form", "snippet": "..."}
    ]])
    step = SamplesStep(searcher, llm)
    ctx = item_ctx()

    result = step(ctx)

    assert result.status == "fail"
    assert len(result.verdicts) == 1
    assert result.verdicts[0].passed is False
    assert "templates" not in ctx.data


def test_samples_step_search_query_built_from_document_type():
    llm = ScriptedLLM([judge_response(True, "заявление на сертификат соответствия")])
    searcher = FakeWebSearcher(responses=[[]])
    step = SamplesStep(searcher, llm)

    step(item_ctx())

    assert len(searcher.calls) == 1
    assert "заявление на сертификат соответствия" in searcher.calls[0]


def test_samples_step_judge_and_hunter_use_mid_tier_verifier_gets_expensive():
    llm = ScriptedLLM([
        judge_response(True, "форма"),
        hunt_response(True, TEMPLATE),
        verdict_json(True),
    ])
    searcher = FakeWebSearcher(responses=[[
        {"title": "Форма", "url": "https://cert.uz/f", "snippet": "..."}
    ]])
    step = SamplesStep(searcher, llm)

    step(item_ctx())

    config = load_models_config()
    assert llm.calls[0][1] == config.tiers["mid"]  # судья
    assert llm.calls[1][1] == config.tiers["mid"]  # hunter
    assert llm.calls[2][1] == verifier_model_for(config.tiers["mid"])  # verifier


def test_samples_step_judge_garbage_answer_returns_fail_not_raise():
    llm = ScriptedLLM(["это не JSON и не пройдёт парсинг"])
    searcher = FakeWebSearcher(responses=[[]])
    step = SamplesStep(searcher, llm)

    result = step(item_ctx())

    assert result.status == "fail"
    assert result.error is not None


def test_samples_step_judge_missing_needed_field_returns_fail_not_raise():
    llm = ScriptedLLM([json.dumps({"document_type": "форма"})])
    searcher = FakeWebSearcher(responses=[[]])
    step = SamplesStep(searcher, llm)

    result = step(item_ctx())

    assert result.status == "fail"
    assert result.error is not None


def test_samples_step_is_registered_in_steps_registry():
    from importer.build.steps import get_step

    assert callable(get_step("samples"))


def test_load_default_steps_imports_steps_samples_lawyer_module_for_samples():
    from importer.build.steps import get_step, load_default_steps

    load_default_steps()  # идемпотентно

    assert callable(get_step("samples"))


# ══════════════════════════════════════════════════════════════════════════
# websearch.get_web_searcher() — паттерн get_client/live (legalx.py)
# ══════════════════════════════════════════════════════════════════════════


def test_get_web_searcher_default_live_backend_raises_only_on_call(monkeypatch):
    monkeypatch.delenv("WEBSEARCH_BACKEND", raising=False)
    searcher = get_web_searcher()  # не падает на конструирование
    assert isinstance(searcher, WebSearcher)
    with pytest.raises(NotImplementedError):
        searcher.search("что угодно")


def test_get_web_searcher_unknown_backend_raises_value_error(monkeypatch):
    monkeypatch.setenv("WEBSEARCH_BACKEND", "totally-unknown")
    with pytest.raises(ValueError):
        get_web_searcher()


# ══════════════════════════════════════════════════════════════════════════
# шаг 'lawyer'
# ══════════════════════════════════════════════════════════════════════════


def test_lawyer_step_happy_path_without_lifecycle_sets_instruction_and_none_status_note():
    llm = ScriptedLLM([
        lawyer_response("требование обязательно к имплементации", ["получить сертификат", "промаркировать партию"], None),
    ])
    step = LawyerStep(llm)
    ctx = item_ctx(sanctions=[{"article": "ст. 204", "fine": {"amount": 50, "unit": "БРВ"}, "measure": None}])

    result = step(ctx)

    assert result.status == "ok"
    assert ctx.data["lawyer_instruction"] == {
        "verdict": "требование обязательно к имплементации",
        "steps": ["получить сертификат", "промаркировать партию"],
    }
    assert ctx.data["status_note"] is None
    assert result.verdicts == []  # Verifier на 'lawyer' не вешаем


def test_lawyer_step_close_future_date_sets_status_note():
    llm = ScriptedLLM([
        lawyer_response(
            "требование скоро изменится", ["подготовить документы"],
            "успеть промаркировать остатки до 2026-09-01",
        ),
    ])
    step = LawyerStep(llm, today=date(2026, 8, 2))
    ctx = item_ctx(lifecycle={
        "effective_from": "2026-09-01", "transition_until": None,
        "valid_to": None, "repealed_by_ref": None,
    })

    result = step(ctx)

    assert result.status == "ok"
    assert ctx.data["status_note"] == "успеть промаркировать остатки до 2026-09-01"


def test_lawyer_step_lifecycle_without_future_dates_returns_none_status_note():
    llm = ScriptedLLM([
        lawyer_response("действует без изменений", ["ничего дополнительно делать не нужно"], None),
    ])
    step = LawyerStep(llm, today=date(2026, 8, 2))
    ctx = item_ctx(lifecycle={
        "effective_from": "2020-01-01",  # уже в прошлом
        "transition_until": None, "valid_to": None, "repealed_by_ref": None,
    })

    result = step(ctx)

    assert result.status == "ok"
    assert ctx.data["status_note"] is None


def test_lawyer_step_close_date_but_llm_returns_null_status_note_is_invalid_retries_then_succeeds():
    """LLM сначала не заметила близкую дату (status_note=null) — это
    невалидно (расходится с фактическими датами) -> ретрай -> валидный ответ."""
    llm = ScriptedLLM([
        lawyer_response("требование скоро изменится", ["подготовить документы"], None),
        lawyer_response(
            "требование скоро изменится", ["подготовить документы"],
            "успеть до 2026-09-01",
        ),
    ])
    step = LawyerStep(llm, today=date(2026, 8, 2))
    ctx = item_ctx(lifecycle={
        "effective_from": "2026-09-01", "transition_until": None,
        "valid_to": None, "repealed_by_ref": None,
    })

    result = step(ctx)

    assert result.status == "ok"
    assert ctx.data["status_note"] == "успеть до 2026-09-01"
    assert len(llm.calls) == 2


def test_lawyer_step_invalid_response_retries_then_fails_twice():
    llm = ScriptedLLM(["мусор, не JSON", "снова не JSON"])
    step = LawyerStep(llm)
    ctx = item_ctx()

    result = step(ctx)

    assert result.status == "fail"
    assert result.error is not None
    assert "lawyer_instruction" not in ctx.data
    assert "status_note" not in ctx.data
    assert len(llm.calls) == 2


def test_lawyer_step_missing_steps_field_is_invalid_retries_then_succeeds():
    llm = ScriptedLLM([
        json.dumps({"verdict": "нужно", "status_note": None}),  # нет steps
        lawyer_response("нужно", ["шаг 1"], None),
    ])
    step = LawyerStep(llm)
    ctx = item_ctx()

    result = step(ctx)

    assert result.status == "ok"
    assert ctx.data["lawyer_instruction"]["steps"] == ["шаг 1"]
    assert len(llm.calls) == 2


def test_lawyer_step_uses_expensive_tier():
    llm = ScriptedLLM([lawyer_response("нужно", ["шаг 1"], None)])
    step = LawyerStep(llm)

    step(item_ctx())

    config = load_models_config()
    assert llm.calls[0][1] == config.tiers["expensive"]


def test_lawyer_step_prompt_includes_accumulated_card_data():
    llm = ScriptedLLM([lawyer_response("нужно", ["шаг 1"], None)])
    step = LawyerStep(llm)
    ctx = item_ctx(
        summary="нужна маркировка акцизной маркой",
        sanctions=[{"article": "ст. 204", "fine": {"amount": 50, "unit": "БРВ"}, "measure": None}],
    )

    step(ctx)

    prompt = llm.calls[0][0]
    assert "нужна маркировка акцизной маркой" in prompt
    assert "ст. 204" in prompt


def test_lawyer_step_is_registered_in_steps_registry():
    from importer.build.steps import get_step

    assert callable(get_step("lawyer"))


def test_load_default_steps_imports_steps_samples_lawyer_module_for_lawyer():
    from importer.build.steps import get_step, load_default_steps

    load_default_steps()  # идемпотентно

    assert callable(get_step("lawyer"))
