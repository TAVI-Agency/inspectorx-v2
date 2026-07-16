"""Резолв акта: JurisBase (канон) → IX.acts (витрина) → очередь загрузки для скрейпера."""
import json
from pathlib import Path

# Имена колонок JurisBase acts — проверить разведкой перед живым прогоном (Task 14):
# python -c "from importer.db import jb_client; print(jb_client().table('acts').select('*').limit(1).execute().data)"
JB_ID_COLUMN = "id"
JB_URL_COLUMN = "source_url"


def _first(resp):
    return resp.data[0] if resp.data else None


def _queue_act(queue_path: Path, doc_id: str, act) -> None:
    queue_path.parent.mkdir(parents=True, exist_ok=True)
    if queue_path.exists():
        for line in queue_path.read_text(encoding="utf-8").splitlines():
            if json.loads(line).get("doc_id") == doc_id:
                return
    entry = {"doc_id": doc_id, "lexuz_url": act.lexuz_url, "name": act.name}
    with queue_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def _jb_lookup(jb, doc_id: str):
    if jb is None:
        return None
    try:
        resp = (jb.table("acts").select("*")
                .ilike(JB_URL_COLUMN, f"%{doc_id}%").limit(1).execute())
        row = _first(resp)
        if row and not row.get("is_stub", False) and row.get("status") == "published":
            return row
    except Exception:
        return None  # JurisBase недоступен — не блокируем гейт (решение: прямой fetch)
    return None


def resolve_act(act, doc_id: str, jb, ix, queue_path: Path) -> dict:
    jb_row = _jb_lookup(jb, doc_id)
    if jb_row is None:
        _queue_act(queue_path, doc_id, act)

    canonical_url = f"https://lex.uz/ru/docs/{doc_id}"  # doc_id уже со знаком
    if jb_row is not None:
        existing = _first(ix.table("acts").select("*")
                          .eq("jurisbase_act_id", str(jb_row[JB_ID_COLUMN])).limit(1).execute())
        if existing:
            return existing
    existing = _first(ix.table("acts").select("*")
                      .ilike("url", f"%{doc_id}%").limit(1).execute())
    if existing:
        return existing

    row = {
        "title": (jb_row or {}).get("title") or act.name or f"Акт lex.uz {doc_id}",
        "number": act.number,
        "url": canonical_url,
        "status": "active",
    }
    if jb_row is not None:
        row["jurisbase_act_id"] = str(jb_row[JB_ID_COLUMN])
    return _first(ix.table("acts").insert(row).execute())


def ensure_paragraph(ix, act_row: dict, ref: str, quote_ru: str | None, doc_id: str,
                     *, quote_uz: str | None = None) -> dict:
    existing = _first(ix.table("act_paragraphs").select("*")
                      .eq("act_id", act_row["id"]).eq("paragraph_ref", ref).limit(1).execute())
    if existing:
        if quote_uz and not existing.get("verbatim_uz"):
            # Библиотека оригиналов копится: досаживаем UZ-текст в старую строку.
            ix.table("act_paragraphs").update({"verbatim_uz": quote_uz}) \
                .eq("id", existing["id"]).execute()
            existing = {**existing, "verbatim_uz": quote_uz}
        return existing
    return _first(ix.table("act_paragraphs").insert({
        "act_id": act_row["id"],
        "paragraph_ref": ref,
        "verbatim_ru": quote_ru,
        "verbatim_uz": quote_uz,
        "deep_link_url": f"https://lex.uz/ru/docs/{doc_id}",
    }).execute())
