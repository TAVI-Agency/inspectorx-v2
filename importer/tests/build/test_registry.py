"""Фабрика per-run STEP_ORDER-шагов `build_step_registry` (Задача 27,
ADR-0003 «Блок 2», финал).

Сценарии из брифа задачи: фабрика прокидывает `jurisdiction`/`group_ref`/
`target_lang` в конкретные шаги — БЕЗ обращения к LLM/LegalX/вебу при самом
конструировании (тест использует `_runner`/`_legalx`, которые падают при
любом реальном вызове — если фабрика случайно дёрнет что-то живое при
конструировании шага, тест обвалится, а не молча пропустит проблему).
"""
from __future__ import annotations

from typing import NoReturn

from importer.build.legalx import CourtCase, NormFragment
from importer.build.registry import build_step_registry, target_lang_for_jurisdiction
from importer.build.steps import STEP_ORDER
from importer.tests.build.stores import InMemoryStore


def _runner(prompt: str, model: str) -> NoReturn:
    raise AssertionError("registry-тест не должен звать LLM — только конструирование шагов")


class _AssertingLegalX:
    """LegalXClient-заглушка: падает при любом реальном вызове (то же
    назначение, что и `_runner` выше — тест проверяет ТОЛЬКО wiring)."""

    def search_norms(self, query: str, jurisdiction: str, domains=None, limit: int = 10) -> list[NormFragment]:
        raise AssertionError("registry-тест не должен звать LegalX — только конструирование шагов")

    def search_cases(self, article: str, topic: str | None = None, limit: int = 5) -> list[CourtCase]:
        raise AssertionError("registry-тест не должен звать LegalX — только конструирование шагов")


def _build(group_ref: str = "2204", jurisdiction: str = "UZ") -> dict:
    store = InMemoryStore()
    return build_step_registry(
        store, _runner, _AssertingLegalX(), group_ref=group_ref, jurisdiction=jurisdiction,
    )


# ── набор шагов: STEP_ORDER без 'coverage' ────────────────────────────────


def test_registry_builds_exactly_step_order_minus_coverage():
    steps = _build()
    assert set(steps) == set(STEP_ORDER) - {"coverage"}
    assert "coverage" not in steps  # run-level, не per-item шаг (coverage.py)


# ── jurisdiction прокидывается в jurisdiction-зависимые шаги ──────────────


def test_registry_injects_jurisdiction_into_norm_sanctions_cases_assemble_load():
    steps = _build(jurisdiction="AE")
    assert steps["norm"]._jurisdiction == "AE"
    assert steps["sanctions"]._jurisdiction == "AE"
    assert steps["cases"]._jurisdiction == "AE"
    assert steps["assemble"]._jurisdiction == "AE"
    assert steps["load"]._jurisdiction == "AE"


def test_registry_default_uz_jurisdiction_also_wired_through():
    steps = _build(jurisdiction="UZ")
    assert steps["norm"]._jurisdiction == "UZ"
    assert steps["load"]._jurisdiction == "UZ"


# ── group_ref прокидывается в group_ref-зависимые шаги ────────────────────


def test_registry_injects_group_ref_into_scope_and_load():
    steps = _build(group_ref="2204")
    assert steps["scope"]._group_ref == "2204"
    assert steps["load"]._group_ref == "2204"


def test_registry_different_group_ref_reflected_in_both_steps():
    steps = _build(group_ref="8703")
    assert steps["scope"]._group_ref == "8703"
    assert steps["load"]._group_ref == "8703"


# ── target_lang по jurisdiction (решение контроллера Задачи 27) ──────────


def test_registry_derives_target_lang_uz_from_uz_jurisdiction():
    steps = _build(jurisdiction="UZ")
    assert steps["translate"]._target_lang == "uz"


def test_registry_derives_target_lang_en_from_ae_jurisdiction():
    steps = _build(jurisdiction="AE")
    assert steps["translate"]._target_lang == "en"


def test_registry_derives_no_target_lang_from_kz_jurisdiction():
    steps = _build(jurisdiction="KZ")
    assert steps["translate"]._target_lang is None


def test_target_lang_for_jurisdiction_mapping_matches_registry():
    assert target_lang_for_jurisdiction("UZ") == "uz"
    assert target_lang_for_jurisdiction("AE") == "en"
    assert target_lang_for_jurisdiction("KZ") is None
    assert target_lang_for_jurisdiction("XX") is None  # неизвестная — безопасный дефолт (не ошибка)
