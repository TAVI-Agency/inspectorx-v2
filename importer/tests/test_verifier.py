from pathlib import Path
from importer.lexuz import LexuzClient, LexuzUnreachable
from importer.models import ProductRequirement
from importer.verifier import verify_item

FIX = Path(__file__).parent / "fixtures"
HTML = (FIX / "lexuz_act_ru.html").read_text()

BASE = {
    "title": "т", "nature": "obligation", "type": "import",
    "category": "Оценка соответствия, декларация и сертификация", "summary": "с",
    "legal_quote_ru": "Продукция, включённая в перечень, подлежит обязательному "
                      "подтверждению соответствия в установленном порядке.",
    "act": {"name": "ЗРУ-819", "number": "819", "date": "2023-04-05",
            "lexuz_url": "https://lex.uz/docs/-6445145"},
    "unit": "ст. 14", "edition_date": None,
    "scope": {"level": "all"}, "addressees": ["importer"], "agency": None,
    "how_to": [], "documents": [], "sanction": None,
    "discovered_via": "domain", "needs_review": False,
}


def req(**over):
    return ProductRequirement.model_validate({**BASE, **over})


def client(tmp_path, html=HTML):
    return LexuzClient(cache_dir=tmp_path, fetcher=lambda url: html)


def test_gate_passes(tmp_path):
    r = verify_item(req(), client(tmp_path), llm=None)
    assert r.ok and r.doc_id == "-6445145" and r.ref == "art.14" and r.confidence >= 0.85


def test_needs_review_short_circuits(tmp_path):
    r = verify_item(req(needs_review=True), client(tmp_path), llm=None)
    assert not r.ok and r.reason == "needs_review_from_report"


def test_act_not_found(tmp_path):
    r = verify_item(req(act={"lexuz_url": None}), client(tmp_path), llm=None)
    assert not r.ok and r.reason == "act_not_found"


def test_unit_not_found(tmp_path):
    r = verify_item(req(unit="ст. 99"), client(tmp_path), llm=None)
    assert not r.ok and r.reason == "unit_not_found"


def test_quote_mismatch(tmp_path):
    r = verify_item(req(legal_quote_ru="совершенно другой текст про налоги и пошлины " * 3),
                    client(tmp_path), llm=None)
    assert not r.ok and r.reason == "quote_mismatch"


def test_repealed(tmp_path):
    html = "<p>Документ утратил силу. " + " и в на или" * 30 + "</p>"
    r = verify_item(req(), client(tmp_path, html), llm=None)
    assert not r.ok and r.reason == "act_repealed"


def test_uz_only(tmp_path):
    html = "<p>Ushbu hujjat faqat o'zbek tilida mavjud. Modda 14. Matn.</p>"
    r = verify_item(req(), client(tmp_path, html), llm=None)
    assert not r.ok and r.reason == "uz_only_act"


def test_unreachable(tmp_path):
    def boom(url):
        raise LexuzUnreachable("down")
    lex = LexuzClient(cache_dir=tmp_path, fetcher=boom)
    r = verify_item(req(), lex, llm=None)
    assert not r.ok and r.reason == "lexuz_unreachable"


UZ_ROW = ("Инфузория ерлари, цемент 2512 00 000 0, 2523 буюмлар учун ишлатиладиган "
          "маҳсулотлар рўйхати мувофиқлик сертификати расмийлаштирилиши лозим")
UZ_HTML = "<p>4-ИЛОВА Мувофиқлик сертификати 9. " + UZ_ROW + "</p><p>10. кейинги банд</p>"


def test_uz_branch_verifies_uz_quote_on_uz_only_page(tmp_path):
    # UZ-страница + legal_quote_uz → сверка проходит с penalty 0.95
    r = verify_item(req(legal_quote_uz=UZ_ROW, unit="прил. № 4, строка 9",
                        legal_quote_ru=None),
                    client(tmp_path, UZ_HTML), llm=None)
    assert r.ok and r.confidence <= 0.95 and r.ref == "app4/row9"


def test_uz_branch_without_uz_quote_still_review(tmp_path):
    r = verify_item(req(unit="прил. № 4, строка 9"), client(tmp_path, UZ_HTML), llm=None)
    assert not r.ok and r.reason == "uz_only_act"


def test_verify_url_checks_alt_page_but_keeps_canonical_doc_id(tmp_path):
    # verify_url указывает на UZ-версию; дедуп-ключ остаётся от act.lexuz_url
    calls = []
    def fetcher(url):
        calls.append(url)
        return UZ_HTML
    lex = LexuzClient(cache_dir=tmp_path, fetcher=fetcher)
    r = verify_item(req(verify_url="https://lex.uz/docs/5249376",
                        legal_quote_uz=UZ_ROW, unit="прил. № 4, строка 9"),
                    lex, llm=None)
    assert r.ok and r.doc_id == "-6445145"
    assert any("5249376" in u for u in calls)
