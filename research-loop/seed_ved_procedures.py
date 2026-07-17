"""Агентный ресёрч + сид: ВЭД-процедуры из Таможенного кодекса РУз (lex.uz/docs/2876352).

Секции transit/re_export/re_import/export пусты у ВСЕХ товаров (measure_prod), потому
что deep-research-отчёты их не искали. Эти режимы регулируются Таможенным кодексом и
применяются ко всем товарам (scope=all_products) — один сид заполняет секцию для всего
каталога. Цитаты — дословные фрагменты статей (тот же экстрактор, что и гейт), поэтому
проходят верификацию детерминированно. В прод — только через verify_item (правило цикла).

Запуск из корня worktree: .venv-importer/bin/python research-loop/seed_ved_procedures.py [--dry-run]
"""
import hashlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from importer.db import ix_client, jb_client  # noqa: E402
from importer.dedup import external_key, find_existing, merge_requirement  # noqa: E402
from importer.loader import _first  # noqa: E402
from importer.lexuz import LexuzClient  # noqa: E402
from importer.loader import Loader  # noqa: E402
from importer.mappings import load_domains  # noqa: E402
from importer.models import ProductPassport, ProductRequirement  # noqa: E402
from importer.resolver import ensure_paragraph, resolve_act  # noqa: E402
from importer.verifier import verify_item  # noqa: E402

ACT = {"name": "Таможенный кодекс Республики Узбекистан", "number": "ЗРУ-400",
       "date": "2016-01-20", "lexuz_url": "https://lex.uz/docs/2876352"}

# (type, unit, addressees, title, quote — дословный фрагмент статьи)
SPECS = [
    # --- Экспорт (Глава 5) ---
    ("export", "ст. 30", ["exporter"],
     "Уплатить таможенные платежи и соблюсти меры экономической политики при экспорте",
     "Требованиями и условиями помещения товара под таможенный режим экспорта являются "
     "уплата таможенных платежей и соблюдение мер экономической политики."),
    ("export", "ст. 31", ["exporter"],
     "Представить документы для таможенного оформления экспорта (перечень — КМ РУз)",
     "Перечень документов, необходимых для таможенного оформления применительно к "
     "таможенному режиму экспорта, устанавливается Кабинетом Министров Республики Узбекистан."),
    ("export", "ст. 29", ["exporter"],
     "Учитывать: экспортируемый товар вывозится без обязательства обратного ввоза",
     "Таможенный режим экспорта — режим, при котором товар Узбекистана вывозится за "
     "пределы таможенной территории без обязательства его обратного ввоза."),
    # --- Реэкспорт (Глава 6) ---
    ("re_export", "ст. 33", ["exporter"],
     "Обеспечить идентификацию товара таможенным органом при реэкспорте",
     "Реэкспорт товара допускается при условии, что товар либо продукт его переработки "
     "может быть идентифицирован таможенным органом"),
    ("re_export", "ст. 34", ["exporter"],
     "Представить ГТД и товаросопроводительные документы при реэкспорте",
     "Для помещения товара под таможенный режим реэкспорта декларантом в таможенный "
     "орган представляются грузовая таможенная декларация и товаросопроводительные документы."),
    ("re_export", "ст. 32", ["exporter"],
     "Учитывать: реэкспорт — вывоз ранее ввезённого товара без уплаты пошлин и налогов",
     "Таможенный режим реэкспорта — режим, при котором ранее ввезенный на таможенную "
     "территорию товар"),
    # --- Реимпорт (Глава 10) ---
    ("re_import", "ст. 59", ["importer"],
     "Соблюсти требования и условия реимпорта (статус товара, сроки ввоза)",
     "Помещение товара под таможенный режим реимпорта осуществляется при соблюдении "
     "следующих требований и условий"),
    ("re_import", "ст. 60", ["importer"],
     "Представить ГТД и товаросопроводительные документы при реимпорте",
     "Для помещения товара под таможенный режим реимпорта декларантом в таможенный "
     "орган представляются грузовая таможенная декларация и товаросопроводительные документы."),
    ("re_import", "ст. 58", ["importer"],
     "Учитывать: реимпорт — обратный ввоз ранее вывезённого товара без уплаты пошлин",
     "Таможенный режим реимпорта — режим, при котором товары, ранее вывезенные с "
     "таможенной территории, ввозятся обратно на таможенную территорию"),
    # --- Таможенный транзит (Глава 18) ---
    ("transit", "ст. 117", ["carrier"],
     "Соблюсти требования и условия таможенного транзита (товар не запрещён к транзиту)",
     "Под таможенный режим таможенного транзита помещается любой товар при соблюдении "
     "следующих требований и условий"),
    ("transit", "ст. 118", ["carrier"],
     "Представить транзитную декларацию и товаросопроводительные документы",
     "Для помещения товара под таможенный режим таможенного транзита декларантом в "
     "таможенный орган представляются транзитная декларация и товаросопроводительные документы."),
    ("transit", "ст. 120", ["carrier"],
     "Завершить таможенный транзит в установленный таможенным органом срок",
     "Таможенный режим таможенного транзита завершается вывозом ввезенного товара с "
     "таможенной территории или ввозом товара Узбекистана на таможенную территорию."),
]

