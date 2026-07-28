"""Тесты инструментов research-loop (фолоу-апы фазы 1 UZ-first)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "research-loop"))

from pass2_autoclear import should_clear  # noqa: E402

from importer.verifier import GateResult  # noqa: E402


def gate(**kw):
    base = dict(ok=True, score=0.9, confidence=0.86, matched_scope="paragraph")
    base.update(kw)
    return GateResult(**base)


def test_clear_uses_raw_score_not_penalized_confidence():
    # RU-item: score 0.87, confidence 0.83 (×0.95) — по старому правилу резался,
    # по новому (score) — чистится: языковой штраф не делает правило строже.
    assert should_clear(gate(score=0.87, confidence=0.83))


def test_clear_rejects_below_verbatim_threshold():
    assert not should_clear(gate(score=0.84, confidence=0.84))


def test_clear_page_scope_needs_near_exact():
    assert not should_clear(gate(score=0.9, matched_scope="page"))
    assert should_clear(gate(score=0.96, matched_scope="page"))


def test_clear_requires_gate_ok_and_score():
    assert not should_clear(gate(ok=False, reason="quote_mismatch"))
    assert not should_clear(gate(score=None))


def test_requeue_paragraph_seam_matches_pipeline():
    """requeue_review передаёт quote_uz в ensure_paragraph только при verified_lang=uz
    и не кладёт UZ-цитату в verbatim_ru (зеркало pipeline.py)."""
    import ast
    src = (Path(__file__).resolve().parents[2] / "research-loop" /
           "requeue_review.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    calls = [n for n in ast.walk(tree)
             if isinstance(n, ast.Call)
             and getattr(n.func, "id", None) == "ensure_paragraph"]
    assert len(calls) == 1
    call = ast.unparse(calls[0])
    assert "quote_uz=" in call
    assert "legal_quote_ru or" not in call  # UZ-текст не течёт в verbatim_ru


# ---------------------------------------------------------------------------
# Добивка библиотеки узбекских оригиналов (backfill_verbatim_uz)
# ---------------------------------------------------------------------------

from backfill_verbatim_uz import backfill, is_machine_ref, pick_uz_doc, plan  # noqa: E402

from importer.tests.fakes import FakeClient  # noqa: E402
from importer.tests.test_verifier import routed_client  # noqa: E402


def test_machine_ref_accepts_canonical_forms():
    for ref in ("art.14", "p.20", "ch.3", "app1/p.5", "app4/row9", "app1-3"):
        assert is_machine_ref(ref), ref


def test_machine_ref_rejects_legacy_prose():
    # 118 из 200 параграфов пришли переносом v1 с текстовой ссылкой — их
    # нельзя найти на странице акта машинно, добивка обязана их пропустить.
    for ref in ("обязательная маркировка", "п. 36", "предельные наценки", ""):
        assert not is_machine_ref(ref), ref


def test_pick_uz_doc_prefers_cyrillic():
    assert pick_uz_doc({"uz_cyr": "111", "uz_lat": "-111"}) == "111"
    assert pick_uz_doc({"uz_lat": "-111"}) == "-111"
    assert pick_uz_doc({}) is None


def test_plan_splits_candidates_from_skips():
    acts = {"a1": {"id": "a1", "url": "https://lex.uz/ru/docs/-6445145"},
            "a2": {"id": "a2", "url": None}}
    paras = [
        {"id": "p1", "act_id": "a1", "paragraph_ref": "art.14", "verbatim_uz": None},
        {"id": "p2", "act_id": "a1", "paragraph_ref": "п. 36", "verbatim_uz": None},
        {"id": "p3", "act_id": "a2", "paragraph_ref": "art.5", "verbatim_uz": None,
         "deep_link_url": None},
        {"id": "p4", "act_id": "a1", "paragraph_ref": "art.9", "verbatim_uz": "бор"},
    ]
    cand, skipped = plan(paras, acts)
    assert [c["id"] for c in cand] == ["p1"]
    assert skipped == {"legacy_ref": 1, "no_lexuz_doc": 1, "already_filled": 1}


def test_backfill_writes_original_only_with_apply(tmp_path):
    acts = {"a1": {"id": "a1", "url": "https://lex.uz/ru/docs/-6445145"}}
    row = {"id": "p1", "act_id": "a1", "paragraph_ref": "art.14", "verbatim_uz": None}
    ix = FakeClient({"act_paragraphs": [row]})

    dry = backfill(ix, routed_client(tmp_path), [row], acts, apply=False)
    assert dry["filled"] == 1
    assert ix.store["act_paragraphs"][0]["verbatim_uz"] is None  # прогон всухую

    done = backfill(ix, routed_client(tmp_path), [row], acts, apply=True)
    assert done["filled"] == 1
    written = ix.store["act_paragraphs"][0]["verbatim_uz"]
    assert written and "14-модда" in written


def test_backfill_reports_missing_uz_version(tmp_path):
    # RU-страница без ссылок на узбекскую версию: добивать нечем, но прогон
    # обязан это назвать, а не молча пропустить.
    from importer.lexuz import LexuzClient
    plain_ru = (Path(__file__).parent / "fixtures" / "lexuz_act_ru.html").read_text()
    lexuz = LexuzClient(cache_dir=tmp_path, fetcher=lambda url: plain_ru)
    acts = {"a1": {"id": "a1", "url": "https://lex.uz/ru/docs/-6445145"}}
    row = {"id": "p1", "act_id": "a1", "paragraph_ref": "art.14", "verbatim_uz": None}
    ix = FakeClient({"act_paragraphs": [row]})

    res = backfill(ix, lexuz, [row], acts, apply=True)
    assert res["filled"] == 0 and res["uz_version_not_found"] == 1
    assert ix.store["act_paragraphs"][0]["verbatim_uz"] is None
