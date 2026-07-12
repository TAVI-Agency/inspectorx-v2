import pytest
from pydantic import ValidationError
from importer.models import ProductReport, ServiceReport, parse_report_json

PRODUCT_JSON = {
    "product": {"name": "Цемент", "hs_code": "2523290000", "ikpu": ["23941001"],
                "domain": "стройматериалы", "duty": "0%", "excise": None, "vat": "12%"},
    "requirements": [{
        "title": "Получить сертификат соответствия", "nature": "obligation", "type": "import",
        "category": "Оценка соответствия, декларация и сертификация",
        "summary": "Цемент подлежит обязательной сертификации.",
        "legal_quote_ru": "продукция подлежит обязательному подтверждению соответствия",
        "act": {"name": "Закон о техническом регулировании", "number": "ЗРУ-819",
                "date": "2023-04-05", "lexuz_url": "https://lex.uz/docs/-6445145"},
        "unit": "ст. 14", "edition_date": "2025-12-20",
        "scope": {"level": "hs_list", "codes": ["2523"], "list_row": "строка 91 прил. 4"},
        "addressees": ["importer"], "agency": "Узстандарт",
        "how_to": [{"step": "Подать заявку", "deadline": "10 дней", "source_act_url": None}],
        "documents": [{"name": "Заявка", "where": "Узстандарт"}],
        "sanction": {"article": "ст. 186 КоАО", "fine_bru": "до 75 БРВ", "extra": None, "url": None},
        "discovered_via": "list", "needs_review": False
    }]
}

def test_product_report_validates():
    report = ProductReport.model_validate(PRODUCT_JSON)
    assert report.product.hs_code == "2523290000"
    assert report.requirements[0].scope.level == "hs_list"

def test_invalid_nature_rejected():
    bad = {**PRODUCT_JSON, "requirements": [{**PRODUCT_JSON["requirements"][0], "nature": "wish"}]}
    with pytest.raises(ValidationError):
        ProductReport.model_validate(bad)

def test_service_report_validates():
    data = {"service": {"name": "Аптека", "okved": "47.73", "admission_type": "license",
                        "licensor": "Минздрав", "related_products": []},
            "requirements": [{**PRODUCT_JSON["requirements"][0],
                              "stage": "start", "periodicity": "once", "scope": "this_okved"}]}
    data["requirements"][0] = {k: v for k, v in data["requirements"][0].items()
                               if k not in ("type", "category")}
    report = ServiceReport.model_validate(data)
    assert report.requirements[0].stage == "start"

def test_parse_report_json_dispatch():
    assert isinstance(parse_report_json(PRODUCT_JSON, "product"), ProductReport)

def test_null_placeholders_tolerated():
    """Реальные отчёты: ikpu=[null], documents=[{name:null,where:null}] — пустышки отбрасываем."""
    data = {**PRODUCT_JSON,
            "product": {**PRODUCT_JSON["product"], "ikpu": [None]},
            "requirements": [{**PRODUCT_JSON["requirements"][0],
                              "documents": [{"name": None, "where": None},
                                            {"name": "Заявка", "where": None}]}]}
    report = ProductReport.model_validate(data)
    assert report.product.ikpu == []
    assert [d.name for d in report.requirements[0].documents] == ["Заявка"]
