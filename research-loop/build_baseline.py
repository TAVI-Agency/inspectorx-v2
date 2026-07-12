"""Baseline eval-цифры по рубрике §4 → research-loop/baseline-2026-07.md.

Запуск из корня worktree: .venv-importer/bin/python research-loop/build_baseline.py
Скорит: 4 импортированных отчёта (research/incoming/) + eval-копии новых
(research-loop/eval-reports/), citation_pass_rate — из import_runs/import_items прода.
"""
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from importer.db import ix_client  # noqa: E402
from importer.evalharness import (PRODUCT_SECTIONS, SERVICE_STAGES,  # noqa: E402
                                  cross_agreement, score_report)

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "research-loop" / "baseline-2026-07.md"

IMPORTED = sorted((ROOT / "research" / "incoming").glob("*--*--*.md"))
EVAL_ONLY = sorted((ROOT / "research-loop" / "eval-reports").glob("*--*--*.md"))


def pct(x):
    return f"{100 * x:.0f}%"


def gate_stats():
    """citation_pass_rate по живому прогону: (loaded+merged)/items, причины review."""
    ix = ix_client()
    runs = ix.table("import_runs").select(
        "id,file_name,loaded_count,merged_count,review_count").execute().data
    items = ix.table("import_items").select("run_id,status,review_reason").limit(1000).execute().data
    if len(items) == 1000:
        raise RuntimeError("items >= 1000: добавь пагинацию (грабля M024)")
    by_run = {}
    for r in runs:
        rid = r["id"]
        run_items = [i for i in items if i["run_id"] == rid]
        total = len(run_items)
        passed = r["loaded_count"] + r["merged_count"]
        reasons = Counter(i["review_reason"] for i in run_items if i["status"] == "review")
        by_run[r["file_name"]] = {"total": total, "passed": passed, "reasons": reasons}
    return by_run


def main():
    scores = [score_report(p) for p in IMPORTED + EVAL_ONLY]
    gates = gate_stats()

    lines = ["# Baseline research-цикла — июль 2026",
             "",
             "> Скоринг по рубрике handoff-research-loop §4 (зафиксирована 12.07.2026).",
             "> Сгенерировано research-loop/build_baseline.py, ночь 13.07.2026.",
             "> citation_pass_rate — только у 4 отчётов, прошедших живой импорт 12.07;",
             "> остальные оценены офлайн (в прод не грузились — решение ночи, см. DECISIONS).",
             ""]

    lines += ["## Метрики по отчётам", "",
              "| Отчёт | kind | model | schema | N req | coverage | needs_review | "
              "unit | how_to+url | docs | санкция ₮ | все 4 поля | gate pass |",
              "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for s in scores:
        name = s.path.name
        gate = gates.get(name)
        gate_cell = f"{gate['passed']}/{gate['total']}" if gate else "—"
        if not s.schema_valid:
            lines.append(f"| {name} | {s.kind or '?'} | {s.model or '?'} | ❌ | — | — | — "
                         f"| — | — | — | — | — | {gate_cell} |")
            continue
        f = s.fields
        lines.append(
            f"| {name} | {s.kind} | {s.model} | ✅ | {s.total} | {pct(s.section_coverage)} "
            f"| {pct(s.needs_review_rate)} | {pct(f.unit / s.total)} | {pct(f.how_to / s.total)} "
            f"| {pct(f.documents / s.total)} | {pct(f.sanction_sum / s.total)} "
            f"| {pct(f.complete / s.total)} | {gate_cell} |")

    lines += ["", "## Причины review в гейте (живой прогон 12.07)", ""]
    for name, g in sorted(gates.items()):
        rs = ", ".join(f"{k}={v}" for k, v in g["reasons"].most_common()) or "—"
        lines.append(f"- **{name}**: pass {g['passed']}/{g['total']}; review: {rs}")

    lines += ["", "## Gap-матрица: товар × секция (число требований)", ""]
    prod_scores = [s for s in scores if s.kind == "product" and s.schema_valid]
    header = "| товар (model) | " + " | ".join(PRODUCT_SECTIONS) + " |"
    lines += [header, "|" + "---|" * (len(PRODUCT_SECTIONS) + 1)]
    for s in prod_scores:
        row = " | ".join(str(s.sections.get(sec, 0)) or "0" for sec in PRODUCT_SECTIONS)
        lines.append(f"| {s.slug} ({s.model}) | {row} |")

    lines += ["", "## Gap-матрица: услуга × этап жизни бизнеса", ""]
    svc_scores = [s for s in scores if s.kind == "service" and s.schema_valid]
    header = "| услуга (model) | " + " | ".join(SERVICE_STAGES) + " |"
    lines += [header, "|" + "---|" * (len(SERVICE_STAGES) + 1)]
    for s in svc_scores:
        row = " | ".join(str(s.sections.get(st, 0)) for st in SERVICE_STAGES)
        lines.append(f"| {s.slug} ({s.model}) | {row} |")

    lines += ["", "## cross_model_agreement (§4.6) — пары прогонов одного предмета", "",
              "| предмет | пара | совпало | только A | только B | Jaccard |",
              "|---|---|---|---|---|---|"]
    by_slug = {}
    for s in scores:
        if s.schema_valid:
            by_slug.setdefault((s.kind, s.slug), []).append(s)
    pairs = 0
    for (kind, slug), group in sorted(by_slug.items()):
        # байт-идентичные копии одного файла — не второй прогон, сравнивать нечего
        uniq = {p.read_bytes(): s for s in group for p in [s.path]}
        group = list(uniq.values())
        if len(group) < 2:
            continue
        for i in range(len(group)):
            for j in range(i + 1, len(group)):
                a, b = group[i], group[j]
                agr = cross_agreement(a, b)
                pairs += 1
                lines.append(f"| {slug} | {a.model} vs {b.model} | {agr.common} "
                             f"| {agr.only_a} | {agr.only_b} | {pct(agr.jaccard)} |")
    if not pairs:
        lines.append("| — | настоящих вторых прогонов нет (проверено хэшами: compass-файлы "
                     "= уже импортированные отчёты) | — | — | — | n/a |")

    unkeyed_total = sum(s.unkeyed for s in scores if s.schema_valid)
    total_reqs = sum(s.total for s in scores if s.schema_valid)
    invalid = [s.path.name for s in scores if not s.schema_valid]
    lines += ["", "## Примечания", "",
              f"- Требований без ключа акт+пункт (нет lex.uz-ссылки): {unkeyed_total} из {total_reqs} "
              "— они не участвуют в agreement.",
              f"- Отчёты с schema_valid=0: {', '.join(invalid) if invalid else 'нет'}.",
              "- section_coverage: явных статусов секций в отчётах нет (sections_checked — "
              "бэклог промпта §5.1), поэтому coverage = доля секций рамки с ≥1 требованием.",
              "- verified-карточек/час (§4.7): пока n/a — review-очередь не разобрана ни разу, "
              "замер невозможен; фиксируем после первого разбора очереди.",
              ""]

    OUT.write_text("\n".join(lines), encoding="utf-8")
    print(f"написано: {OUT} ({len(scores)} отчётов)")


if __name__ == "__main__":
    main()
