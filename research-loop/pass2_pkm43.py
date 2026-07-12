"""Проход 2 (прототип, ночь 13.07.2026): серые зоны ПКМ-43 для шин и цемента.

Делает три вещи:
1) ставит джобы smart_import в JurisBase processing_jobs на недостающие акты
   (идемпотентно: не дублирует pending-джобу на тот же lexuz_id);
2) извлекает дословные UZ-строки прил. 4 ПКМ-43 (сертификация) для кодов 4011 и 2523
   из закэшированной страницы lex.uz/docs/5249376;
3) дописывает находку в review_detail соответствующих import_items (прод не публикуем:
   решение ночи — карточки в БД только через гейт и человека).
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from importer.db import ix_client, jb_client  # noqa: E402
from importer.lexuz import LexuzClient  # noqa: E402

UZ_HTML = Path("research/.cache/lexuz/5249376-uz.html")

ACTS_TO_QUEUE = [
    ("5249376", "https://lex.uz/docs/5249376", "uz"),   # ПКМ-43, перечни оценки соответствия
    ("7533469", "https://lex.uz/docs/7533469", "ru"),   # ПП-181, ТН ВЭД + ставки
    ("3180907", "https://lex.uz/ru/docs/3180907", "ru"),  # техрегламент колёсных ТС
    ("5563048", "https://lex.uz/docs/5563048", "ru"),   # закон «О транспорте»
    ("5511900", "https://lex.uz/docs/5511900", "ru"),   # закон о лицензировании
]

# item_id → (код ТН ВЭД, слаг)
TARGET_ITEMS = {
    "f313a32f": ("4011", "tyre"),
    "a50277e0": ("4011", "tyre"),
    "0da18b4e": ("2523", "cement"),
    "435c0df0": ("2523", "cement"),
}


def extract_row(text: str, code: str) -> tuple[str, str]:
    """Дословная строка прил. 4 с кодом: (номер строки, текст строки)."""
    h = text.find(code)
    if h < 0:
        raise RuntimeError(f"код {code} не найден")
    before = text[:h]
    m = list(re.finditer(r"\s(\d{1,3})\.\s", before))
    row_no = m[-1].group(1) if m else "?"
    row_start = m[-1].start() if m else max(0, h - 400)
    after = re.search(r"\s\d{1,3}\.\s", text[h:h + 600])
    row_end = h + (after.start() if after else 400)
    return row_no, re.sub(r"\s+", " ", text[row_start:row_end]).strip()


def queue_jobs(jb):
    existing = jb.table("processing_jobs").select("id,input_data,status").in_(
        "status", ["pending", "processing"]).limit(1000).execute().data
    queued_ids = {(j.get("input_data") or {}).get("lexuz_id") for j in existing}
    created = []
    for lexuz_id, url, lang in ACTS_TO_QUEUE:
        if lexuz_id in queued_ids:
            continue
        try:
            jb.table("processing_jobs").insert({
                "job_type": "smart_import",
                "status": "pending",
                "priority": 5,
                "input_data": {"source_url": url, "source_type": "link",
                               "lexuz_id": lexuz_id, "source_lang": lang,
                               "options": {"requested_by": "inspector-x pass2 2026-07-13"}},
            }).execute()
        except Exception as exc:  # RLS: публичный ключ не пишет — джобы ставит service-роль
            print(f"  джоба {lexuz_id} не поставлена ({str(exc)[:80]}) — нужен service-ключ JB")
            continue
        created.append(lexuz_id)
    return created


def main():
    text = LexuzClient.page_text(UZ_HTML.read_text())
    rows = {code: extract_row(text, code) for code in ("4011", "2523")}
    for code, (no, row) in rows.items():
        print(f"[{code}] прил. 4, строка {no}: {row[:120]}…")

    jb = jb_client()
    created = queue_jobs(jb)
    print("джобы поставлены:", created or "все уже в очереди")

    ix = ix_client()
    items = ix.table("import_items").select("id,review_detail").limit(1000).execute().data
    updated = 0
    for item in items:
        short = item["id"][:8]
        if short not in TARGET_ITEMS:
            continue
        code, _ = TARGET_ITEMS[short]
        row_no, row = rows[code]
        note = (f" || pass2 2026-07-13: код {code} подтверждён в прил. 4 ПКМ-43 "
                f"(обязательная СЕРТИФИКАЦИЯ, «Мувофиқлик сертификати расмийлаштирилиши "
                f"лозим бўлган маҳсулотлар»), строка {row_no}, действующая ред. 24.12.2025, "
                f"UZ-текст: «{row[:600]}» — источник https://lex.uz/docs/5249376. "
                f"Гейт v1 не пропустит (uz_only_act): подтверждение — за человеком.")
        detail = (item.get("review_detail") or "") + note
        ix.table("import_items").update({"review_detail": detail}).eq("id", item["id"]).execute()
        updated += 1
    print(f"обогащено items: {updated}/4")


if __name__ == "__main__":
    main()
