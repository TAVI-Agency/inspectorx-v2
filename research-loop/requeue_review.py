"""Ре-верификация review-очереди через гейт (луп, решение 13.07.2026).

Берёт items status=review/resolution=pending, применяет pass2-оверрайды из
research-loop/pass2-overrides.json (ключ — первые 8 символов item id), заново гонит
через verify_item (с UZ-веткой). Прошло → штатная загрузка лоадером (published/
validated), item → status loaded/merged + resolution='fixed'. Не прошло — остаётся
review (review_detail дописывается новой причиной, если она изменилась).

Запуск: .venv-importer/bin/python research-loop/requeue_review.py [--dry-run] [--llm]
(--llm включает claude -p same_meaning для пограничных цитат 0.60–0.85)
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from importer.db import ix_client, jb_client  # noqa: E402
from importer.dedup import external_key, find_existing, merge_requirement  # noqa: E402
from importer.lexuz import LexuzClient  # noqa: E402
from importer.loader import Loader  # noqa: E402
from importer.mappings import MappingError, load_domains  # noqa: E402
from importer.models import parse_report_json  # noqa: E402
from importer.resolver import ensure_paragraph, resolve_act  # noqa: E402
from importer.verifier import verify_item  # noqa: E402

OVERRIDES_PATH = Path(__file__).parent / "pass2-overrides.json"
QUEUE_PATH = Path("research/act_queue.jsonl")


def load_overrides() -> dict:
    if OVERRIDES_PATH.exists():
        return json.loads(OVERRIDES_PATH.read_text(encoding="utf-8"))
    return {}


def main(dry_run: bool = False, use_llm: bool = False):
    ix = ix_client()
    try:
        jb = jb_client()
    except RuntimeError:
        jb = None
    llm = None
    if use_llm:
        from importer.llm import LLM
        llm = LLM()
    lexuz = LexuzClient(cache_dir=Path("research/.cache/lexuz"))
    domains = load_domains()
    loader = Loader(ix, domains)
    overrides = load_overrides()

    runs = {r["id"]: r for r in ix.table("import_runs").select(
        "id,subject_kind,raw_json").execute().data}
    stage_ids = {r["code"]: r["id"] for r in
                 ix.table("lifecycle_stages").select("*").execute().data}
    items = ix.table("import_items").select("*").eq("status", "review") \
        .eq("resolution", "pending").limit(1000).execute().data
    if len(items) == 1000:
        raise RuntimeError("items >= 1000: добавь пагинацию (M024)")

    passed = merged = still = 0
    for item in items:
        run = runs[item["run_id"]]
        kind = run["subject_kind"]
        raw = dict(item["raw"])
        over = overrides.get(item["id"][:8], {})
        raw.update(over)
        report = parse_report_json(run["raw_json"], kind)
        subject = report.product if kind == "product" else report.service
        req_cls = type(report.requirements[0]) if report.requirements else None
        req = req_cls.model_validate(raw)

        gate = verify_item(req, lexuz, llm=llm)
        tag = f"{item['id'][:8]} {req.title[:50]!r}"
        if not gate.ok:
            still += 1
            if gate.reason != item["review_reason"]:
                print(f"  [review] {tag}: {item['review_reason']} → {gate.reason} ({gate.detail})")
            continue
        if dry_run:
            passed += 1
            print(f"  [dry-PASS] {tag} conf={gate.confidence}")
            continue

        try:
            key = external_key(gate.doc_id, gate.ref)
            existing = find_existing(ix, key)
            if existing:
                sanction = req.sanction.model_dump() if req.sanction else None
                status = merge_requirement(ix, existing, [], sanction, item["id"])
                if status == "conflict":
                    still += 1
                    continue
                ix.table("import_items").update(
                    {"status": "merged", "requirement_id": existing["id"],
                     "resolution": "fixed", "raw": raw}).eq("id", item["id"]).execute()
                merged += 1
                print(f"  [MERGED] {tag} → {key}")
                continue
            act_row = resolve_act(req.act, gate.doc_id, jb, ix, QUEUE_PATH)
            paragraph_row = ensure_paragraph(
                ix, act_row, gate.ref, req.legal_quote_ru or req.legal_quote_uz, gate.doc_id)
            req_id = loader.load_requirement(req, kind, gate, act_row, paragraph_row,
                                             subject, stage_ids)
            ix.table("requirement_sources").insert(
                {"requirement_id": req_id, "import_item_id": item["id"]}).execute()
            ix.table("import_items").update(
                {"status": "loaded", "requirement_id": req_id,
                 "resolution": "fixed", "raw": raw}).eq("id", item["id"]).execute()
            passed += 1
            print(f"  [LOADED] {tag} → {key} conf={gate.confidence}")
        except MappingError as e:
            still += 1
            print(f"  [review] {tag}: mapping {e.reason} {e.detail}")
        except Exception as e:  # noqa: BLE001 — ошибка item не роняет прогон
            still += 1
            print(f"  [error] {tag}: {str(e)[:120]}")

    print(f"\nитог: loaded={passed} merged={merged} осталось в review={still}")


if __name__ == "__main__":
    main(dry_run="--dry-run" in sys.argv, use_llm="--llm" in sys.argv)
