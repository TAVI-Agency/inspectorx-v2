"""CLI импортёра: import-report / review list / review show / build ...."""
import argparse
import json
import os
from pathlib import Path

from importer.build.cartographer import Cartographer
from importer.build.coverage import coverage_report, publish_ready
from importer.build.eval_golden import HeuristicBaselineLLM, load_golden_set, run_eval
from importer.build.legalx import get_client as get_legalx_client
from importer.build.llm_client import RunnerAgentLLM
from importer.build.orchestrator import (
    MapAlreadyApprovedError,
    MapNotApprovedError,
    Orchestrator,
    SupabaseBuildStore,
)
from importer.build.registry import build_step_registry
from importer.build.steps import load_default_steps
from importer.build.trace import Tracer, cost_report
from importer.db import ix_client, jb_client
from importer.lexuz import LexuzClient
from importer.llm import LLM
from importer.monitoring.impact_mapper import (
    InHouseLawyer,
    SupabaseMonitoringStore,
    process_changes,
)
from importer.pipeline import run_import


def _cartographer_llm_runner(prompt: str, model: str) -> str:
    """Заглушка runner'а для CLI `build map`: живое LLM-подключение
    (Cartographer — expensive-тир, deep-research) не входит в эту задачу —
    решение контроллера (task-15-brief.md) отнесло смоук на пилотной группе
    2402 к пилотному прогону Задачи 27. Пилотный прогон Задачи 27 —
    СИНТЕТИЧЕСКИЙ (решение контроллера, task-27-brief.md): карта пишется
    руками через `store.save_map`, не через этот runner. В тестах
    Cartographer используется скриптованный `AgentLLMClient` (см.
    `importer/tests/build/test_cartographer.py`), сеть не трогается вообще."""
    raise NotImplementedError(
        "Живой LLM-runner для Cartographer ещё не подключён — 'build map' "
        "заработает после получения живого LLM-ключа (вне Задачи 27, см. "
        "importer/build/llm_client.py:RunnerAgentLLM)"
    )


def _build_llm_runner(prompt: str, model: str) -> str:
    """Заглушка runner'а для CLI `build run`: тот же принцип отсрочки, что
    и `_cartographer_llm_runner` — живого LLM-ключа нет (решение
    контроллера Задачи 27), падает только при РЕАЛЬНОМ вызове модели, не
    при построении реестра шагов (`build_step_registry`). Синтетический
    прогон Задачи 27 (`scripts/pilot_synthetic.py`) инжектирует свой
    scripted-runner напрямую в Python, минуя эту CLI-заглушку."""
    raise NotImplementedError(
        "Живой LLM-runner для Build-конвейера ещё не подключён — 'build run' "
        "заработает после получения живого LLM-ключа (см. "
        "importer/build/llm_client.py:RunnerAgentLLM)"
    )


