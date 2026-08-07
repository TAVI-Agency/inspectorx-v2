from __future__ import annotations

import pytest

from .conftest import requires_db

pytestmark = [pytest.mark.integration, requires_db]


def test_photo_checklist_returns_rows_for_tobacco(service, tobacco_product_id):
    rows = service.rpc("photo_checklist", {
        "p_product_id": tobacco_product_id, "p_level": "consumer",
        "p_markets": ["UZ", "EAEU"]}).execute().data
    assert len(rows) >= 70            # у табака consumer ~79 пунктов (план §2А шаг 1)
    kinds = {r["kind"] for r in rows}
    assert kinds <= {"presence", "text_semantic", "absence", "geometry"}


def test_checkable_requirement_must_have_checks(service):
    """Починка тавтологичного CHECK из DB_EXTENSION.sql: checkable без единой
    проверки не проходит constraint-триггер."""
    with pytest.raises(Exception, match="checkable_needs_checks"):
        service.table("requirement_photo").insert({
            "rule_ref": "test.orphan", "title_ru": "сирота",
            "checkability": "checkable", "packaging_level": "consumer",
            "why": "тест"}).execute()


def test_params_json_schema_constraint(service):
    """surface принимает любую строку (словарь vision — ratchet-цель линтера,
    не форма текущих данных — см. комментарий в 20260810130000_requirement_photo.sql),
    а language остаётся закрытым словарём — невалидный код языка бьёт constraint."""
    with pytest.raises(Exception):
        service.table("requirement_photo_checks").insert({
            "rule_ref": "test.orphan", "check_id": "bad", "kind": "geometry",
            "severity": "major", "group_key": "geometry", "subject": "x",
            "packaging_level": "both", "measure": "min_size_mm",
            "params": {"language": ["xx"]}}).execute()


def test_photo_checklist_respects_packaging_level(service, tobacco_product_id):
    """Требование потребительского уровня не должно всплывать в транспортном
    чек-листе (и наоборот) — независимый фильтр от уровня отдельной проверки,
    как в compile_checklist() на стороне vision."""
    consumer_refs = {r["rule_ref"] for r in service.rpc("photo_checklist", {
        "p_product_id": tobacco_product_id, "p_level": "consumer",
        "p_markets": ["UZ", "EAEU"]}).execute().data}
    transport_refs = {r["rule_ref"] for r in service.rpc("photo_checklist", {
        "p_product_id": tobacco_product_id, "p_level": "transport",
        "p_markets": ["UZ", "EAEU"]}).execute().data}
    # Хотя бы часть пунктов уникальна своему уровню — списки не идентичны
    assert consumer_refs - transport_refs
    assert transport_refs - consumer_refs


def test_photo_checklist_includes_any_market_requirements(service, tobacco_product_id):
    """markets=['ANY'] (горизонтальные нормы gs1/horizontal) обязаны попасть в
    чек-лист при любом запрошенном рынке — это НЕ буквальное пересечение
    массивов, особый случай (см. комментарий в photo_checklist())."""
    rows = service.rpc("photo_checklist", {
        "p_product_id": tobacco_product_id, "p_level": "consumer",
        "p_markets": ["UZ"]}).execute().data
    assert any(r["rule_ref"].startswith("gs1.") for r in rows)
