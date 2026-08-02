"""Eval golden set (Задача 28): retrieval_hit/verifier_agreement/
category_accuracy/lifecycle_date_accuracy, толерантный к формату матчинг
реквизитов, `HeuristicBaselineLLM` (заглушка ТОЛЬКО для baseline.json),
`compute_delta` против прошлого прогона.

LLM в тестах — только инжектируемый `ScriptedLLM` (тот же паттерн, что и
`test_agents.py`) — сети нет, ответы полностью контролируются каждым тестом.
Единственная интеграционная проверка (генератор на живой локальной БД)
помечена `@pytest.mark.integration` и скипается, если локальный Supabase
не поднят (`supabase db start && supabase db reset --local`).
"""
from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import pytest
import yaml

from importer.build.agents import load_models_config, verifier_model_for
from importer.build.legalx import NormFragment
from importer.build.llm_client import AgentLLMError
from importer.build.eval_golden import (
    AggregateMetrics,
    GoldenItem,
    GoldenOrigin,
    HeuristicBaselineLLM,
    LifecycleDates,
    SourceAct,
    _pick_decoy,
    _pick_near_miss_decoy,
    category_accuracy_for_item,
    compute_delta,
    lifecycle_date_accuracy_for_item,
    load_golden_set,
    normalize_act,
    normalize_article,
    retrieval_hit_for_item,
    run_eval,
    source_acts_match,
    verifier_agreement_for_item,
)

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))


# ── тестовые дублёры (тот же паттерн, что test_agents.py) ────────────────


@dataclass
class FakeLegalX:
    """На i-й вызов search_norms отдаёт responses[i] (последний повторяется)."""

    responses: list[list[NormFragment]]
    calls: list[tuple[str, str]] = field(default_factory=list)

    def search_norms(self, query, jurisdiction, domains=None, limit=10):
        self.calls.append((query, jurisdiction))
        idx = min(len(self.calls) - 1, len(self.responses) - 1)
        return self.responses[idx] if self.responses else []

    def search_cases(self, article, topic=None, limit=5):
        raise NotImplementedError("retrieval_hit не должен вызывать search_cases")


class ScriptedLLM:
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
        fragment_id="frag-1", act_id="act-1", act_title="ПКМ-290, ТР",
        article_ref="п. 24", anchor="#p24", content="текст фрагмента",
        act_status="active", valid_from=None, valid_to=None, score=1.0,
    )
    return NormFragment(**{**base, **over})


def item(
    golden_id="g1", expected_item="Пройти таможенное оформление", category_slug="customs",
    act="ПКМ-290, ТР", article="п. 24", sanction=None,
    lifecycle=(None, None, None), req_id="req-1", kind="product", code="2404110001", name="сигареты",
) -> GoldenItem:
    return GoldenItem(
        id=golden_id, expected_item=expected_item, category_slug=category_slug,
        canonical_question=f'Какая норма права устанавливает требование: «{expected_item}»?',
        source_act=SourceAct(act=act, article=article),
        lifecycle_dates=LifecycleDates(*lifecycle),
        sanction_article=sanction,
        origin=GoldenOrigin(requirement_id=req_id, kind=kind, code=code, name=name),
    )


# ══════════════════════════════════════════════════════════════════════════
# load_golden_set — YAML round-trip
# ══════════════════════════════════════════════════════════════════════════


