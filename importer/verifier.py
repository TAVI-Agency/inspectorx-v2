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

    # UZ-ветка (решение 13.07.2026, класс фейла uz_only_act/33 needs_review):
    # если задан verify_url — сверяем по нему (UZ-страница акта с приложениями);
    # цитата — legal_quote_uz, если есть, иначе legal_quote_ru.
    quote = req.legal_quote_ru
    penalty = 1.0
    if getattr(req, "verify_url", None):
        verify_doc = lexuz_doc_id(req.verify_url)
        if not verify_doc:
            return _review("act_not_found", f"verify_url не lex.uz: {req.verify_url!r}",
                           doc_id=doc_id)
        try:
            html = lexuz.fetch(verify_doc)
        except LexuzUnreachable as e:
            return _review("lexuz_unreachable", str(e), doc_id=doc_id)
        if getattr(req, "legal_quote_uz", None):
            quote = req.legal_quote_uz
        penalty = 0.95  # сверка не по канонической RU-странице
    elif not LexuzClient.is_russian(html):
        if getattr(req, "legal_quote_uz", None):
            quote = req.legal_quote_uz
            penalty = 0.95
        else:
            return _review("uz_only_act",
                           "официального RU-текста нет и нет legal_quote_uz для UZ-сверки",
                           doc_id=doc_id)

    ref = parse_unit_ref(req.unit)
    if ref is None:
        return _review("unit_not_found", f"unit не распознан: {req.unit!r}", doc_id=doc_id)

    paragraph = LexuzClient.find_paragraph(html, ref)
    if paragraph is None:
        if ref.startswith(("art.", "p.")):
            return _review("unit_not_found", f"пункт {ref} не найден в акте",
                           doc_id=doc_id, ref=ref)
        paragraph = LexuzClient.page_text(html)  # перечни: сверка по всей странице (v1)
        penalty *= 0.9

    if not quote:
        return _review("quote_missing", "нет legal_quote_ru/uz", doc_id=doc_id, ref=ref)

    score = fuzz.partial_ratio(quote.lower(), paragraph.lower()) / 100.0
    confidence = round(score * penalty, 2)
    if score >= 0.85:
        return GateResult(ok=True, doc_id=doc_id, ref=ref,
                          confidence=confidence, paragraph_text=paragraph[:4000])
    if score >= 0.60 and llm is not None and llm.same_meaning(quote, paragraph[:6000]):
        return GateResult(ok=True, doc_id=doc_id, ref=ref,
                          confidence=confidence, paragraph_text=paragraph[:4000])
    return _review("quote_mismatch", f"fuzzy={score:.2f}", doc_id=doc_id, ref=ref,
                   confidence=confidence)
