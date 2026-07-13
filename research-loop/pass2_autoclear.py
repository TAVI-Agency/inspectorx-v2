"""Проход 2, авточистка needs_review (правило лупа 13.07.2026).

Для items с review_reason=needs_review_from_report: гоним цитату через гейт,
игнорируя ТОЛЬКО флаг needs_review. Если цитата ДОСЛОВНО сошлась с официальной
страницей (fuzzy >= 0.85, строго без LLM) — модельная неуверенность снята фактом:
пишем {needs_review: false} в pass2-overrides.json (аудируемо) и дописываем
review_detail. Публикацию делает следующий запуск requeue_review.py.

Обоснование: needs_review в отчётах ставился из-за невозможности проверить
источник; если проверка первоисточником прошла дословно — причина исчерпана.
Пограничные (0.60–0.85) НЕ чистим: там нужна человеческая/агентная вычитка.

Запуск: .venv-importer/bin/python research-loop/pass2_autoclear.py
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from importer.db import ix_client  # noqa: E402
from importer.lexuz import LexuzClient  # noqa: E402
from importer.models import parse_report_json  # noqa: E402
from importer.verifier import verify_item  # noqa: E402

OVERRIDES_PATH = Path(__file__).parent / "pass2-overrides.json"


def main():
    ix = ix_client()
    lexuz = LexuzClient(cache_dir=Path("research/.cache/lexuz"))
    overrides = json.loads(OVERRIDES_PATH.read_text(encoding="utf-8")) \
        if OVERRIDES_PATH.exists() else {}

    runs = {r["id"]: r for r in ix.table("import_runs").select(
        "id,subject_kind,raw_json").execute().data}
    items = ix.table("import_items").select("*").eq("status", "review") \
        .eq("resolution", "pending").eq("review_reason", "needs_review_from_report") \
        .limit(1000).execute().data

    cleared = borderline = failed = 0
    for item in items:
        short = item["id"][:8]
        if short in overrides and overrides[short].get("needs_review") is False:
            continue
        run = runs[item["run_id"]]
        report = parse_report_json(run["raw_json"], run["subject_kind"])
        if not report.requirements:
            continue
        req_cls = type(report.requirements[0])
        raw = dict(item["raw"])
        raw.update(overrides.get(short, {}))
        raw["needs_review"] = False  # снимаем ТОЛЬКО флаг, всё прочее — как есть
        req = req_cls.model_validate(raw)

        gate = verify_item(req, lexuz, llm=None)  # строго: без LLM
        if gate.ok and (gate.confidence or 0) >= 0.85:
            over = overrides.setdefault(short, {})
            over["needs_review"] = False
            note = (f" || pass2-autoclear 2026-07-13: цитата дословно сошлась с "
                    f"первоисточником (conf={gate.confidence}, {gate.doc_id}/{gate.ref}) — "
                    f"флаг needs_review снят правилом лупа.")
            ix.table("import_items").update(
                {"review_detail": (item.get("review_detail") or "") + note}
            ).eq("id", item["id"]).execute()
            cleared += 1
            print(f"  [CLEAR] {short} {req.title[:55]!r} conf={gate.confidence}")
        elif gate.reason == "quote_mismatch":
            borderline += 1
        else:
            failed += 1

    OVERRIDES_PATH.write_text(json.dumps(overrides, ensure_ascii=False, indent=1),
                              encoding="utf-8")
    print(f"\nитог: снято={cleared}, пограничных (нужна вычитка)={borderline}, "
          f"прочих фейлов={failed}; overrides → {OVERRIDES_PATH.name}")


if __name__ == "__main__":
    main()