def test_load_golden_set_round_trip(tmp_path):
    doc = {
        "status": "draft",
        "items": [{
            "id": "g01", "expected_item": "Заголовок", "category_slug": "tbt",
            "canonical_question": "Вопрос?",
            "source_act": {"act": "ПКМ-290, ТР", "article": "п. 5"},
            "lifecycle_dates": {"effective_from": None, "transition_until": None, "valid_to": "2027-01-01"},
            "sanction_article": "ст. 165 КоАО",
            "origin": {"requirement_id": "req-1", "kind": "product", "code": "2404110001", "name": "сигареты"},
        }],
    }
    path = tmp_path / "golden_set.yaml"
    path.write_text(yaml.safe_dump(doc, allow_unicode=True), encoding="utf-8")

    items = load_golden_set(path)

    assert len(items) == 1
    loaded = items[0]
    assert loaded.id == "g01"
    assert loaded.source_act == SourceAct(act="ПКМ-290, ТР", article="п. 5")
    assert loaded.lifecycle_dates == LifecycleDates(None, None, "2027-01-01")
    assert loaded.sanction_article == "ст. 165 КоАО"
    assert loaded.origin == GoldenOrigin("req-1", "product", "2404110001", "сигареты")


# ══════════════════════════════════════════════════════════════════════════
# normalize_act / normalize_article / source_acts_match — толерантность к формату
# ══════════════════════════════════════════════════════════════════════════


def test_normalize_act_strips_leading_enumeration_and_extracts_code():
    assert normalize_act("1. ПКМ-290, ТР") == "пкм290"
    assert normalize_act("ПКМ-290, Технический регламент") == "пкм290"


def test_normalize_act_prefers_decree_number_over_date_fragment():
    # "от 02.04.2022" не должен ложно распознаться как номер акта — приоритет
    # у явного "№149" (см. докстринг normalize_act).
    assert normalize_act(
        "Постановление Кабинета Министров №149 от 02.04.2022 (маркировка лекарств Asl Belgisi)"
    ) == "№149"


def test_normalize_act_extracts_hyphenated_code_even_with_trailing_date():
    assert normalize_act(
        'Закон ЗРУ-701 от 14.07.2021 «О лицензировании, разрешительных и уведомительных процедурах»'
    ) == "зру701"


def test_normalize_act_no_code_falls_back_to_normalized_text():
    assert normalize_act("Налоговый кодекс Республики Узбекистан") == "налоговый кодекс республики узбекистан"


def test_normalize_act_none_or_empty_is_none():
    assert normalize_act(None) is None
    assert normalize_act("") is None


def test_normalize_article_strips_dedup_suffix_and_extracts_number():
    assert normalize_article("п. 35 (37b7)") == "#35"
    assert normalize_article("п. 35 (21c9)") == "#35"
    assert normalize_article("п. 33") == "#33"


def test_normalize_article_range_uses_first_number():
    assert normalize_article("п. 24-25") == "#24"


def test_normalize_article_text_descriptor_without_number_is_literal_text():
    assert normalize_article("обязательная маркировка") == "обязательная маркировка"


def test_normalize_article_none_or_empty_is_none():
    assert normalize_article(None) is None
    assert normalize_article("") is None


def test_source_acts_match_tolerant_to_format_variations():
    assert source_acts_match(
        SourceAct("1. ПКМ-290, ТР", "п. 33"),
        SourceAct("ПКМ-290, Технический регламент", "п. 33"),
    )
    assert source_acts_match(
        SourceAct("ПКМ-290, ТР", "п. 35 (37b7)"),
        SourceAct("ПКМ-290, Технический регламент", "п. 35 (37b7)"),
    )


def test_source_acts_match_false_on_different_article():
    assert not source_acts_match(
        SourceAct("ПКМ-290, ТР", "п. 24"),
        SourceAct("ПКМ-290, ТР", "п. 33"),
    )


def test_source_acts_match_false_on_different_act():
    assert not source_acts_match(
        SourceAct("ПКМ-290, ТР", "п. 24"),
        SourceAct("Налоговый кодекс", "п. 24"),
    )


def test_source_acts_match_false_when_either_side_missing():
    assert not source_acts_match(SourceAct(None, None), SourceAct("ПКМ-290, ТР", "п. 24"))
    assert not source_acts_match(SourceAct("ПКМ-290, ТР", "п. 24"), SourceAct(None, None))


