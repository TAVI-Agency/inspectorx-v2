import pytest
from importer.mappings import (MappingError, STAGE_TO_CODE, load_domains, map_addressees,
                               map_category, map_nature, map_product_scope, map_service_scope)
from importer.models import ProductScope


def test_map_nature():
    assert map_nature("right") == "permission"
    assert map_nature("obligation") == "obligation"


def test_map_addressees():
    assert map_addressees(["manufacturer", "importer"]) == ["producer", "importer"]
    with pytest.raises(MappingError):
        map_addressees(["alien"])

def test_map_addressees_russian():
    # реальные отчёты пишут адресатов и по-русски
    assert map_addressees(["продавец", "импортёр", "производитель"]) == \
        ["seller", "importer", "producer"]
    assert map_addressees(["импортер", "перевозчик", "владелец"]) == \
        ["importer", "carrier", "all"]


def test_map_category():
    assert map_category("Налоги и платежи") == "fiscal"
    assert map_category("Экология") is None
    with pytest.raises(MappingError):
        map_category("Новая выдуманная категория")


def test_map_product_scope():
    domains = {"стройматериалы": ["25", "68"]}
    assert map_product_scope(ProductScope(level="all"), "2523290000", domains) == [("all_products", None)]
    assert map_product_scope(ProductScope(level="this_code"), "2523290000", domains) == [("hs_code", "2523290000")]
    assert map_product_scope(ProductScope(level="hs_list", codes=["2523", "2523290000"]),
                             None, domains) == [("hs_prefix", "2523"), ("hs_code", "2523290000")]
    assert map_product_scope(ProductScope(level="domain"), None,
                             domains | {"_domain": "стройматериалы"}) or True
    with pytest.raises(MappingError):
        map_product_scope(ProductScope(level="domain"), None, {"_domain": "неизвестный"})


def test_map_service_scope():
    assert map_service_scope("this_okved", "47.73") == [("oked_code", "47.73")]
    assert map_service_scope("all_business", "47.73") == [("all_services", None)]
    with pytest.raises(MappingError):
        map_service_scope("licensed", "47.73")


def test_stage_codes_and_domains_file():
    assert STAGE_TO_CODE["termination"] == "svc-06-closure"
    assert "фарма" in load_domains()