def _monitor_llm_runner(prompt: str, model: str) -> str:
    """Заглушка runner'а для CLI `monitor process-changes` (Задача 40): тот
    же принцип отсрочки, что и `_build_llm_runner`/`_cartographer_llm_runner`
    — падает только при РЕАЛЬНОМ вызове модели (Classifier-кандидаты пути
    (б) или In-house lawyer), не при построении `InHouseLawyer`/вызове
    `process_changes` на событии, которое разрешилось точным цитатным
    совпадением (путь а) без единого обращения к LLM. Живое подключение —
    после получения живого LLM-ключа, как и у остальных LLM-раннеров CLI."""
    raise NotImplementedError(
        "Живой LLM-runner для мониторинга ещё не подключён — "
        "'monitor process-changes' заработает после получения живого "
        "LLM-ключа (см. importer/build/llm_client.py:RunnerAgentLLM)"
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
    p_build_run.add_argument(
        "--no-publish", action="store_true",
        help="не публиковать автоматически после coverage (осторожный прогон)",
    )
    p_build_status = build_sub.add_parser("status", help="статус айтемов запуска")
    p_build_status.add_argument("--run", dest="run_id", required=True)
    build_sub.add_parser("attention", help="список айтемов needs_attention")
    p_build_coverage = build_sub.add_parser(
        "coverage", help="coverage-отчёт по прогону: карта vs факт (Задача 27)"
    )
    p_build_coverage.add_argument("--run", dest="run_id", required=True)
    p_build_publish = build_sub.add_parser(
        "publish", help="публикация draft_loaded-айтемов прогона по вердиктам (Задача 27)"
    )
    p_build_publish.add_argument("--run", dest="run_id", required=True)
    p_build_cost = build_sub.add_parser(
        "cost", help="стоимость прогона по ролям: role | calls | in_tokens | out_tokens | cost_usd (Задача 29)"
    )
    p_build_cost.add_argument("--run", dest="run_id", required=True)
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
    p_build_eval_golden = build_sub.add_parser(
        "eval-golden",
        help="eval golden set (Задача 28, СТОП-ТОЧКА ②): retrieval_hit/verifier_agreement/"
             "category_accuracy/lifecycle_date_accuracy против generic-агентов",
    )
    p_build_eval_golden.add_argument(
        "--limit", type=int, default=None, help="прогнать только первые N айтемов golden-набора"
    )
    p_build_eval_golden.add_argument(
        "--save-baseline", action="store_true",
        help="записать текущий прогон в importer/golden/baseline.json (следующий прогон "
             "покажет дельту против него)",
    )

    # Задача 40: мониторинг изменений (Impact-маппер + In-house lawyer +
    # ре-ревью). Продовый запуск — cron-джоб Railway каждые 15 минут
    # (`python -m importer monitor process-changes`, без публичного
    # endpoint — YAGNI, докстринг `importer/monitoring/impact_mapper.py`);
    # сама настройка джоба — вне репозитория.
    p_monitor = sub.add_parser("monitor", help="мониторинг изменений LegalX (Задача 40)")
    monitor_sub = p_monitor.add_subparsers(dest="monitor_cmd", required=True)
    monitor_sub.add_parser(
        "process-changes",
        help="необработанные change_events -> impacts + флаг + ре-ревью + уведомления",
    )

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
            # group_ref/jurisdiction карты — фабрике шагов (build_step_registry,
            # Задача 27): конструкторные зависимости шагов (jurisdiction у
            # NormStep/SanctionsStep/CasesStep/AssembleStep, group_ref у
            # ScopeStep/LoadStep, target_lang у TranslateStep) обязаны прийти
            # ИЗ карты этого прогона, не из заглушек глобального реестра
            # steps.py (load_default_steps/_STUB_GROUP_REF/DEFAULT_JURISDICTION).
            map_record = store.load_map(args.map_id)
            # Задача 29 (фикс-раунд ревью): ОДИН Tracer, late-bound
            # (run_id/item_id ещё не существуют на этом шаге, см. докстринг
            # `trace.py:Tracer`) — та же ссылка идёт И в фабрику шагов
            # (агенты внутри Step-ов трейсят через неё), И в Orchestrator
            # (который её же bind_run/bind_item мутирует по ходу прогона).
            # Тождество объекта обязательно: разные экземпляры Tracer друг
            # друга не видят.
            tracer = Tracer(store)
            registry = build_step_registry(
                store, _build_llm_runner, get_legalx_client(),
                group_ref=map_record.group_ref, jurisdiction=map_record.jurisdiction,
                tracer=tracer,
            )
            try:
                report = Orchestrator(store, steps=registry, tracer=tracer).run_group(
                    args.map_id, publish=not args.no_publish
                )
            except MapNotApprovedError as exc:
                print(f"ошибка: {exc}")
                raise SystemExit(1)
            print(f"run={report.run_id} total={report.total_items} "
                  f"draft_loaded={report.draft_loaded} published={report.published} "
                  f"no_norm={report.no_norm} needs_attention={report.needs_attention}")
            if report.coverage:
                print()
                print(report.coverage.markdown)
        elif args.build_cmd == "coverage":
            report = coverage_report(store, args.run_id)
            store.save_coverage_report(args.run_id, report.markdown)
            print(report.markdown)
        elif args.build_cmd == "publish":
            count = publish_ready(store, args.run_id)
            print(f"опубликовано: {count}")
        elif args.build_cmd == "cost":
            report = cost_report(store, args.run_id)
            print(report.markdown)
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
        elif args.build_cmd == "reject-map":
            record = store.set_map_status(args.map_id, "rejected")
            print(f"map={record.id} status={record.status}")
        else:  # eval-golden
            golden_path = Path("importer/golden/golden_set.yaml")
            baseline_path = Path("importer/golden/baseline.json")
            items = load_golden_set(golden_path)
            if args.limit:
                items = items[: args.limit]
            baseline = (
                json.loads(baseline_path.read_text(encoding="utf-8"))
                if baseline_path.exists() else None
            )
            # Живого LLM-ключа в контуре нет (тот же принцип отсрочки, что и
            # у 'build run'/'build map' выше) — HeuristicBaselineLLM НЕ
            # семантика, только smoke-проверка проводки golden->агент->
            # метрика (см. докстринг importer/build/eval_golden.py).
            print("backend=mock (LEGALX_BACKEND) + HeuristicBaselineLLM "
                  "(живого LLM-ключа нет — числа НЕ мера качества, только smoke)")
            report = run_eval(
                items, legalx=get_legalx_client(), llm=HeuristicBaselineLLM(),
                valid_category_slugs=store.list_category_slugs(),
                backend="mock", baseline=baseline,
            )
            print(report.markdown)
            print(json.dumps(report.to_json_dict(), ensure_ascii=False, indent=2))
            if args.save_baseline:
                baseline_path.parent.mkdir(parents=True, exist_ok=True)
                baseline_path.write_text(
                    json.dumps(report.to_json_dict(), ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8",
                )
                print(f"baseline сохранён -> {baseline_path}")
        return

    if args.cmd == "monitor":
        if args.monitor_cmd == "process-changes":
            monitor_store = SupabaseMonitoringStore(ix)
            # Оркестратор ре-ревью — БЕЗ явного steps= (глобальный реестр
            # `get_step`, наполняется `load_default_steps()` ниже): в
            # отличие от `build run`, у `rerun_item` нет одной карты
            # (group_ref/jurisdiction), из которой `build_step_registry`
            # мог бы собрать per-run реестр — затронутые требования этого
            # прогона мониторинга могут быть из РАЗНЫХ групп/юрисдикций.
            # Глобальный реестр использует заглушки `_STUB_GROUP_REF=""`/
            # `DEFAULT_JURISDICTION='UZ'` (см. докстринг `registry.py`) —
            # корректно для UZ-прогонов по группе, случайно совпавшей с
            # заглушкой; полная привязка per-item реестра к его исходной
            # карте — известный технический долг, тот же, что уже
            # зафиксирован в `registry.py`, не новый для этой задачи.
            load_default_steps()
            build_store = SupabaseBuildStore(ix)
            orchestrator = Orchestrator(build_store)
            lawyer = InHouseLawyer(RunnerAgentLLM(_monitor_llm_runner))
            report = process_changes(
                monitor_store,
                classifier_llm=RunnerAgentLLM(_monitor_llm_runner),
                lawyer=lawyer,
                orchestrator=orchestrator,
            )
            print(
                f"events_seen={report.events_seen} processed={report.events_processed} "
                f"duplicates_skipped={report.duplicates_skipped} "
                f"no_candidates={report.events_no_candidates}"
            )
            print(
                f"impacts_created={report.impacts_created} "
                f"requirements_flagged={report.requirements_flagged} "
                f"rereviews_enqueued={report.rereviews_enqueued} "
                f"notifications_sent={report.notifications_sent}"
            )
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