# ══════════════════════════════════════════════════════════════════════════
# retrieval_hit_for_item — через реальный Retriever
# ══════════════════════════════════════════════════════════════════════════


def test_retrieval_hit_found_immediately_no_llm_calls():
    golden = item(article="п. 33")
    legalx = FakeLegalX(responses=[[fragment(article_ref="п. 33")]])
    llm = ScriptedLLM([])

    result = retrieval_hit_for_item(golden, legalx, llm)

    assert result.outcome == "hit"
    assert llm.calls == []


def test_retrieval_hit_found_but_wrong_requisites_is_miss():
    golden = item(article="п. 33")
    legalx = FakeLegalX(responses=[[fragment(article_ref="п. 40")]])  # не та статья
    llm = ScriptedLLM([])

    result = retrieval_hit_for_item(golden, legalx, llm)

    assert result.outcome == "miss"


def test_retrieval_hit_hit_among_several_fragments():
    golden = item(article="п. 33")
    legalx = FakeLegalX(responses=[[fragment(article_ref="п. 40"), fragment(article_ref="п. 33")]])
    llm = ScriptedLLM([])

    result = retrieval_hit_for_item(golden, legalx, llm)

    assert result.outcome == "hit"


def test_retrieval_hit_not_found_after_reformulations_is_miss():
    golden = item()
    legalx = FakeLegalX(responses=[[], [], []])
    llm = ScriptedLLM([
        json.dumps({"reformulated_query": "переформулировка 1"}),
        json.dumps({"reformulated_query": "переформулировка 2"}),
    ])

    result = retrieval_hit_for_item(golden, legalx, llm)

    assert result.outcome == "miss"


def test_retrieval_hit_no_norm_signal_is_miss():
    golden = item()
    legalx = FakeLegalX(responses=[[]])
    llm = ScriptedLLM([json.dumps({"no_norm": True})])

    result = retrieval_hit_for_item(golden, legalx, llm)

    assert result.outcome == "miss"


def test_retrieval_hit_no_source_act_skips_legalx_and_llm():
    golden = item(act=None, article=None)
    legalx = FakeLegalX(responses=[[fragment()]])
    llm = ScriptedLLM([])

    result = retrieval_hit_for_item(golden, legalx, llm)

    assert result.outcome == "no_source_act"
    assert legalx.calls == []
    assert llm.calls == []


def test_retrieval_hit_garbage_llm_answer_is_error_not_exception():
    golden = item()
    legalx = FakeLegalX(responses=[[]])
    llm = ScriptedLLM(["это не JSON"])

    result = retrieval_hit_for_item(golden, legalx, llm)

    assert result.outcome == "error"
    assert result.error is not None


# ══════════════════════════════════════════════════════════════════════════
# verifier_agreement_for_item — через реальный Verifier
# ══════════════════════════════════════════════════════════════════════════


def test_verifier_agreement_true_when_correct_passes_gross_and_near_miss_fail():
    golden = item(golden_id="g1", article="п. 24")
    gross = item(golden_id="g2", expected_item="Другое требование", act="Налоговый кодекс", article="обязанность")
    near_miss = item(golden_id="g3", expected_item="Соседнее требование", article="п. 33")  # тот же акт, другая статья
    llm = ScriptedLLM([
        json.dumps({"passed": True, "reason": "ok"}),       # correct
        json.dumps({"passed": False, "reason": "не о том"}),  # gross decoy
        json.dumps({"passed": False, "reason": "не та статья"}),  # near-miss decoy
    ])

    result = verifier_agreement_for_item(golden, gross, near_miss, llm)

    assert result.correct_passed is True
    assert result.gross_decoy_passed is False
    assert result.near_miss_decoy_passed is False
    assert result.near_miss_decoy_item_id == "g3"


