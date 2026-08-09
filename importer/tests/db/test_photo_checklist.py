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
    with pytest.raises(Exception, match="photo_check_params_valid"):
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


def _insert_synthetic(service, rule_ref: str, check_id: str, **rp_overrides):
    """Синтетическая пара requirement_photo + один check — три теста ниже
    проверяют фильтры photo_checklist(), которые данные сами по себе сегодня
    не нарушают (генератор их не производит), но SQL обязана держать явно, а
    не полагаться на внешнее соглашение экспорта."""
    row = {
        "rule_ref": rule_ref, "title_ru": "синтетика ревью", "checkability": "partial",
        "packaging_level": "consumer", "why": "тест", "markets": ["ANY"],
        "scope": "all_products",
    }
    row.update(rp_overrides)
    service.table("requirement_photo").insert(row).execute()
    service.table("requirement_photo_checks").insert({
        "rule_ref": rule_ref, "check_id": check_id, "kind": "presence",
        "severity": "major", "group_key": "identity", "subject": "synthetic",
        "packaging_level": "consumer", "target": "synthetic",
    }).execute()


def test_photo_checklist_does_not_leak_across_verticals(service, tobacco_product_id):
    """Правка ревью Задачи 15: SQL обязана фильтровать по requirement_photo.pack
    ровно как Python-эталон обходит только product.packs (compile_checklist /
    bench_sql_parity.py:85-87) — иначе all_products-требование ЧУЖОГО
    вертикального пакета (dairy) протекает на товары другой вертикали
    (tobacco), потому что 'all_products' в данных означает «все товары ВНУТРИ
    пакета», а не буквально все товары системы."""
    rule_ref = "test.review.dairy_pack_leak"
    _insert_synthetic(service, rule_ref, "leak.check", pack="dairy")
    try:
        rows = service.rpc("photo_checklist", {
            "p_product_id": tobacco_product_id, "p_level": "consumer",
            "p_markets": ["UZ", "EAEU"]}).execute().data
        assert rule_ref not in {r["rule_ref"] for r in rows}
    finally:
        service.table("requirement_photo").delete().eq("rule_ref", rule_ref).execute()


def test_photo_checklist_any_market_is_membership_not_equality(service, tobacco_product_id):
    """markets=['ANY', 'UZ'] — 'ANY' вперемешку с настоящим кодом рынка;
    равенство массива (`rp.markets = array['ANY']`) такую строку бы упустило,
    членство (`'ANY' = any(rp.markets)`) — нет. Пакет 'tobacco' — свой для
    фикстуры, рынок запроса намеренно не пересекается с 'UZ' в данных."""
    rule_ref = "test.review.any_mixed_market"
    _insert_synthetic(service, rule_ref, "any.check", pack="tobacco", markets=["ANY", "UZ"])
    try:
        rows = service.rpc("photo_checklist", {
            "p_product_id": tobacco_product_id, "p_level": "consumer",
            "p_markets": ["EAEU"]}).execute().data
        assert rule_ref in {r["rule_ref"] for r in rows}
    finally:
        service.table("requirement_photo").delete().eq("rule_ref", rule_ref).execute()


def test_photo_checklist_excludes_not_checkable(service, tobacco_product_id):
    """checkability='not_checkable' с проверкой (данные экспорта такого не
    производят, но constraint-триггер этого и не запрещает — только
    checkable ⇒ есть проверка, не наоборот) не должна выдаваться —
    photo_checklist() отсекает not_checkable сама, не полагаясь на то, что у
    таких строк случайно нет checks."""
    rule_ref = "test.review.not_checkable_with_check"
    _insert_synthetic(service, rule_ref, "nc.check", pack="tobacco", checkability="not_checkable")
    try:
        rows = service.rpc("photo_checklist", {
            "p_product_id": tobacco_product_id, "p_level": "consumer",
            "p_markets": ["UZ", "EAEU"]}).execute().data
        assert rule_ref not in {r["rule_ref"] for r in rows}
    finally:
        service.table("requirement_photo").delete().eq("rule_ref", rule_ref).execute()
