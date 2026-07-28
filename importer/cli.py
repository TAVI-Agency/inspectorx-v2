"""CLI импортёра: import-report / review list / review show."""
import argparse
import json
from pathlib import Path

from importer.db import ix_client, jb_client
from importer.lexuz import LexuzClient
from importer.llm import LLM
from importer.pipeline import run_import


def main(argv=None):
    parser = argparse.ArgumentParser(prog="importer")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_imp = sub.add_parser("import-report", help="импорт одного отчёта")
    p_imp.add_argument("file", type=Path)
    p_imp.add_argument("--dry-run", action="store_true")
    p_imp.add_argument("--no-llm", action="store_true", help="без claude -p (спорное → review)")

    p_rev = sub.add_parser("review", help="review-очередь")
    rev_sub = p_rev.add_subparsers(dest="rev_cmd", required=True)
    rev_sub.add_parser("list")
    p_show = rev_sub.add_parser("show")
    p_show.add_argument("item_id")

    args = parser.parse_args(argv)
    ix = ix_client()

    if args.cmd == "import-report":
        try:
            jb = jb_client()
        except RuntimeError:
            jb = None  # JB-ключей нет — резолвим только через lex.uz, акты в очередь
        lexuz = LexuzClient(cache_dir=Path("research/.cache/lexuz"))
        llm = None if args.no_llm else LLM()
        s = run_import(args.file, ix, jb, lexuz, llm, dry_run=args.dry_run)
        print(f"\n{'[DRY RUN] ' if s.dry_run else ''}loaded={s.loaded} "
              f"merged={s.merged} review={s.review}")
        if s.uz_backfill:
            print(f"  без узбекского оригинала (добивка фазы 3): {s.uz_backfill}")
        for reason, n in sorted(s.reasons.items(), key=lambda kv: -kv[1]):
            print(f"  review:{reason} = {n}")
        return

    if args.rev_cmd == "list":
        rows = ix.table("import_items").select("id, review_reason, review_detail, raw") \
            .eq("status", "review").eq("resolution", "pending").execute().data
        for r in rows:
            print(f"{r['id']}  [{r['review_reason']}] {r['raw'].get('title', '')[:70]}")
        print(f"\nвсего в очереди: {len(rows)}")
    else:
        rows = ix.table("import_items").select("*").eq("id", args.item_id).execute().data
        print(json.dumps(rows[0] if rows else {}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