def test_verifier_agreement_near_miss_none_when_no_candidate():
    golden = item(golden_id="g1")
    gross = item(golden_id="g2", article="п. 99")
    llm = ScriptedLLM([json.dumps({"passed": True}), json.dumps({"passed": False})])

    result = verifier_agreement_for_item(golden, gross, None, llm)

    assert result.near_miss_decoy_item_id is None
    assert result.near_miss_decoy_passed is None
    assert len(llm.calls) == 2  # near-miss вызов НЕ делается, кандидата нет


def test_verifier_agreement_false_when_correct_fails():
    golden = item(golden_id="g1")
    gross = item(golden_id="g2", article="п. 99")
    llm = ScriptedLLM([
        json.dumps({"passed": False, "reason": "не подтвердил правильный"}),
        json.dumps({"passed": False, "reason": "ok"}),
    ])

    result = verifier_agreement_for_item(golden, gross, None, llm)

    assert result.correct_passed is False


def test_verifier_agreement_true_when_gross_or_near_miss_decoy_wrongly_passes():
    golden = item(golden_id="g1", article="п. 24")
    gross = item(golden_id="g2", act="Налоговый кодекс", article="обязанность")
    near_miss = item(golden_id="g3", article="п. 33")
    llm = ScriptedLLM([
        json.dumps({"passed": True}),
        json.dumps({"passed": True}),  # грубый подложный НЕ должен пройти, но прошёл
        json.dumps({"passed": True}),  # near-miss подложный тоже прошёл
    ])

    result = verifier_agreement_for_item(golden, gross, near_miss, llm)

    assert result.gross_decoy_passed is True
    assert result.near_miss_decoy_passed is True


def test_verifier_agreement_uses_model_different_from_producer():
    golden = item()
    gross = item(golden_id="g2", article="п. 99")
    llm = ScriptedLLM([json.dumps({"passed": True}), json.dumps({"passed": False})])
    config = load_models_config()

    verifier_agreement_for_item(golden, gross, None, llm, models=config)

    producer_model = config.tiers["mid"]  # VERIFY_PROFILE.tier == 'mid'
    expected_verifier_model = verifier_model_for(producer_model, config)
    assert llm.calls[0][1] == expected_verifier_model
    assert llm.calls[1][1] == expected_verifier_model


def test_verifier_agreement_garbage_answer_is_error_not_exception():
    golden = item()
    gross = item(golden_id="g2", article="п. 99")
    llm = ScriptedLLM(["не могу ответить"])

    result = verifier_agreement_for_item(golden, gross, None, llm)

    assert result.correct_passed is None
    assert result.gross_decoy_passed is None
    assert result.near_miss_decoy_passed is None
    assert result.error is not None
    assert len(llm.calls) == 1  # второй вызов (подложный) не делается после ошибки первого


# ══════════════════════════════════════════════════════════════════════════
# _pick_decoy — не подставляет айтем с ТЕМ ЖЕ source_act
# ══════════════════════════════════════════════════════════════════════════


def test_pick_decoy_skips_items_sharing_same_source_act():
    items = [
        item(golden_id="g1", article="п. 24"),
        item(golden_id="g2", article="п. 24"),  # тот же реквизит, что g1
        item(golden_id="g3", article="п. 40"),  # другой
    ]

    decoy = _pick_decoy(items, 0)

    assert decoy.id == "g3"


def test_pick_decoy_falls_back_to_next_when_all_identical():
    items = [item(golden_id="g1"), item(golden_id="g2")]  # оба одинаковый source_act по умолчанию

    decoy = _pick_decoy(items, 0)

    assert decoy.id == "g2"


# ══════════════════════════════════════════════════════════════════════════
# _pick_near_miss_decoy — тот же акт, ДРУГАЯ статья; n/a если кандидата нет
# ══════════════════════════════════════════════════════════════════════════


