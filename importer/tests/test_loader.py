from importer.loader import Loader
from importer.models import ProductReport
from importer.parser import ReportFile
from importer.tests.fakes import FakeClient
from importer.tests.test_models import PRODUCT_JSON
from importer.verifier import GateResult
from pathlib import Path

RF = ReportFile(Path("product--cement--claude.md"), "product", "cement", "claude", "h" * 64, "md")
GATE = GateResult(ok=True, doc_id="6445145", ref="art.14", confidence=0.93)


def make_loader():
    ix = FakeClient({t: [] for t in
                     ("import_runs", "import_items", "products", "services", "requirements",
                      "requirement_contents", "requirement_details", "requirement_citations",
                      "requirement_applicability", "requirement_sources")})
    return Loader(ix, domains={"стройматериалы": ["25", "68"]}), ix


def test_start_run_idempotent():
    loader, ix = make_loader()
    run1 = loader.start_run(RF, PRODUCT_JSON, ["зона 1"])
    ix.store["import_items"].append({"id": "x", "run_id": run1, "idx": 0,
                                     "raw": {}, "status": "review"})
    run2 = loader.start_run(RF, PRODUCT_JSON, ["зона 1"])
    assert run1 == run2
    assert ix.store["import_items"] == []  # items пересозданы заново


def test_upsert_subject_product():
    loader, ix = make_loader()
    report = ProductReport.model_validate(PRODUCT_JSON)
    loader.upsert_subject(report)
    loader.upsert_subject(report)
    assert len(ix.store["products"]) == 1
    assert ix.store["products"][0]["hs_code"] == "2523290000"


def test_load_requirement_full():
    loader, ix = make_loader()
    report = ProductReport.model_validate(PRODUCT_JSON)
    req_id = loader.load_requirement(
        report.requirements[0], "product", GATE,
        act_row={"id": "act-1"}, paragraph_row={"id": "par-1"},
        subject=report.product, stage_ids={})
    r = ix.store["requirements"][0]
    assert r["status"] == "published" and r["trust_label"] == "validated"
    assert r["origin"] == "ai_pipeline" and r["external_key"] == "lexuz:6445145/art.14"
    assert r["requirement_category"] == "tbt"
    assert ix.store["requirement_contents"][0]["title"].startswith("Получить")
    assert ix.store["requirement_details"][0]["how_to_comply"][0]["step"] == "Подать заявку"
    assert ix.store["requirement_citations"][0] == {
        "id": "id-0", "requirement_id": req_id, "paragraph_id": "par-1",
        "is_primary": True, "sort_order": 0}
    assert ix.store["requirement_applicability"][0]["scope"] == "hs_prefix"


UZ_REQ = {
    "title": "Litsenziya olish", "nature": "obligation", "type": "product",
    "category": "прочее", "summary": "Faoliyat uchun litsenziya kerak",
    "legal_quote_uz": "modda matni", "act": {"name": "ЗРУ-819", "number": "819",
    "date": "2023-02-27", "lexuz_url": "https://lex.uz/docs/6392314"},
    "unit": "ст. 24", "scope": {"level": "all"}, "addressees": ["all"],
    "how_to": [{"step": "Ariza topshirish", "deadline": "10 kun"}],
    "documents": [{"name": "Guvohnoma"}],
    "sanction": {"article": "ст. 46", "fine_bru": "50%", "extra": "jarima"},
    "needs_review": False, "content_lang": "uz",
}


def test_load_uz_card_with_translation_writes_bilingual_rows():
    from importer.models import ProductRequirement
    loader, ix = make_loader()
    req = ProductRequirement.model_validate(UZ_REQ)
    loader.load_requirement(
        req, "product", GATE, act_row={"id": "act-1"}, paragraph_row={"id": "par-1"},
        subject=type("S", (), {"hs_code": None, "domain": None})(), stage_ids={},
        ru_translation={"title": "Получить лицензию", "summary": "Нужна лицензия",
                        "how_to_steps": ["Подать заявление"],
                        "documents": [{"name": "Свидетельство", "where": None}],
                        "sanction_extra": "штраф"})
    contents = {c["lang"]: c for c in ix.store["requirement_contents"]}
    details = {d["lang"]: d for d in ix.store["requirement_details"]}
    assert contents["uz"]["translation_origin"] == "verbatim"
    assert contents["uz"]["title"] == "Litsenziya olish"
    assert contents["ru"]["translation_origin"] == "machine"
    assert contents["ru"]["title"] == "Получить лицензию"
    assert details["uz"]["translation_origin"] == "verbatim"
    assert details["ru"]["translation_origin"] == "machine"
    # перевод шагов наследует deadline/cost от оригинала
    assert details["ru"]["how_to_comply"] == [
        {"step": "Подать заявление", "deadline": "10 kun", "cost": None}]
    assert details["ru"]["sanctions"][0]["extra"] == "штраф"


def test_load_uz_card_without_translation_is_uz_only():
    from importer.models import ProductRequirement
    loader, ix = make_loader()
    req = ProductRequirement.model_validate(UZ_REQ)
    loader.load_requirement(
        req, "product", GATE, act_row={"id": "act-1"}, paragraph_row={"id": "par-1"},
        subject=type("S", (), {"hs_code": None, "domain": None})(), stage_ids={})
    assert [c["lang"] for c in ix.store["requirement_contents"]] == ["uz"]
    assert [d["lang"] for d in ix.store["requirement_details"]] == ["uz"]


def test_load_ru_card_keeps_single_verbatim_row():
    # регрессия: русские DR-отчёты пишутся как раньше, но с origin='verbatim'
    loader, ix = make_loader()
    report = ProductReport.model_validate(PRODUCT_JSON)
    loader.load_requirement(
        report.requirements[0], "product", GATE,
        act_row={"id": "act-1"}, paragraph_row={"id": "par-1"},
        subject=report.product, stage_ids={})
    assert [c["lang"] for c in ix.store["requirement_contents"]] == ["ru"]
    assert ix.store["requirement_contents"][0]["translation_origin"] == "verbatim"
    assert ix.store["requirement_details"][0]["translation_origin"] == "verbatim"


def test_loader_writes_without_origin_until_migration_applied():
    # прод без миграции translation_origin → строки пишутся без поля, не падаем
    loader, ix = make_loader()
    loader._origin_supported = False
    report = ProductReport.model_validate(PRODUCT_JSON)
    loader.load_requirement(
        report.requirements[0], "product", GATE,
        act_row={"id": "act-1"}, paragraph_row={"id": "par-1"},
        subject=report.product, stage_ids={})
    assert "translation_origin" not in ix.store["requirement_contents"][0]
    assert "translation_origin" not in ix.store["requirement_details"][0]
