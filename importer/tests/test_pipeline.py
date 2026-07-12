from pathlib import Path
from importer.lexuz import LexuzClient
from importer.pipeline import run_import
from importer.tests.fakes import FakeClient

FIX = Path(__file__).parent / "fixtures"
HTML = (FIX / "lexuz_act_ru.html").read_text()


def make_ix():
    return FakeClient({t: [] for t in
                       ("import_runs", "import_items", "products", "services", "acts",
                        "act_paragraphs", "requirements", "requirement_contents",
                        "requirement_details", "requirement_citations",
                        "requirement_applicability", "requirement_sources",
                        "lifecycle_stages")})


def prepare(tmp_path):
    report = (FIX / "report_product_ok.md").read_text()
    # цитата фикстуры отчёта должна совпадать со статьёй 14 фикстуры HTML
    report = report.replace(
        "продукция подлежит обязательному подтверждению соответствия",
        "Продукция, включённая в перечень, подлежит обязательному подтверждению соответствия")
    path = tmp_path / "product--cement--claude.md"
    path.write_text(report)
    lexuz = LexuzClient(cache_dir=tmp_path / "cache", fetcher=lambda url: HTML)
    return path, lexuz


def test_e2e_load(tmp_path):
    path, lexuz = prepare(tmp_path)
    ix = make_ix()
    s = run_import(path, ix, jb=None, lexuz=lexuz, llm=None,
                   queue_path=tmp_path / "q.jsonl")
    assert (s.loaded, s.merged, s.review) == (1, 0, 0)
    assert ix.store["requirements"][0]["external_key"] == "lexuz:-6445145/art.14"
    assert ix.store["import_runs"][0]["status"] == "loaded"
    assert ix.store["import_items"][0]["status"] == "loaded"


def test_e2e_rerun_merges_not_duplicates(tmp_path):
    path, lexuz = prepare(tmp_path)
    ix = make_ix()
    run_import(path, ix, None, lexuz, None, queue_path=tmp_path / "q.jsonl")
    s2 = run_import(path, ix, None, lexuz, None, queue_path=tmp_path / "q.jsonl")
    assert len(ix.store["requirements"]) == 1  # идемпотентность
    assert s2.merged == 1 and s2.loaded == 0


def test_e2e_dry_run_writes_nothing(tmp_path):
    path, lexuz = prepare(tmp_path)
    ix = make_ix()
    s = run_import(path, ix, None, lexuz, None, dry_run=True,
                   queue_path=tmp_path / "q.jsonl")
    assert s.loaded == 1 and s.run_id is None
    assert all(not rows for rows in ix.store.values())