def test_pick_near_miss_decoy_finds_same_act_different_article():
    items = [
        item(golden_id="g1", act="ПКМ-290, ТР", article="п. 24"),
        item(golden_id="g2", act="Налоговый кодекс", article="обязанность"),  # другой акт — не near-miss
        item(golden_id="g3", act="ПКМ-290, ТР", article="п. 33"),  # тот же акт, другая статья
    ]

    decoy = _pick_near_miss_decoy(items, 0)

    assert decoy is not None
    assert decoy.id == "g3"


def test_pick_near_miss_decoy_skips_same_act_same_article():
    items = [
        item(golden_id="g1", act="ПКМ-290, ТР", article="п. 24"),
        item(golden_id="g2", act="ПКМ-290, ТР", article="п. 24"),  # тот же акт И та же статья — не near-miss
        item(golden_id="g3", act="ПКМ-290, ТР", article="п. 33"),
    ]

    decoy = _pick_near_miss_decoy(items, 0)

    assert decoy.id == "g3"


def test_pick_near_miss_decoy_none_when_no_same_act_candidate():
    items = [
        item(golden_id="g1", act="ПКМ-290, ТР", article="п. 24"),
        item(golden_id="g2", act="Налоговый кодекс", article="обязанность"),
        item(golden_id="g3", act="ЗРУ-701", article="прил. №1"),
    ]

    decoy = _pick_near_miss_decoy(items, 0)

    assert decoy is None


def test_pick_near_miss_decoy_none_when_item_has_no_source_act():
    items = [
        item(golden_id="g1", act=None, article=None),
        item(golden_id="g2", act="ПКМ-290, ТР", article="п. 33"),
    ]

    decoy = _pick_near_miss_decoy(items, 0)

    assert decoy is None


# ══════════════════════════════════════════════════════════════════════════
# category_accuracy_for_item — через реальный Classifier
# ══════════════════════════════════════════════════════════════════════════


def test_category_accuracy_correct_match():
    golden = item(category_slug="marking")
    llm = ScriptedLLM([json.dumps({"category_slug": "marking"})])

    result = category_accuracy_for_item(golden, llm, ["marking", "tbt", "customs"])

    assert result.predicted == "marking"
    assert result.correct is True


def test_category_accuracy_mismatch():
    golden = item(category_slug="marking")
    llm = ScriptedLLM([json.dumps({"category_slug": "tbt"})])

    result = category_accuracy_for_item(golden, llm, ["marking", "tbt"])

    assert result.correct is False


def test_category_accuracy_skips_when_golden_has_no_category():
    golden = item(category_slug=None)
    llm = ScriptedLLM([])

    result = category_accuracy_for_item(golden, llm, ["marking", "tbt"])

    assert result.correct is None
    assert llm.calls == []


def test_category_accuracy_valid_slugs_appear_in_prompt():
    golden = item(category_slug="marking")
    llm = ScriptedLLM([json.dumps({"category_slug": "marking"})])

    category_accuracy_for_item(golden, llm, ["marking", "sps", "customs"])

    prompt = llm.calls[0][0]
    assert "marking" in prompt and "sps" in prompt and "customs" in prompt


def test_category_accuracy_garbage_answer_is_error_not_exception():
    golden = item(category_slug="marking")
    llm = ScriptedLLM(["мусор"])

    result = category_accuracy_for_item(golden, llm, ["marking"])

    assert result.correct is None
    assert result.error is not None


# ══════════════════════════════════════════════════════════════════════════
# lifecycle_date_accuracy_for_item — через реальный Classifier
# ══════════════════════════════════════════════════════════════════════════


def test_lifecycle_date_accuracy_exact_match_all_null():
    golden = item(lifecycle=(None, None, None))
    llm = ScriptedLLM([json.dumps({
        "effective_from": None, "transition_until": None, "valid_to": None, "repealed_by_ref": None,
    })])

    result = lifecycle_date_accuracy_for_item(golden, llm)

    assert result.field_accuracy == 1.0
    assert result.exact_match is True


