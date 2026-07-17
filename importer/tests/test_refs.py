import pytest
from importer.refs import lexuz_doc_id, parse_unit_ref

@pytest.mark.parametrize("url,expected", [
    # знак — часть id: на lex.uz /docs/-N и /docs/N — разные документы
    ("https://lex.uz/docs/-6445145", "-6445145"),
    ("https://lex.uz/ru/docs/-6445145#p12", "-6445145"),
    ("https://www.lex.uz/acts/6445145", "6445145"),
    ("https://lex.uz/uz/docs/6445145/", "6445145"),
    ("https://example.com/doc/123", None),
    (None, None),
])
def test_lexuz_doc_id(url, expected):
    assert lexuz_doc_id(url) == expected

@pytest.mark.parametrize("unit,expected", [
    ("ст. 14", "art.14"),
    ("статья 14", "art.14"),
    ("ст. 186-1", "art.186-1"),
    ("п. 11", "p.11"),
    ("пункт 11", "p.11"),
    ("п. 5 ст. 14", "art.14/p.5"),
    ("прил. 2", "app2"),
    ("приложение 4, строка 91", "app4/row91"),
    ("прил. 4, строка 91", "app4/row91"),
    ("раздел 3", "sec.3"),
    ("непонятное", None),
    (None, None),
    # реальные форматы из отчётов (живой прогон 12.07.2026)
    ("прил. № 1, п. 5 (гл. 3)", "app1/p.5"),
    ("прил. № 1, раздел по ТС с электродвигателем (870380)", "app1"),
    ("ст. 4; гл. 3", "art.4"),
    ("ст. 254, ст. 258", "art.254"),
    ("ст. 14 (ЗРУ-706); прил. № 1, гл. 2 (ПКМ № 683)", "art.14"),
    ("прил. №1–3 (перечни лицензируемых видов и разрешений)", "app1-3"),
    ("ст. 227-22, ст. 227 КоАО", "art.227-22"),
])
def test_parse_unit_ref(unit, expected):
    assert parse_unit_ref(unit) == expected


def test_glava_pattern():
    from importer.refs import parse_unit_ref
    assert parse_unit_ref("гл. 3") == "ch.3"
    assert parse_unit_ref("глава 7 (ст. 34-46)") == "ch.7"
