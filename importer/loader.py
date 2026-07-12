"""Запись результатов в Supabase Inspector X: staging + основные таблицы витрины."""
from datetime import datetime, timezone

from importer.dedup import external_key
from importer.mappings import (STAGE_TO_CODE, map_addressees, map_category, map_nature,
                               map_operation, map_product_scope, map_service_scope)


def _first(resp):
    return resp.data[0] if resp.data else None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Loader:
    def __init__(self, ix, domains: dict):
        self.ix = ix
        self.domains = domains

    def start_run(self, rf, raw_json, gray_zones) -> str:
        existing = _first(self.ix.table("import_runs").select("*")
                          .eq("file_hash", rf.file_hash).limit(1).execute())
        if existing:
            self.ix.table("import_items").delete().eq("run_id", existing["id"]).execute()
            return existing["id"]
        row = _first(self.ix.table("import_runs").insert({
            "file_name": rf.path.name, "file_hash": rf.file_hash,
            "subject_kind": rf.kind, "subject_slug": rf.slug, "model": rf.model,
            "status": "parsed", "raw_json": raw_json, "gray_zones": gray_zones,
        }).execute())
        return row["id"]

    def upsert_subject(self, report) -> None:
        if hasattr(report, "product"):
            p = report.product
            if not p.hs_code:
                return
            if _first(self.ix.table("products").select("id")
                      .eq("hs_code", p.hs_code).limit(1).execute()):
                return
            self.ix.table("products").insert(
                {"hs_code": p.hs_code, "name_ru": p.name}).execute()
        else:
            s = report.service
            if _first(self.ix.table("services").select("id")
                      .eq("oked_code", s.okved).limit(1).execute()):
                return
            self.ix.table("services").insert(
                {"oked_code": s.okved, "name_ru": s.name}).execute()

    def save_item(self, run_id, idx, req, status, *, review_reason=None,
                  review_detail=None, requirement_id=None) -> str:
        row = _first(self.ix.table("import_items").insert({
            "run_id": run_id, "idx": idx, "raw": req.model_dump(mode="json"),
            "status": status, "review_reason": review_reason,
            "review_detail": review_detail, "requirement_id": requirement_id,
        }).execute())
        return row["id"]

    def load_requirement(self, req, kind, gate, act_row, paragraph_row,
                         subject, stage_ids: dict) -> str:
        base = {
            "status": "published", "trust_label": "validated", "origin": "ai_pipeline",
            "deontic": map_nature(req.nature),
            "operation": map_operation(kind, req),
            "addressee_roles": map_addressees(req.addressees),
            "confidence_score": gate.confidence,
            "external_key": external_key(gate.doc_id, gate.ref),
            "published_at": _now(),
        }
        if kind == "product":
            base["requirement_category"] = map_category(req.category)
            scope_rows = map_product_scope(
                req.scope, subject.hs_code,
                {**self.domains, "_domain": subject.domain or ""})
        else:
            base["lifecycle_stage_id"] = stage_ids.get(STAGE_TO_CODE[req.stage])
            scope_rows = map_service_scope(req.scope, subject.okved)

        req_row = _first(self.ix.table("requirements").insert(base).execute())
        req_id = req_row["id"]

        sanction = req.sanction
        self.ix.table("requirement_contents").insert({
            "requirement_id": req_id, "lang": "ru", "title": req.title,
            "sanction_summary": (f"{sanction.article}: {sanction.fine_bru}"
                                 if sanction and sanction.article else None),
        }).execute()
        self.ix.table("requirement_details").insert({
            "requirement_id": req_id, "lang": "ru", "description": req.summary,
            "how_to_comply": [{"step": h.step, "deadline": h.deadline,
                               "cost": h.fee or h.cost} for h in req.how_to],
            "documents": [{"name": d.name, "where_to_get": d.where} for d in req.documents],
            "sanctions": ([{"amount": sanction.fine_bru, "article": sanction.article,
                            "extra": sanction.extra}] if sanction and sanction.article else []),
        }).execute()
        self.ix.table("requirement_citations").insert({
            "requirement_id": req_id, "paragraph_id": paragraph_row["id"],
            "is_primary": True, "sort_order": 0,
        }).execute()
        for scope, code in scope_rows:
            self.ix.table("requirement_applicability").insert({
                "requirement_id": req_id, "scope": scope, "code": code}).execute()
        return req_id

    def finalize_run(self, run_id, status, counters, error=None) -> None:
        self.ix.table("import_runs").update({
            "status": status, "error": error,
            "loaded_count": counters.get("loaded", 0),
            "merged_count": counters.get("merged", 0),
            "review_count": counters.get("review", 0),
        }).eq("id", run_id).execute()