def test_lifecycle_date_accuracy_partial_mismatch():
    golden = item(lifecycle=(None, None, None))
    llm = ScriptedLLM([json.dumps({
        "effective_from": "2026-01-01", "transition_until": None, "valid_to": None, "repealed_by_ref": None,
    })])

    result = lifecycle_date_accuracy_for_item(golden, llm)

    assert result.field_accuracy == pytest.approx(2 / 3)
    assert result.exact_match is False


def test_lifecycle_date_accuracy_garbage_answer_is_error_not_exception():
    golden = item()
    llm = ScriptedLLM(["не JSON"])

    result = lifecycle_date_accuracy_for_item(golden, llm)

    assert result.field_accuracy is None
    assert result.error is not None


# ══════════════════════════════════════════════════════════════════════════
# run_eval — агрегаты + таблица по ролям + дельта
# ══════════════════════════════════════════════════════════════════════════


def _three_item_set() -> list[GoldenItem]:
    """3 айтема: g1/g2 делят акт ПКМ-290 (разные статьи — near-miss друг
    для друга), g3 — единственный со своим актом (n/a для near-miss,
    гросс-декой для соседей). Порядок [g1, g3, g2] — так `_pick_decoy(g1)`
    сразу натыкается на g3 (полностью другой акт, чистый «грубый» декой),
    а `_pick_near_miss_decoy(g1)` доходит до g2 (тот же акт, другая статья)
    — конкретные цели уже проверены отдельно в тестах `_pick_decoy`/
    `_pick_near_miss_decoy` выше, здесь важны только агрегаты. Тексты несут
    ключевые слова `_CATEGORY_KEYWORDS`, чтобы `HeuristicBaselineLLM`
    детерминированно классифицировала их в ОЖИДАЕМУЮ категорию (без
    scripted-очереди ответов — реальное поведение эвристики, порядок
    вызовов LLM руками не считаем)."""
    return [
        item(golden_id="g1", expected_item="Наносить маркировку на упаковку",
             category_slug="marking", act="ПКМ-290, ТР", article="п. 24"),
        item(golden_id="g3", expected_item="Установить онлайн-кассу",
             category_slug="fiscal", act="Налоговый кодекс", article="обязанность"),
        item(golden_id="g2", expected_item="Соблюдать технический регламент по сигаретам",
             category_slug="tbt", act="ПКМ-290, ТР", article="п. 40"),
    ]


def test_run_eval_aggregates_and_markdown_table():
    items = _three_item_set()
    legalx = FakeLegalX(responses=[
        [fragment(act_title="ПКМ-290, ТР", article_ref="п. 24")],             # g1 retrieval hit
        [fragment(act_title="Налоговый кодекс", article_ref="обязанность")],  # g3 retrieval hit
        [fragment(act_title="ПКМ-290, ТР", article_ref="п. 40")],             # g2 retrieval hit
    ])
    llm = HeuristicBaselineLLM()  # реальное (не scripted) поведение — независимо unit-тестировано ниже

    report = run_eval(
        items, legalx=legalx, llm=llm, valid_category_slugs=["marking", "tbt", "fiscal"], backend="mock",
    )
    m = report.metrics

    assert m.retrieval_hit_rate == 1.0
    assert m.verifier_pass_on_correct_rate == 1.0
    assert m.verifier_fail_on_gross_decoy_rate == 1.0
    # near-miss измерим только для g1 и g2 (делят акт ПКМ-290, разные статьи) — g3 n/a (уникальный акт)
    assert m.verifier_fail_on_near_miss_decoy_rate == 1.0
    assert m.verifier_near_miss_na == 1
    assert m.category_accuracy == 1.0
    assert m.lifecycle_date_exact_match_rate == 1.0
    assert "Retriever" in report.markdown
    assert "Verifier" in report.markdown
    assert "Classifier" in report.markdown
    assert "near_miss" in report.markdown


