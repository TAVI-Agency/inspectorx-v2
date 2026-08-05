"""Шаг 'cases' Build-конвейера (Задача 22, ADR-0003 «Блок 2»,
`docs/TARGET_FORMAT.md` §4 «Судебные кейсы»).

Один шаг STEP_ORDER, внутри — три фазы:

1) LegalX.search_cases(article) → ≤5 кейсов;
2) Verifier (профиль 'cases', один вызов на пачку): кейсы реально по этой статье;
3) Summarizer (cheap): для каждого кейса однострочное саммари (суть · исход · сумма).

Только УЗ: jurisdiction != 'UZ' → StepResult ok, court_cases=None, ноль вызовов.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from importer.build.agents import load_models_config, verifier_model_for
from importer.build.legalx import CourtCase
from importer.build.steps import ItemContext, ItemRecord
from importer.build.steps_cases import CasesStep


# ── тестовые дублёры (тот же паттерн, что test_steps_norm.py) ──────────────


@dataclass
class FakeLegalX:
    """Мок LegalXClient: на i-й вызов search_cases отдаёт responses[i]."""

    responses: list[list[CourtCase]]
    calls: list[tuple[str, str | None]] = field(default_factory=list)

    def search_norms(self, query, jurisdiction, domains=None, limit=10):
        raise NotImplementedError("шаг 'cases' не должен вызывать search_norms")

    def search_cases(self, article, topic=None, limit=5):
        self.calls.append((article, topic))
        idx = min(len(self.calls) - 1, len(self.responses) - 1)
        return self.responses[idx][:limit]


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


def court_case(**over) -> CourtCase:
    base = dict(
        case_url="https://sudx.uz/cases/test-1",
        case_title="Дело №1 — тест против БЮЛ",
        summary="Нарушение требования. Суд наложил штраф.",
        outcome="Штраф наложен",
        amount=Decimal("5000000"),
    )
    return CourtCase(**{**base, **over})


def item_ctx(*, sanctions: list[dict] | None = None, jurisdiction: str = "UZ") -> ItemContext:
    item = ItemRecord(
        id="item-1", run_id="run-1",
        expected_item="требование о маркировке", category_slug="marking",
    )
    ctx = ItemContext(item=item)
    if sanctions is not None:
        ctx.data["sanctions"] = sanctions
    else:
        ctx.data["sanctions"] = [{"article": "ст. 204 КоАО", "fine": {"amount": 50, "unit": "БРВ"}}]
    ctx.data["jurisdiction"] = jurisdiction
    return ctx


def verdict_json(passed: bool, reason: str = "") -> str:
    return json.dumps({"passed": passed, "reason": reason}, ensure_ascii=False)


def summary_line(text: str) -> str:
    """Саммаризатор возвращает просто строку."""
    return text


# ── юрисдикция != UZ -> пропуск ────────────────────────────────────────────


def test_cases_step_kz_jurisdiction_returns_ok_with_none_and_no_calls():
    """Пин-тест: для KZ шаг пропускается без ошибки, без вызовов LLM/LegalX."""
    legalx = FakeLegalX(responses=[])  # не должен быть вызван
    llm = ScriptedLLM([])  # не должен быть вызван
    step = CasesStep(legalx, llm, jurisdiction="KZ")
    ctx = item_ctx(jurisdiction="KZ")

    result = step(ctx)

    assert result.status == "ok"
    assert ctx.data.get("court_cases") is None
    assert legalx.calls == []
    assert llm.calls == []


# ── happy-path: 2 кейса -> verifier pass -> 2 саммари ──────────────────────


def test_cases_step_happy_path_returns_structured_cases_with_summaries():
    case1 = court_case(
        case_url="https://sudx.uz/cases/koao-204-2025-1",
        case_title="Дело №1",
        summary="Кейс 1 текст",
        outcome="Штраф наложен",
        amount=Decimal("1000000"),
    )
    case2 = court_case(
        case_url="https://sudx.uz/cases/koao-204-2025-2",
        case_title="Дело №2",
        summary="Кейс 2 текст",
        outcome="Жалоба отклонена",
        amount=Decimal("2000000"),
    )
    legalx = FakeLegalX(responses=[[case1, case2]])
    llm = ScriptedLLM([
        verdict_json(True, "кейсы реально по ст. 204"),
        summary_line("Суть · штраф 1000000 · отклонено"),
        summary_line("Суть · штраф 2000000 · отклонено"),
    ])
    step = CasesStep(legalx, llm)
    ctx = item_ctx(sanctions=[{"article": "ст. 204 КоАО", "fine": {"amount": 50, "unit": "БРВ"}}])

    result = step(ctx)

    assert result.status == "ok"
    assert len(ctx.data["court_cases"]) == 2
    assert ctx.data["court_cases"][0]["case_url"] == "https://sudx.uz/cases/koao-204-2025-1"
    assert ctx.data["court_cases"][0]["summary_line"] == "Суть · штраф 1000000 · отклонено"
    assert ctx.data["court_cases"][1]["case_url"] == "https://sudx.uz/cases/koao-204-2025-2"
    assert ctx.data["court_cases"][1]["summary_line"] == "Суть · штраф 2000000 · отклонено"
    assert len(result.verdicts) == 1
    assert result.verdicts[0].passed is True


def test_cases_step_article_taken_from_first_sanction():
    """Статья для поиска берётся из sanctions[0]['article']."""
    case1 = court_case()
    legalx = FakeLegalX(responses=[[case1]])
    llm = ScriptedLLM([
        verdict_json(True),
        summary_line("Резюме"),
    ])
    step = CasesStep(legalx, llm)
    ctx = item_ctx(sanctions=[
        {"article": "ст. 204 КоАО", "fine": {"amount": 50, "unit": "БРВ"}},
        {"article": "ст. 205 КоАО", "fine": {"amount": 100, "unit": "БРВ"}},
    ])

    step(ctx)

    # Должен быть вызван search_cases с первой статьёй
    assert legalx.calls[0][0] == "ст. 204 КоАО"


# ── санкции не найдены -> ok + None ────────────────────────────────────────


def test_cases_step_sanctions_not_found_returns_ok_with_none():
    """Если sanctions_not_found=True, кейсы не ищем."""
    legalx = FakeLegalX(responses=[])  # не должен быть вызван
    llm = ScriptedLLM([])  # не должен быть вызван
    step = CasesStep(legalx, llm)
    ctx = item_ctx()
    ctx.data["sanctions"] = []
    ctx.data["sanctions_not_found"] = True

    result = step(ctx)

    assert result.status == "ok"
    assert ctx.data.get("court_cases") is None
    assert legalx.calls == []
    assert llm.calls == []


def test_cases_step_empty_sanctions_returns_ok_with_none():
    """Если санкции пусты (но флага sanctions_not_found нет), кейсы не ищем."""
    legalx = FakeLegalX(responses=[])
    llm = ScriptedLLM([])
    step = CasesStep(legalx, llm)
    ctx = item_ctx(sanctions=[])

    result = step(ctx)

    assert result.status == "ok"
    assert ctx.data.get("court_cases") is None
    assert legalx.calls == []
    assert llm.calls == []


# ── поиск кейсов вернул пусто -> ok + [] ──────────────────────────────────


def test_cases_step_empty_search_returns_ok_with_empty_list():
    """Если search_cases ничего не нашёл — это не ошибка, кейсов нет."""
    legalx = FakeLegalX(responses=[[]])
    llm = ScriptedLLM([])  # Verifier не вызывается, если кейсов нет
    step = CasesStep(legalx, llm)
    ctx = item_ctx()

    result = step(ctx)

    assert result.status == "ok"
    assert ctx.data["court_cases"] == []
    assert len(result.verdicts) == 0  # Verifier не вызывался


# ── Verifier fail -> StepResult(fail) ───────────────────────────────────────


def test_cases_step_verifier_fail_returns_fail():
    """Если Verifier не подтвердит кейсы -> fail."""
    case1 = court_case()
    legalx = FakeLegalX(responses=[[case1]])
    llm = ScriptedLLM([
        verdict_json(False, "кейсы не по этой статье"),
    ])
    step = CasesStep(legalx, llm)
    ctx = item_ctx()

    result = step(ctx)

    assert result.status == "fail"
    assert "court_cases" not in ctx.data
    assert len(result.verdicts) == 1
    assert result.verdicts[0].passed is False
    assert len(llm.calls) == 1  # Summarizer не вызывался


# ── ≤5 enforced ──────────────────────────────────────────────────────────


def test_cases_step_limits_to_5_cases():
    """search_cases вернул 6 кейсов, шаг берёт только первые 5."""
    cases = [court_case(case_url=f"https://sudx.uz/cases/test-{i}") for i in range(1, 7)]
    legalx = FakeLegalX(responses=[cases])
    llm = ScriptedLLM([
        verdict_json(True),
        *[summary_line(f"Резюме {i}") for i in range(5)],
    ])
    step = CasesStep(legalx, llm)
    ctx = item_ctx()

    result = step(ctx)

    assert result.status == "ok"
    assert len(ctx.data["court_cases"]) == 5


# ── регистрация в реестре steps.py ───────────────────────────────────────


def test_cases_step_is_registered_in_steps_registry():
    from importer.build.steps import get_step

    assert callable(get_step("cases"))


def test_load_default_steps_imports_steps_cases_module():
    from importer.build.steps import get_step, load_default_steps

    load_default_steps()

    assert callable(get_step("cases"))
