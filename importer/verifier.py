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
    verified_lang: str | None = None      # "uz" — канон, "ru" — переходный режим
    uz_backfill_needed: bool = False      # карточку надо добить UZ-цитатой (фаза 3)
    uz_doc_id: str | None = None          # doc_id узбекской версии, если найден


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

    # UZ-first (фаза 1, спека 2026-07-16): канон — узбекская цитата против
    # узбекской версии акта (у неё СВОЙ doc_id, ищем по шапке страницы).
    # RU-сверка — вторичная (penalty 0.95) + флаг добивки для фазы 3.
    quote = None
    penalty = 1.0
    verified_lang = None
    uz_backfill = False
    uz_doc_id = None
    page = html

    if getattr(req, "verify_url", None):
        # Явный оверрайд страницы сверки из отчёта (прежнее поведение).
        verify_doc = lexuz_doc_id(req.verify_url)
        if not verify_doc:
            return _review("act_not_found", f"verify_url не lex.uz: {req.verify_url!r}",
                           doc_id=doc_id)
        try:
            page = lexuz.fetch(verify_doc)
        except LexuzUnreachable as e:
            return _review("lexuz_unreachable", str(e), doc_id=doc_id)
        if getattr(req, "legal_quote_uz", None):
            quote, verified_lang, uz_doc_id = req.legal_quote_uz, "uz", verify_doc
        else:
            quote, verified_lang, uz_backfill = req.legal_quote_ru, "ru", True
        penalty = 0.95  # страница указана отчётом, не подтверждена шапкой акта
    elif getattr(req, "legal_quote_uz", None):
        quote, verified_lang = req.legal_quote_uz, "uz"
        if LexuzClient.is_russian(html):
            versions = LexuzClient.language_versions(html)
            script = LexuzClient.quote_script(quote)
            uz_doc_id = (versions.get(f"uz_{script}")
                         or versions.get("uz_cyr") or versions.get("uz_lat"))
            if uz_doc_id is None:
                return _review("uz_version_not_found",
                               "на RU-странице нет ссылки на UZ-версию акта",
                               doc_id=doc_id)
            try:
                page = lexuz.fetch(uz_doc_id)
            except LexuzUnreachable as e:
                return _review("lexuz_unreachable", str(e), doc_id=doc_id)
        else:
            # страница сама UZ → она и есть UZ-версия акта
            uz_doc_id = doc_id
        # penalty остаётся 1.0 (канон)
    elif not LexuzClient.is_russian(html):
        return _review("uz_only_act",
                       "официального RU-текста нет и нет legal_quote_uz для UZ-сверки",
                       doc_id=doc_id)
    else:
        # Переходный режим: только RU-цитата против RU-страницы.
        quote, verified_lang, uz_backfill = req.legal_quote_ru, "ru", True
        penalty = 0.95

    ref = parse_unit_ref(req.unit)
    if ref is None:
        return _review("unit_not_found", f"unit не распознан: {req.unit!r}", doc_id=doc_id)

    paragraph = LexuzClient.find_paragraph(page, ref)
    if paragraph is None:
        if ref.startswith(("art.", "p.")):
            return _review("unit_not_found", f"пункт {ref} не найден в акте",
                           doc_id=doc_id, ref=ref)
        paragraph = LexuzClient.page_text(page)  # перечни: сверка по всей странице (v1)
        penalty *= 0.9

    if not quote:
        return _review("quote_missing", "нет legal_quote_ru/uz", doc_id=doc_id, ref=ref)

    score = fuzz.partial_ratio(quote.lower(), paragraph.lower()) / 100.0
    confidence = round(score * penalty, 2)
    extra = {"verified_lang": verified_lang, "uz_backfill_needed": uz_backfill,
             "uz_doc_id": uz_doc_id}
    if score >= 0.85:
        return GateResult(ok=True, doc_id=doc_id, ref=ref, confidence=confidence,
                          paragraph_text=paragraph[:4000], **extra)
    if score >= 0.60 and llm is not None and llm.same_meaning(quote, paragraph[:6000]):
        return GateResult(ok=True, doc_id=doc_id, ref=ref, confidence=confidence,
                          paragraph_text=paragraph[:4000], **extra)
    return _review("quote_mismatch", f"fuzzy={score:.2f}", doc_id=doc_id, ref=ref,
                   confidence=confidence)
