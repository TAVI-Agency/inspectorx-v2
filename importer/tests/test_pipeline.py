from pathlib import Path
from unittest.mock import patch

from importer.lexuz import LexuzClient
from importer.pipeline import run_import
from importer.tests.fakes import FakeClient
from importer.tests.test_verifier import UZ_QUOTE_CYR, routed_client
from importer.verifier import GateResult

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


# Инвариант pipeline.py: verbatim_uz в act_paragraphs пишется ТОЛЬКО когда гейт
# подтвердил цитату по узбекскому тексту (gate.verified_lang == "uz"). Непроверенный
# UZ-текст не должен попадать в библиотеку оригиналов — это шов между verify_item
# и ensure_paragraph, не покрытый ни одним другим тестом (см. pipeline.py:97).

def test_e2e_uz_verified_quote_lands_in_act_paragraphs(tmp_path):
    # UZ-цитата + RU-страница с шапкой, ведущей на UZ-версию по doc_id → гейт
    # сверяет по узбекскому тексту (verified_lang == "uz"), и verbatim_uz заполняется.
    report = (FIX / "report_product_ok.md").read_text()
    report = report.replace(
        '"legal_quote_ru": "продукция подлежит обязательному подтверждению соответствия",',
        '"legal_quote_ru": "Продукция, включённая в перечень, подлежит обязательному '
        'подтверждению соответствия в установленном порядке.", '
        f'"legal_quote_uz": "{UZ_QUOTE_CYR}",')
    path = tmp_path / "product--uz--claude.md"
    path.write_text(report)
    lexuz = routed_client(tmp_path)
    ix = make_ix()
    s = run_import(path, ix, jb=None, lexuz=lexuz, llm=None,
                   queue_path=tmp_path / "q.jsonl")
    assert (s.loaded, s.merged, s.review) == (1, 0, 0)
    assert ix.store["act_paragraphs"][0]["verbatim_uz"] == UZ_QUOTE_CYR


def test_e2e_ru_fallback_quote_leaves_verbatim_uz_none(tmp_path):
    # Только RU-цитата, страница без шапки языков → гейт верифицирует по-русски
    # (verified_lang == "ru"), непроверенный UZ-текст в library не попадает.
    path, lexuz = prepare(tmp_path)
    ix = make_ix()
    s = run_import(path, ix, jb=None, lexuz=lexuz, llm=None,
                   queue_path=tmp_path / "q.jsonl")
    assert (s.loaded, s.merged, s.review) == (1, 0, 0)
    assert ix.store["act_paragraphs"][0]["verbatim_uz"] is None


def test_e2e_ru_verified_gate_never_leaks_unverified_uz_quote(tmp_path):
    # Более жёсткая версия негативной ветки: в отчёте ЕСТЬ legal_quote_uz, но гейт
    # (реальный или, как здесь, подконтрольный) вернул verified_lang == "ru" — т.е.
    # узбекский текст НЕ был подтверждён по узбекской версии акта. Это отличает
    # "verified_lang == 'uz'" от "req.legal_quote_uz is not None": даже если
    # условие в pipeline.py вообще уберут (всегда прокидывать req.legal_quote_uz),
    # предыдущие два теста этого не поймают, т.к. в них при verified_lang == "ru"
    # поле legal_quote_uz и так пусто. Здесь оно намеренно непустое.
    report = (FIX / "report_product_ok.md").read_text()
    report = report.replace(
        '"legal_quote_ru": "продукция подлежит обязательному подтверждению соответствия",',
        '"legal_quote_ru": "Продукция, включённая в перечень, подлежит обязательному '
        'подтверждению соответствия в установленном порядке.", '
        f'"legal_quote_uz": "{UZ_QUOTE_CYR}",')
    path = tmp_path / "product--gate-ru--claude.md"
    path.write_text(report)
    lexuz = routed_client(tmp_path)
    ix = make_ix()

    fake_gate = GateResult(ok=True, doc_id="-6445145", ref="art.14", confidence=0.95,
                           paragraph_text="текст статьи", verified_lang="ru",
                           uz_backfill_needed=True)
    with patch("importer.pipeline.verify_item", return_value=fake_gate):
        s = run_import(path, ix, jb=None, lexuz=lexuz, llm=None,
                       queue_path=tmp_path / "q.jsonl")
    assert (s.loaded, s.merged, s.review) == (1, 0, 0)
    assert ix.store["act_paragraphs"][0]["verbatim_uz"] is None
