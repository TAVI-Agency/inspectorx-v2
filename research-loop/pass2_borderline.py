"""Проход 2, пограничные цитаты (fuzzy 0.60–0.85): агентная вычитка по первоисточнику.

Для items needs_review_from_report/quote_mismatch, где цитата с пункта акта сошлась
лишь частично: агент (claude -p) читает НАЙДЕННЫЙ на официальной странице пункт и
цитату отчёта. Если пункт действительно подтверждает требование — возвращает
ДОСЛОВНЫЙ фрагмент страницы. Скрипт принимает ответ ТОЛЬКО если фрагмент буквально
входит в текст страницы (защита от галлюцинации), пишет его в overrides как
legal_quote_ru + needs_review=false. Публикует следующий requeue (гейт пройдёт
детерминированно: цитата взята со страницы).

Запуск: .venv-importer/bin/python research-loop/pass2_borderline.py [--limit N]
"""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from rapidfuzz import fuzz  # noqa: E402

from importer.db import ix_client  # noqa: E402
from importer.lexuz import LexuzClient  # noqa: E402
from importer.llm import LLM  # noqa: E402
from importer.models import parse_report_json  # noqa: E402
from importer.refs import lexuz_doc_id, parse_unit_ref  # noqa: E402

OVERRIDES_PATH = Path(__file__).parent / "pass2-overrides.json"

PROMPT = """Ты сверяешь юридическую цитату с официальным текстом акта (lex.uz).

ТЕКСТ С ОФИЦИАЛЬНОЙ СТРАНИЦЫ (пункт/фрагмент):
<<<
{paragraph}
>>>

ЦИТАТА ИЗ ОТЧЁТА (могла быть перефразирована):
<<<
{quote}
>>>

ТРЕБОВАНИЕ, которое цитата должна подтверждать: {title} — {summary}

Если официальный текст ПОДТВЕРЖДАЕТ требование, ответь строго дословным фрагментом
официального текста (скопируй 150–500 знаков, без изменений, без кавычек, без
комментариев). Если НЕ подтверждает или текст о другом — ответь ровно: NO"""


def normalize(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def main(limit: int = 60):
    ix = ix_client()
    lexuz = LexuzClient(cache_dir=Path("research/.cache/lexuz"))
    llm = LLM()
    overrides = json.loads(OVERRIDES_PATH.read_text(encoding="utf-8")) \
        if OVERRIDES_PATH.exists() else {}

    runs = {r["id"]: r for r in ix.table("import_runs").select(
        "id,subject_kind,raw_json").execute().data}
    items = ix.table("import_items").select("*").eq("status", "review") \
        .eq("resolution", "pending") \
        .in_("review_reason", ["needs_review_from_report", "quote_mismatch"]) \
        .limit(1000).execute().data

    fixed = rejected = skipped = 0
    processed = 0
    for item in items:
        if processed >= limit:
            break
        short = item["id"][:8]
        over = overrides.get(short, {})
        if over.get("legal_quote_ru"):
            continue
        raw = dict(item["raw"])
        raw.update(over)
        run = runs[item["run_id"]]
        report = parse_report_json(run["raw_json"], run["subject_kind"])
        if not report.requirements:
            continue
        req = type(report.requirements[0]).model_validate({**raw, "needs_review": False})

        doc_id = lexuz_doc_id(req.verify_url or req.act.lexuz_url)
        ref = parse_unit_ref(req.unit)
        quote = req.legal_quote_ru or req.legal_quote_uz
        if not (doc_id and quote):
            skipped += 1
            continue
        try:
            html = lexuz.fetch(doc_id)
        except Exception:
            skipped += 1
            continue
        paragraph = (LexuzClient.find_paragraph(html, ref) if ref else None) \
            or LexuzClient.page_text(html)
        score = fuzz.partial_ratio(quote.lower(), paragraph.lower()) / 100.0
        if not 0.60 <= score < 0.85:
            continue  # не пограничный: либо уже дословный, либо совсем не о том
        processed += 1

        # окно вокруг лучшего совпадения: полная страница может быть 60k+ знаков,
        # первые 6000 — не то место (урок первого прогона: 31/31 ложных NO)
        window = paragraph
        if len(paragraph) > 6000:
            al = fuzz.partial_ratio_alignment(quote.lower(), paragraph.lower())
            lo = max(0, (al.dest_start if al else 0) - 2500)
            window = paragraph[lo:lo + 6000]

        answer = normalize(llm.complete(PROMPT.format(
            paragraph=window, quote=quote[:1500],
            title=req.title, summary=req.summary[:400])))
        if answer.upper().startswith("NO") or len(answer) < 60:
            rejected += 1
            print(f"  [NO]   {short} {req.title[:55]!r} fuzzy={score:.2f}")
            continue
        # защита от галлюцинации: фрагмент обязан дословно входить в страницу
        if normalize(answer).lower() not in normalize(paragraph).lower():
            rejected += 1
            print(f"  [HALL] {short} фрагмент не найден на странице — отклонено")
            continue
        over.update({"legal_quote_ru": answer[:900], "needs_review": False})
        overrides[short] = over
        note = (f" || pass2-borderline 2026-07-13: цитата заменена дословным фрагментом "
                f"страницы {doc_id}/{ref or 'full'} (агентная вычитка, fuzzy был {score:.2f}).")
        ix.table("import_items").update(
            {"review_detail": (item.get("review_detail") or "") + note}
        ).eq("id", item["id"]).execute()
        fixed += 1
        print(f"  [FIX]  {short} {req.title[:55]!r} fuzzy={score:.2f} → verbatim")

    OVERRIDES_PATH.write_text(json.dumps(overrides, ensure_ascii=False, indent=1),
                              encoding="utf-8")
    print(f"\nитог: verbatim-замен={fixed}, отклонено агентом={rejected}, "
          f"пропущено={skipped}")


if __name__ == "__main__":
    limit = 60
    if "--limit" in sys.argv:
        limit = int(sys.argv[sys.argv.index("--limit") + 1])
    main(limit)
