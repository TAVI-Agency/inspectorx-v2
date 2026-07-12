from pathlib import Path

from importer.evalharness import (Agreement, PRODUCT_SECTIONS, cross_agreement,
                                  requirement_key, score_report)
from importer.models import ActRef, ProductRequirement, ProductScope

FIX = Path(__file__).parent / "fixtures"


def _req(**over):
    base = dict(
        title="t", nature="obligation", summary="s",
        act=ActRef(lexuz_url="https://lex.uz/docs/123456"),
        unit="ст. 5", type="import", category="Налоги и платежи",
        scope=ProductScope(level="this_code"),
    )
    base.update(over)
    return ProductRequirement.model_validate(base)


def test_requirement_key_matches_dedup_canon():
    assert requirement_key(_req()) == "lexuz:123456/art.5"
    # знак минуса — часть doc_id (урок: /docs/-N и /docs/N — разные документы)
    assert requirement_key(
        _req(act=ActRef(lexuz_url="https://lex.uz/docs/-654321"))) == "lexuz:-654321/art.5"
    # есть акт, но unit не распознан → ключ с '?' (для agreement совпасть не сможет
    # с конкретным пунктом, но сам акт учитывается)
    assert requirement_key(_req(unit=None)) == "lexuz:123456/?"
    # нет lex.uz-ссылки → ключа нет
    assert requirement_key(_req(act=ActRef(name="без ссылки"))) is None


def test_score_report_fixture(tmp_path):
    src = FIX / "report_product_ok.md"
    path = tmp_path / "product--cement--claude.md"
    path.write_text(src.read_text())
    score = score_report(path)
    assert score.schema_valid
    assert score.kind == "product"
    assert score.total == len([v for v in score.sections.values() if v]) or score.total >= 1
    assert set(score.sections) >= set(PRODUCT_SECTIONS)
    assert 0.0 < score.section_coverage <= 1.0
    assert score.fields.complete <= score.total
    assert score.needs_review_rate <= 1.0


def test_score_report_bad_filename(tmp_path):
    path = tmp_path / "cement.md"
    path.write_text("# нет JSON")
    score = score_report(path)
    assert not score.schema_valid
    assert score.parse_error


def test_score_report_no_json(tmp_path):
    path = tmp_path / "product--cement--claude.md"
    path.write_text("# отчёт без JSON-блока")
    score = score_report(path)
    assert not score.schema_valid
    assert score.parse_error


def test_agreement_jaccard():
    agr = Agreement(common=2, only_a=1, only_b=1)
    assert agr.jaccard == 0.5


def test_cross_agreement_sets(tmp_path):
    src = (FIX / "report_product_ok.md").read_text()
    p1 = tmp_path / "product--cement--claude.md"
    p2 = tmp_path / "product--cement--chatgpt.md"
    p1.write_text(src)
    p2.write_text(src)
    s1, s2 = score_report(p1), score_report(p2)
    agr = cross_agreement(s1, s2)
    # идентичные отчёты полностью совпадают по ключам
    assert agr.only_a == agr.only_b == 0
    assert agr.jaccard == (1.0 if s1.keys else 0.0)
