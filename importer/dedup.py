"""Глобальный дедуп по ключу акт+пункт. Ложная склейка хуже дубля: сомнение → review."""
import re


def external_key(doc_id: str, ref: str) -> str:
    return f"lexuz:{doc_id}/{ref}"


def _first(resp):
    return resp.data[0] if resp.data else None


def find_existing(ix, key: str):
    return _first(ix.table("requirements").select("*")
                  .eq("external_key", key).limit(1).execute())


def _norm_article(article: str | None) -> str:
    return re.sub(r"\s+", "", (article or "").lower())


def sanctions_conflict(existing_sanctions: list[dict], new_sanction: dict | None) -> bool:
    if not new_sanction or not new_sanction.get("article"):
        return False
    new_art = _norm_article(new_sanction["article"])
    new_amount = (new_sanction.get("fine_bru") or "").strip().lower()
    for s in existing_sanctions:
        if _norm_article(s.get("article")) == new_art:
            old_amount = (s.get("amount") or "").strip().lower()
            if old_amount and new_amount and old_amount != new_amount:
                return True
    return False


def merge_requirement(ix, existing: dict, new_scope_rows, new_sanction, import_item_id) -> str:
    req_id = existing["id"]

    details = _first(ix.table("requirement_details").select("*")
                     .eq("requirement_id", req_id).eq("lang", "ru").limit(1).execute())
    old_sanctions = (details or {}).get("sanctions") or []
    if sanctions_conflict(old_sanctions, new_sanction):
        return "conflict"

    current = ix.table("requirement_applicability").select("*") \
        .eq("requirement_id", req_id).execute().data
    has_all = any(r["scope"] in ("all_products", "all_services") for r in current)
    present = {(r["scope"], r.get("code")) for r in current}
    if not has_all:
        for scope, code in new_scope_rows:
            if (scope, code) not in present:
                ix.table("requirement_applicability").insert(
                    {"requirement_id": req_id, "scope": scope, "code": code}).execute()
                present.add((scope, code))

    if details is not None and new_sanction and new_sanction.get("article"):
        arts = {_norm_article(s.get("article")) for s in old_sanctions}
        if _norm_article(new_sanction["article"]) not in arts:
            merged = old_sanctions + [{"amount": new_sanction.get("fine_bru"),
                                       "article": new_sanction.get("article"),
                                       "extra": new_sanction.get("extra")}]
            ix.table("requirement_details").update({"sanctions": merged}) \
                .eq("requirement_id", req_id).eq("lang", "ru").execute()

    src = _first(ix.table("requirement_sources").select("*")
                 .eq("requirement_id", req_id)
                 .eq("import_item_id", import_item_id).limit(1).execute())
    if src is None:
        ix.table("requirement_sources").insert(
            {"requirement_id": req_id, "import_item_id": import_item_id}).execute()
    return "merged"
