"""Сид товаров под фотоконтроль (20260810170000_seed_photocontrol_products.sql).

До этой миграции photo_profile_for_product() резолвил ровно один товар каталога —
молоко 0401201100; табачных (2402*) и электронных (84*/85*) товаров в
public.products не было вовсе, поэтому api/vision/checklist.ts отдавал
404 no_checklist для всех, кроме молока. Тесты держат три инварианта: товар в
каталоге есть, профиль движка резолвится, чек-лист непустой — и что товар
вообще находится поиском витрины (иначе выбрать его на /checks/packaging нельзя).
"""
from __future__ import annotations

import pytest

from .conftest import requires_db

pytestmark = [pytest.mark.integration, requires_db]

# hs_code -> (profile_id движка, дефолтный алиас поиска)
SEEDED = {
    "2402209000": ("tobacco", "Сигареты"),
    "8517620009": ("electronics", "Wi-Fi роутер"),
    "8517130000": ("electronics", "Смартфон"),
}


def _product(service, hs_code: str) -> dict:
    rows = service.table("products").select(
        "id, hs_code, name_ru, name_uz, is_active, product_type_id").eq(
        "hs_code", hs_code).execute().data
    assert rows, f"товар {hs_code} не засеян"
    return rows[0]


@pytest.mark.parametrize("hs_code", sorted(SEEDED))
def test_seeded_product_resolves_engine_profile(service, hs_code):
    product = _product(service, hs_code)
    assert product["is_active"] is True
    assert product["name_uz"], "name_uz заполняем — товар курируемый, не из снапшота v1"
    profile = service.rpc("photo_profile_for_product",
                          {"p_product_id": product["id"]}).execute().data
    assert profile == SEEDED[hs_code][0]


@pytest.mark.parametrize("hs_code", sorted(SEEDED))
@pytest.mark.parametrize("level", ["consumer", "transport"])
def test_seeded_product_has_non_empty_checklist(service, hs_code, level):
    """Профиль резолвится — но чек-лист мог бы оказаться пустым (например, если
    у пакета нет ни одного правила нужного уровня упаковки). Проверяем факт, а
    не только проводку."""
    product = _product(service, hs_code)
    rows = service.rpc("photo_checklist", {
        "p_product_id": product["id"], "p_level": level,
        "p_markets": ["UZ"]}).execute().data
    assert len(rows) > 0, f"пустой чек-лист {hs_code}/{level}"
    # вертикальный пакет своего профиля обязан присутствовать, а не только
    # горизонтальные gs1/horizontal/uzbekistan — иначе «чек-лист есть», но
    # товарной специфики в нём нет
    packs = {r["rule_ref"].split(".", 1)[0] for r in rows}
    assert SEEDED[hs_code][0] in packs


@pytest.mark.parametrize("hs_code", sorted(SEEDED))
def test_seeded_product_is_findable_by_search(service, hs_code):
    """Поиск витрины (src/data/real.ts:294) — три запроса без RPC: ilike по
    search_aliases.alias, ilike по products.name_ru, like по hs_code. Без
    дефолтного алиаса товар в выдаче показался бы официальной строкой ТН ВЭД.

    default'ов ровно один и он русский: defaultAliases() строит Map без фильтра
    по языку, второй is_default перетирает первый — при трёх языковых default'ах
    в выдаче показывалось «cigarettes» вместо «Сигареты» (поймано скриншотом)."""
    product = _product(service, hs_code)
    alias = SEEDED[hs_code][1]
    rows = service.table("search_aliases").select("alias, lang, is_default").eq(
        "product_id", product["id"]).execute().data
    assert rows, f"у товара {hs_code} нет алиасов — поиском его не найти"
    defaults = [r for r in rows if r["is_default"]]
    assert [(r["alias"], r["lang"]) for r in defaults] == [(alias, "ru")]


def test_cigarettes_are_findable_by_word_cigarettes(service):
    """Ключевая жалоба владельца: запрос «сигареты» не находил ничего (витринный
    флагман — стики IQOS 2404110001 с единственным алиасом «IQOS»)."""
    hits = service.table("search_aliases").select(
        "product_id, products(hs_code)").ilike("alias", "%сигарет%").execute().data
    assert "2402209000" in {h["products"]["hs_code"] for h in hits if h["products"]}


@pytest.mark.parametrize("hs_code", sorted(SEEDED))
def test_seeded_product_wired_into_catalog(service, hs_code):
    """ADR-0004: у товара должен быть тип (HS6) и национальный код ТН ВЭД —
    на проде product_type_id заполнен у всех 265 товаров без исключения."""
    product = _product(service, hs_code)
    assert product["product_type_id"]
    catalog = service.schema("catalog")
    ptype = catalog.table("product_types").select("hs_code, kind").eq(
        "id", product["product_type_id"]).execute().data[0]
    assert ptype["kind"] == "good"
    assert ptype["hs_code"] == hs_code[:6]
    codes = catalog.table("country_codes").select("code").eq(
        "country", "UZ").eq("system", "tnved").eq("code", hs_code).execute().data
    assert codes, f"нет строки catalog.country_codes UZ/tnved/{hs_code}"


def test_iqos_still_has_no_engine_profile(service):
    """Осознанно зафиксированная развилка, НЕ решённая сидом: витринный флагман
    «стики IQOS» — 2404110001, а photo_profiles.tobacco покрывает {2402,2403}.
    Профиль у него не резолвится. Если владелец решит расширить префиксы до
    2404, этот тест обязан упасть и быть переписан — молча такое меняться не должно.
    """
    rows = service.table("products").select("id").eq(
        "hs_code", "2404110001").execute().data
    if not rows:                                   # на локальной базе товар из v1-сида есть
        pytest.skip("товар 2404110001 отсутствует в этой базе")
    profile = service.rpc("photo_profile_for_product",
                          {"p_product_id": rows[0]["id"]}).execute().data
    assert profile is None
