"""Верификационный гейт: любое сомнение → review, не в БД (правило хендоффа)."""
from dataclasses import dataclass

from rapidfuzz import fuzz

from importer.lexuz import LexuzClient, LexuzUnreachable
from importer.refs import lexuz_doc_id, parse_unit_ref


@dataclass
class GateResult:
    ok: bool
    reason: str | None = None
    detail: str | None = None
    doc_id: str | None = None
    ref: str | None = None
    confidence: float | None = None
    paragraph_text: str | None = None


def _review(reason: str, detail: str = "", **kw) -> GateResult:
    return GateResult(ok=False, reason=reason, detail=detail, **kw)


def verify_item(req, lexuz: LexuzClient, llm) -> GateResult:
    if req.needs_review:
        return _review("needs_review_from_report", "помечено моделью в отчёте")

    doc_id = lexuz_doc_id(req.act.lexuz_url)
    if not doc_id:
        return _review("act_not_found", f"нет lex.uz-ссылки: {req.act.lexuz_url!r}")

    try:
        html = lexuz.fetch(doc_id)
    except LexuzUnreachable as e:
        return _review("lexuz_unreachable", str(e), doc_id=doc_id)

    if LexuzClient.is_repealed(html):
        return _review("act_repealed", "маркер «утратил силу» на странице", doc_id=doc_id)
    if not LexuzClient.is_russian(html):
        return _review("uz_only_act", "официального RU-текста нет (v1: ветка UZ не реализована)",
                       doc_id=doc_id)

    ref = parse_unit_ref(req.unit)
    if ref is None:
        return _review("unit_not_found", f"unit не распознан: {req.unit!r}", doc_id=doc_id)

    paragraph = LexuzClient.find_paragraph(html, ref)
    penalty = 1.0
    if paragraph is None:
        if ref.startswith(("art.", "p.")):
            return _review("unit_not_found", f"пункт {ref} не найден в акте",
                           doc_id=doc_id, ref=ref)
        paragraph = LexuzClient.page_text(html)  # перечни: сверка по всей странице (v1)
        penalty = 0.9

    if not req.legal_quote_ru:
        return _review("quote_missing", "нет legal_quote_ru", doc_id=doc_id, ref=ref)

    score = fuzz.partial_ratio(req.legal_quote_ru.lower(), paragraph.lower()) / 100.0
    confidence = round(score * penalty, 2)
    if score >= 0.85:
        return GateResult(ok=True, doc_id=doc_id, ref=ref,
                          confidence=confidence, paragraph_text=paragraph[:4000])
    if score >= 0.60 and llm is not None and llm.same_meaning(req.legal_quote_ru, paragraph[:6000]):
        return GateResult(ok=True, doc_id=doc_id, ref=ref,
                          confidence=confidence, paragraph_text=paragraph[:4000])
    return _review("quote_mismatch", f"fuzzy={score:.2f}", doc_id=doc_id, ref=ref,
                   confidence=confidence)
