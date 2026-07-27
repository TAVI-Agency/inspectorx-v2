"""Оркестрация: parse → resolve → verify → dedup → load для одного файла отчёта."""
import sys
import traceback
from dataclasses import dataclass, field
from pathlib import Path

from importer.dedup import external_key, find_existing, merge_requirement
from importer.loader import Loader
from importer.mappings import (MappingError, load_domains, map_product_scope,
                               map_service_scope)
from importer.parser import ReportParseError, load_report_file, extract_gray_zones, parse_report
from importer.resolver import ensure_paragraph, resolve_act
from importer.translator import translate_card_fields
from importer.verifier import verify_item


@dataclass
class RunSummary:
    run_id: str | None
    loaded: int = 0
    merged: int = 0
    review: int = 0
    reasons: dict = field(default_factory=dict)
    dry_run: bool = False


def _scope_rows(req, kind, subject, domains):
    if kind == "product":
        return map_product_scope(req.scope, subject.hs_code,
                                 {**domains, "_domain": subject.domain or ""})
    return map_service_scope(req.scope, subject.okved)


def run_import(path: Path, ix, jb, lexuz, llm, dry_run: bool = False,
               queue_path: Path = Path("research/act_queue.jsonl")) -> RunSummary:
    rf = load_report_file(path)
    domains = load_domains()
    report = parse_report(rf, llm=llm)  # ReportParseError → наружу, run failed целиком
    subject = report.product if rf.kind == "product" else report.service
    gray = extract_gray_zones(rf.markdown)

    summary = RunSummary(run_id=None, dry_run=dry_run)
    loader = None
    stage_ids = {}
    if not dry_run:
        loader = Loader(ix, domains)
        summary.run_id = loader.start_run(rf, report.model_dump(mode="json"), gray)
        loader.upsert_subject(report)
        stage_ids = {r["code"]: r["id"] for r in
                     ix.table("lifecycle_stages").select("*").execute().data}

    def mark_review(idx, req, reason, detail):
        summary.review += 1
        summary.reasons[reason] = summary.reasons.get(reason, 0) + 1
        if loader:
            loader.save_item(summary.run_id, idx, req, "review",
                             review_reason=reason, review_detail=detail)

    for idx, req in enumerate(report.requirements):
        try:
            gate = verify_item(req, lexuz, llm)
            if not gate.ok:
                mark_review(idx, req, gate.reason, gate.detail)
                continue
            try:
                scope_rows = _scope_rows(req, rf.kind, subject, domains)
            except MappingError as e:
                mark_review(idx, req, e.reason, e.detail)
                continue

            key = external_key(gate.doc_id, gate.ref)
            if dry_run:
                summary.loaded += 1
                print(f"  [dry] {req.title[:60]} → {key}")
                continue

            existing = find_existing(ix, key)
            if existing:
                item_id = loader.save_item(summary.run_id, idx, req, "merged",
                                           requirement_id=existing["id"])
                sanction = req.sanction.model_dump() if req.sanction else None
                status = merge_requirement(ix, existing, scope_rows, sanction, item_id)
                if status == "conflict":
                    ix.table("import_items").update(
                        {"status": "review", "review_reason": "cross_model_conflict",
                         "review_detail": "разные данные на одном ключе акт+пункт",
                         "requirement_id": existing["id"]}).eq("id", item_id).execute()
                    summary.review += 1
                    summary.reasons["cross_model_conflict"] = \
                        summary.reasons.get("cross_model_conflict", 0) + 1
                else:
                    summary.merged += 1
                continue

            act_row = resolve_act(req.act, gate.doc_id, jb, ix, queue_path)
            paragraph_row = ensure_paragraph(
                ix, act_row, gate.ref, req.legal_quote_ru, gate.doc_id,
                quote_uz=(req.legal_quote_uz if gate.verified_lang == "uz" else None))
            # Фаза 2: UZ-контент публикуется с производным RU-переводом витринных
            # полей; перевод не удался → честная UZ-only публикация (спека §2).
            ru_tr = (translate_card_fields(req, llm)
                     if getattr(req, "content_lang", "ru") == "uz" else None)
            req_id = loader.load_requirement(req, rf.kind, gate, act_row,
                                             paragraph_row, subject, stage_ids,
                                             ru_translation=ru_tr)
            item_id = loader.save_item(summary.run_id, idx, req, "loaded",
                                       requirement_id=req_id)
            ix.table("requirement_sources").insert(
                {"requirement_id": req_id, "import_item_id": item_id}).execute()
            summary.loaded += 1
        except Exception as e:  # ошибка item не роняет прогон
            traceback.print_exc(file=sys.stderr)
            mark_review(idx, req, "internal_error", str(e)[:500])

    if loader:
        loader.finalize_run(summary.run_id, "loaded",
                            {"loaded": summary.loaded, "merged": summary.merged,
                             "review": summary.review})
    return summary
