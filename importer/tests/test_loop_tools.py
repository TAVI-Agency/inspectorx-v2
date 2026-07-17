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
