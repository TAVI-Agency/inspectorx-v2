import pytest
from importer.refs import lexuz_doc_id, parse_unit_ref

@pytest.mark.parametrize("url,expected", [
    ("https://lex.uz/docs/-6445145", "6445145"),
    ("https://lex.uz/ru/docs/-6445145#p12", "6445145"),
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
])
def test_parse_unit_ref(unit, expected):
    assert parse_unit_ref(unit) == expected