def test_run_eval_with_baseline_prints_delta():
    items = _three_item_set()
    legalx = FakeLegalX(responses=[[], [], []])  # ничего не находит -> retrieval misses (via no_norm)
    llm = HeuristicBaselineLLM()
    baseline = {
        "retrieval_hit_rate": 0.5,
        "verifier_pass_on_correct_rate": 1.0,
        "verifier_fail_on_gross_decoy_rate": 1.0,
        "verifier_fail_on_near_miss_decoy_rate": 1.0,
        "category_accuracy": 0.5,
    }

    report = run_eval(
        items, legalx=legalx, llm=llm, valid_category_slugs=["marking", "tbt", "fiscal"],
        backend="mock", baseline=baseline,
    )

    assert "Дельта против baseline.json" in report.markdown
    assert report.metrics.retrieval_hit_rate == 0.0  # 0/3 hits
    # verifier не зависит от retrieval — суб-метрики те же, что и в первом тесте
    assert report.metrics.verifier_fail_on_near_miss_decoy_rate == 1.0


def test_compute_delta_skips_metrics_missing_on_either_side():
    metrics = AggregateMetrics(
        total_items=1, retrieval_hit_rate=0.8, retrieval_hits=4, retrieval_misses=1,
        retrieval_no_source_act=0, retrieval_errors=0,
        verifier_pass_on_correct_rate=None, verifier_fail_on_gross_decoy_rate=None,
        verifier_fail_on_near_miss_decoy_rate=None, verifier_near_miss_na=0, verifier_errors=0,
        category_accuracy=0.9, category_measured=10, category_errors=0,
        lifecycle_date_field_accuracy=1.0, lifecycle_date_exact_match_rate=1.0, lifecycle_errors=0,
    )
    baseline = {"retrieval_hit_rate": 0.5, "category_accuracy": None}  # нет verifier_*_rate вовсе

    delta = compute_delta(metrics, baseline)

    assert delta["retrieval_hit_rate"] == {"baseline": 0.5, "current": 0.8, "delta": pytest.approx(0.3)}
    assert delta["verifier_pass_on_correct_rate"] is None  # текущее None
    assert delta["verifier_fail_on_gross_decoy_rate"] is None
    assert delta["verifier_fail_on_near_miss_decoy_rate"] is None
    assert delta["category_accuracy"] is None  # baseline None


def test_compute_delta_all_three_verifier_submetrics():
    metrics = AggregateMetrics(
        total_items=3, retrieval_hit_rate=1.0, retrieval_hits=3, retrieval_misses=0,
        retrieval_no_source_act=0, retrieval_errors=0,
        verifier_pass_on_correct_rate=1.0, verifier_fail_on_gross_decoy_rate=0.8,
        verifier_fail_on_near_miss_decoy_rate=0.6, verifier_near_miss_na=1, verifier_errors=0,
        category_accuracy=1.0, category_measured=3, category_errors=0,
        lifecycle_date_field_accuracy=1.0, lifecycle_date_exact_match_rate=1.0, lifecycle_errors=0,
    )
    baseline = {
        "verifier_pass_on_correct_rate": 1.0,
        "verifier_fail_on_gross_decoy_rate": 1.0,
        "verifier_fail_on_near_miss_decoy_rate": 0.5,
    }

    delta = compute_delta(metrics, baseline)

    assert delta["verifier_pass_on_correct_rate"]["delta"] == pytest.approx(0.0)
    assert delta["verifier_fail_on_gross_decoy_rate"]["delta"] == pytest.approx(-0.2)
    assert delta["verifier_fail_on_near_miss_decoy_rate"]["delta"] == pytest.approx(0.1)


# ══════════════════════════════════════════════════════════════════════════
# HeuristicBaselineLLM — заглушка ТОЛЬКО для baseline.json (без семантики)
# ══════════════════════════════════════════════════════════════════════════


