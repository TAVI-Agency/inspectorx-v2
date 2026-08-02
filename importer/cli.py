"""CLI импортёра: import-report / review list / review show / build ...."""
import argparse
import json
import os
from pathlib import Path

from importer.build.cartographer import Cartographer
from importer.build.llm_client import RunnerAgentLLM
from importer.build.orchestrator import (
    MapAlreadyApprovedError,
    MapNotApprovedError,
    Orchestrator,
    SupabaseBuildStore,
)
from importer.db import ix_client, jb_client
from importer.lexuz import LexuzClient
from importer.llm import LLM
from importer.pipeline import run_import


def _cartographer_llm_runner(prompt: str, model: str) -> str:
    """Заглушка runner'а для CLI `build map`: живое LLM-подключение
    (Cartographer — expensive-тир, deep-research) не входит в эту задачу —
    решение контроллера (task-15-brief.md) отнесло смоук на пилотной группе
    2402 к пилотному прогону Задачи 27. В тестах Cartographer используется
    скриптованный `AgentLLMClient` (см. `importer/tests/build/test_cartographer.py`),
    сеть не трогается вообще."""
    raise NotImplementedError(
        "Живой LLM-runner для Cartographer ещё не подключён — 'build map' "
        "заработает после пилотного прогона Задачи 27 (инъекция runner'а, "
        "см. importer/build/llm_client.py:RunnerAgentLLM)"
    )


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

    p_build = sub.add_parser("build", help="Build-конвейер: оркестратор pipeline.items (Задача 14)")
    build_sub = p_build.add_subparsers(dest="build_cmd", required=True)
    p_build_run = build_sub.add_parser("run", help="прогнать конвейер по утверждённой карте")
    p_build_run.add_argument("--map", dest="map_id", required=True)
    p_build_status = build_sub.add_parser("status", help="статус айтемов запуска")
    p_build_status.add_argument("--run", dest="run_id", required=True)
    build_sub.add_parser("attention", help="список айтемов needs_attention")
    p_build_map = build_sub.add_parser(
        "map", help="Cartographer: построить draft-карту группы (Задача 15)"
    )
    p_build_map.add_argument("--group", dest="group_ref", required=True)
    p_build_map.add_argument("--jurisdiction", required=True)
    p_build_approve = build_sub.add_parser(
        "approve-map", help="апрув draft-карты владельцем: draft -> approved (стоп-точка ①)"
    )
    p_build_approve.add_argument("--map", dest="map_id", required=True)
    p_build_reject = build_sub.add_parser(
        "reject-map", help="отклонить draft-карту: draft -> rejected"
    )
    p_build_reject.add_argument("--map", dest="map_id", required=True)

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

    if args.cmd == "build":
        store = SupabaseBuildStore(ix)
        if args.build_cmd == "run":
            try:
                report = Orchestrator(store).run_group(args.map_id)
            except MapNotApprovedError as exc:
                print(f"ошибка: {exc}")
                raise SystemExit(1)
            print(f"run={report.run_id} total={report.total_items} "
                  f"published={report.published} no_norm={report.no_norm} "
                  f"needs_attention={report.needs_attention}")
        elif args.build_cmd == "status":
            summary = store.run_summary(args.run_id)
            if not summary:
                print(f"по запуску {args.run_id} айтемов не найдено")
            for status, count in sorted(summary.items()):
                print(f"{status}: {count}")
        elif args.build_cmd == "attention":
            items = store.list_needs_attention()
            for item in items:
                print(f"{item.id}  [{item.last_error}] {item.expected_item[:70]}")
            print(f"\nвсего needs_attention: {len(items)}")
        elif args.build_cmd == "map":
            cartographer = Cartographer(store, RunnerAgentLLM(_cartographer_llm_runner))
            try:
                report = cartographer.build_map(args.group_ref, args.jurisdiction)
            except MapAlreadyApprovedError as exc:
                print(f"ошибка: {exc}")
                raise SystemExit(1)
            print(
                f"map={report.map_id} group={report.group_ref} "
                f"jurisdiction={report.jurisdiction} items={report.items_count} "
                "status=draft"
            )
            if report.candidate_categories:
                print("кандидаты новых категорий (НЕ попали в карту, нужен апрув владельца):")
                for c in report.candidate_categories:
                    print(f"  slug={c.get('category_slug')!r} item={str(c.get('expected_item'))[:70]}")
        elif args.build_cmd == "approve-map":
            approved_by = os.environ.get("USER") or "owner"
            record = store.set_map_status(args.map_id, "approved", approved_by=approved_by)
            print(
                f"map={record.id} status={record.status} "
                f"approved_by={record.approved_by} approved_at={record.approved_at}"
            )
        else:  # reject-map
            record = store.set_map_status(args.map_id, "rejected")
            print(f"map={record.id} status={record.status}")
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
