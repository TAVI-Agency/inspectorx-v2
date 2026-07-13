"""Замер прода для лупа: published-требования по предметам × секциям против цели.

Источник правды — БД прода (M001), не витрина и не отчёты.
Цель (решение 13.07.2026): минимум 3 требования на секцию товара / этап услуги,
либо явный статус «норм нет». Запуск:
.venv-importer/bin/python research-loop/measure_prod.py
"""
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from importer.db import ix_client  # noqa: E402

PRODUCT_OPS = ["product", "realization", "import", "export", "transit", "re_export", "re_import"]
TARGET_MIN = 3


def fetch_all(ix, table, select, page=1000):
    out, start = [], 0
    while True:  # пагинация всегда (M024)
        rows = ix.table(table).select(select).range(start, start + page - 1).execute().data
        out += rows
        if len(rows) < page:
            return out
        start += page


def main():
    ix = ix_client()
    reqs = {r["id"]: r for r in fetch_all(
        ix, "requirements", "id,operation,status,lifecycle_stage_id,origin")
        if r["status"] == "published"}
    apps = fetch_all(ix, "requirement_applicability", "requirement_id,scope,code")
    stages = {s["id"]: s["code"] for s in fetch_all(ix, "lifecycle_stages", "id,code")}
    products = fetch_all(ix, "products", "id,name_ru,hs_code,is_active")
    services = fetch_all(ix, "services", "id,name_ru,oked_code,is_active") \
        if _has(ix, "services") else []

    # предметы лупа: 4 товара bootstrap-цикла (v1-иерархию ТН ВЭД не меряем)
    loop_prefixes = ("4011", "2523", "8703", "3208")
    products = [p for p in products
                if p.get("hs_code") and p["hs_code"].startswith(loop_prefixes)]

    # товар × операция: требование применимо, если код применимости — префикс hs товара
    print("## Товары (published, цель ≥3 на секцию; '.'=0)\n")
    header = "товар".ljust(38) + " ".join(op[:7].rjust(8) for op in PRODUCT_OPS)
    print(header)
    for p in products:
        if not p.get("is_active") or not p.get("hs_code"):
            continue
        counts = defaultdict(int)
        for a in apps:
            r = reqs.get(a["requirement_id"])
            if not r or not r.get("operation"):
                continue
            code = a.get("code") or ""
            if a["scope"] == "all" or (code and (p["hs_code"].startswith(code)
                                                 or code.startswith(p["hs_code"]))):
                counts[r["operation"]] += 1
        row = "".join(str(counts.get(op) or ".").rjust(9) for op in PRODUCT_OPS)
        gaps = sum(1 for op in PRODUCT_OPS if (counts.get(op) or 0) < TARGET_MIN)
        print(p["name_ru"][:37].ljust(38) + row + f"   gaps:{gaps}/7")

    print("\n## Услуги (published по этапам)\n")
    stage_by_req = {rid: stages.get(r.get("lifecycle_stage_id"))
                    for rid, r in reqs.items()}
    svc_stage_codes = sorted({c for c in stages.values() if c and c.startswith("svc-")})
    if services:
        svc_apps = defaultdict(lambda: defaultdict(int))
        for a in apps:
            r = reqs.get(a["requirement_id"])
            if not r:
                continue
            st = stage_by_req.get(a["requirement_id"])
            if st:
                svc_apps[a.get("code") or "all"][st] += 1
        print("этапы:", " ".join(svc_stage_codes))
        for s in services:
            counts = svc_apps.get(s.get("oked_code") or "", {})
            general = svc_apps.get("all", {})
            merged = {k: general.get(k, 0) + counts.get(k, 0)
                      for k in set(general) | set(counts)}
            row = " ".join(str(merged.get(c) or ".").rjust(6) for c in svc_stage_codes)
            gaps = sum(1 for c in svc_stage_codes if (merged.get(c) or 0) < TARGET_MIN)
            print(f"{(s.get('name_ru') or '?')[:36].ljust(37)}{row}   gaps:{gaps}/{len(svc_stage_codes)}")
    else:
        by_stage = defaultdict(int)
        for rid, r in reqs.items():
            st = stage_by_req.get(rid)
            if st:
                by_stage[st] += 1
        for c in svc_stage_codes:
            print(f"  {c}: {by_stage.get(c, 0)} (все услуги вместе — таблицы services нет)")

    total = len(reqs)
    by_origin = defaultdict(int)
    for r in reqs.values():
        by_origin[r.get("origin") or "?"] += 1
    print(f"\nвсего published: {total}; по origin: {dict(by_origin)}")


def _has(ix, table):
    try:
        ix.table(table).select("id").limit(1).execute()
        return True
    except Exception:
        return False


if __name__ == "__main__":
    main()