def test_heuristic_baseline_llm_signals_no_norm_for_retriever_prompt():
    llm = ScriptedLLM([])  # не используется, просто для симметрии сигнатуры
    heuristic = HeuristicBaselineLLM()
    legalx = FakeLegalX(responses=[[], [], []])
    golden = item()

    result = retrieval_hit_for_item(golden, legalx, heuristic)

    assert result.outcome == "miss"  # no_norm сразу после первого пустого поиска


def test_heuristic_baseline_llm_verifier_passes_when_source_embedded_in_fragment():
    from importer.build.agents import Verifier
    from importer.build.eval_golden import VERIFY_PROFILE

    verifier = Verifier(llm=HeuristicBaselineLLM(), model="gpt-5")

    passed = verifier.run(
        question="q", fragment="Пройти таможенное оформление (ПКМ-290, ТР, п. 24)",
        source="ПКМ-290, ТР, п. 24", profile=VERIFY_PROFILE,
    )
    failed = verifier.run(
        question="q", fragment="Совсем другое требование (ПКМ-290, ТР, п. 40)",
        source="ПКМ-290, ТР, п. 24", profile=VERIFY_PROFILE,
    )

    assert passed.passed is True
    assert failed.passed is False


def test_heuristic_baseline_llm_classifies_category_by_keywords():
    from importer.build.agents import Classifier
    from importer.build.eval_golden import _category_profile

    classifier = Classifier(HeuristicBaselineLLM())
    profile = _category_profile(["marking", "sps", "customs", "tbt"])

    result = classifier.run("Продавать только маркированные лекарства", profile)

    assert result["category_slug"] == "marking"


def test_heuristic_baseline_llm_lifecycle_always_null():
    from importer.build.agents import Classifier
    from importer.build.steps_scope_lifecycle import LIFECYCLE_PROFILE

    classifier = Classifier(HeuristicBaselineLLM())

    result = classifier.run("любой текст требования", LIFECYCLE_PROFILE)

    assert result == {
        "effective_from": None, "transition_until": None, "valid_to": None, "repealed_by_ref": None,
    }


def test_heuristic_baseline_llm_unknown_prompt_raises():
    with pytest.raises(AgentLLMError):
        HeuristicBaselineLLM().complete("совершенно нераспознаваемый текст промпта", "model")


# ══════════════════════════════════════════════════════════════════════════
# Интеграционный тест генератора — живая локальная БД, скипается без неё
# ══════════════════════════════════════════════════════════════════════════


def _local_supabase_reachable() -> bool:
    try:
        proc = subprocess.run(
            ["supabase", "db", "query", "select 1;", "--local", "-o", "json", "--agent=no"],
            cwd=Path(__file__).resolve().parents[3], capture_output=True, text=True, timeout=15,
        )
        return proc.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


@pytest.mark.integration
@pytest.mark.skipif(not _local_supabase_reachable(), reason="локальный Supabase не поднят (supabase db start && supabase db reset --local)")
def test_generate_golden_set_against_local_db():
    import generate_golden_set  # noqa: E402 — модуль в scripts/, путь добавлен выше

    doc = generate_golden_set.generate()

    assert doc["status"].startswith("draft")
    assert doc["counters"]["total"] == 20
    assert doc["counters"]["distinct_categories"] >= 3
    assert "product" in doc["counters"]["by_kind"]
    assert "service" in doc["counters"]["by_kind"]
    # каждый айтем обязан собираться в GoldenItem без ошибок формата
    loaded_items = [
        GoldenItem(
            id=raw["id"], expected_item=raw["expected_item"], category_slug=raw["category_slug"],
            canonical_question=raw["canonical_question"],
            source_act=SourceAct(**raw["source_act"]),
            lifecycle_dates=LifecycleDates(**raw["lifecycle_dates"]),
            sanction_article=raw["sanction_article"],
            origin=GoldenOrigin(**raw["origin"]),
        )
        for raw in doc["items"]
    ]
    assert len(loaded_items) == 20
