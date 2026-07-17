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