SUBJECT = ProductPassport(name="ВЭД-процедуры (Таможенный кодекс)", hs_code=None)


def build(spec) -> ProductRequirement:
    typ, unit, addressees, title, quote = spec
    return ProductRequirement.model_validate({
        "title": title, "nature": "obligation", "type": typ,
        "category": "прочее", "summary": title,
        "legal_quote_ru": quote, "act": ACT, "unit": unit,
        "addressees": addressees, "scope": {"level": "all"},
        "discovered_via": "customs-code-agent", "needs_review": False,
    })


def main(dry_run: bool = False):
    ix = ix_client()
    try:
        jb = jb_client()
    except RuntimeError:
        jb = None
    lexuz = LexuzClient(cache_dir=Path("research/.cache/lexuz"))
    domains = load_domains()
    loader = Loader(ix, domains)
    queue = Path("research/act_queue.jsonl")

    run_id = None
    if not dry_run:
        h = hashlib.sha256(repr(SPECS).encode()).hexdigest()
        existing = ix.table("import_runs").select("id").eq("file_hash", h).limit(1).execute().data
        if existing:
            run_id = existing[0]["id"]
        else:
            run_id = _first(ix.table("import_runs").insert({
                "file_name": "product--ved-procedures--customs-code.md",
                "file_hash": h, "subject_kind": "product",
                "subject_slug": "ved-procedures", "model": "customs-code",
                "status": "loaded", "raw_json": {"note": "seed ВЭД из Таможенного кодекса"},
            }).execute())["id"]

    loaded = merged = review = 0
    for idx, spec in enumerate(SPECS):
        req = build(spec)
        gate = verify_item(req, lexuz, llm=None)
        tag = f"{req.type:>10} {req.unit:>8} {req.title[:48]!r}"
        if not gate.ok:
            review += 1
            print(f"  [review:{gate.reason}] {tag} ({gate.detail})")
            if not dry_run:
                loader.save_item(run_id, idx, req, "review",
                                 review_reason=gate.reason, review_detail=gate.detail)
            continue
        if dry_run:
            loaded += 1
            print(f"  [dry-PASS] {tag} conf={gate.confidence} → {external_key(gate.doc_id, gate.ref)}")
            continue
        key = external_key(gate.doc_id, gate.ref)
        existing = find_existing(ix, key)
        if existing:
            item_id = loader.save_item(run_id, idx, req, "merged", requirement_id=existing["id"])
            merge_requirement(ix, existing, [("all_products", None)], None, item_id)
            merged += 1
            print(f"  [MERGED] {tag} → {key}")
            continue
        act_row = resolve_act(req.act, gate.doc_id, jb, ix, queue)
        paragraph_row = ensure_paragraph(ix, act_row, gate.ref, req.legal_quote_ru, gate.doc_id)
        req_id = loader.load_requirement(req, "product", gate, act_row, paragraph_row, SUBJECT, {})
        item_id = loader.save_item(run_id, idx, req, "loaded", requirement_id=req_id)
        ix.table("requirement_sources").insert(
            {"requirement_id": req_id, "import_item_id": item_id}).execute()
        loaded += 1
        print(f"  [LOADED] {tag} conf={gate.confidence} → {key}")

    print(f"\nитог: loaded={loaded} merged={merged} review={review}")


if __name__ == "__main__":
    main(dry_run="--dry-run" in sys.argv)
