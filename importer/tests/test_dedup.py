from importer.dedup import external_key, find_existing, merge_requirement, sanctions_conflict
from importer.tests.fakes import FakeClient


def test_external_key():
    assert external_key("6445145", "art.14") == "lexuz:6445145/art.14"


def test_find_existing():
    ix = FakeClient({"requirements": [{"id": "r1", "external_key": "lexuz:1/art.2"}]})
    assert find_existing(ix, "lexuz:1/art.2")["id"] == "r1"
    assert find_existing(ix, "lexuz:1/art.3") is None


def test_sanctions_conflict_same_article_diff_fine():
    existing = [{"amount": "до 75 БРВ", "article": "ст. 186 КоАО", "extra": None}]
    assert sanctions_conflict(existing, {"article": "ст.186 КоАО", "fine_bru": "до 100 БРВ"})
    # другая статья = второй слой, не конфликт
    assert not sanctions_conflict(existing, {"article": "ст. 46 ЗРУ-819", "fine_bru": "50%"})
    # та же статья, тот же штраф — не конфликт
    assert not sanctions_conflict(existing, {"article": "ст. 186 КоАО", "fine_bru": "до 75 БРВ"})


def _store():
    return {
        "requirements": [{"id": "r1", "external_key": "lexuz:1/art.2"}],
        "requirement_applicability": [
            {"id": "a1", "requirement_id": "r1", "scope": "hs_code", "code": "2523290000"}],
        "requirement_details": [
            {"requirement_id": "r1", "lang": "ru",
             "sanctions": [{"amount": "до 75 БРВ", "article": "ст. 186 КоАО", "extra": None}]}],
        "requirement_sources": [],
    }


def test_merge_extends_scope_and_sources():
    ix = FakeClient(_store())
    status = merge_requirement(ix, {"id": "r1"}, [("hs_code", "3208101000")],
                               {"article": "ст. 46 ЗРУ-819", "fine_bru": "до 50%"}, "item-9")
    assert status == "merged"
    codes = {r["code"] for r in ix.store["requirement_applicability"]}
    assert codes == {"2523290000", "3208101000"}
    assert len(ix.store["requirement_details"][0]["sanctions"]) == 2
    assert ix.store["requirement_sources"][0]["import_item_id"] == "item-9"
    # идемпотентность
    merge_requirement(ix, {"id": "r1"}, [("hs_code", "3208101000")], None, "item-9")
    assert len(ix.store["requirement_applicability"]) == 2
    assert len(ix.store["requirement_sources"]) == 1


def test_merge_conflict():
    ix = FakeClient(_store())
    status = merge_requirement(ix, {"id": "r1"}, [],
                               {"article": "ст. 186 КоАО", "fine_bru": "до 500 БРВ"}, "item-9")
    assert status == "conflict"
    assert len(ix.store["requirement_details"][0]["sanctions"]) == 1  # ничего не записано


def test_canonical_details_prefers_verbatim_over_machine_and_legacy():
    from importer.dedup import _canonical_details
    uz = {"lang": "uz", "translation_origin": "verbatim"}
    ru_machine = {"lang": "ru", "translation_origin": "machine"}
    legacy_ru = {"lang": "ru", "translation_origin": None}
    assert _canonical_details([ru_machine, uz]) is uz
    assert _canonical_details([ru_machine, legacy_ru]) is legacy_ru  # легаси = verbatim
    assert _canonical_details([ru_machine]) is None  # машинный перевод каноном не бывает
    assert _canonical_details([]) is None
