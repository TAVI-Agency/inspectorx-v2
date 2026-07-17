"""Агентный ресёрч + сид: секции product/realization для всех товаров (итерация 7, 17.07.2026).

Топ-провал measure_prod после итерации 6: у всех 4 товаров product/realization < 3.
Общие для любых товаров нормы: ЗоЗПП (lex.uz/docs/14643), Закон «О техническом
регулировании» ЗРУ-819 (docs/6392314), Правила розничной торговли ПКМ-75 (docs/243233).
Цитаты добыты агентным ресёрчем (WebSearch → lex.uz) и проверены как дословные
подстроки живых страниц; в прод — только через verify_item (правило цикла).

Дедуп-ключ ст. 6 ЗоЗПП намеренно один: карточка «информация о товаре» покрывает и
язык информации (гос. язык — та же статья); вторую карточку на ту же статью не сеем.

Запуск из корня worktree: .venv-importer/bin/python research-loop/seed_product_realization.py [--dry-run]
"""
import hashlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from importer.db import ix_client, jb_client  # noqa: E402
from importer.dedup import external_key, find_existing, merge_requirement  # noqa: E402
from importer.lexuz import LexuzClient  # noqa: E402
from importer.loader import Loader, _first  # noqa: E402
from importer.mappings import load_domains  # noqa: E402
from importer.models import ProductPassport, ProductRequirement  # noqa: E402
from importer.resolver import ensure_paragraph, resolve_act  # noqa: E402
from importer.verifier import verify_item  # noqa: E402

ZOZPP = {"name": "Закон Республики Узбекистан «О защите прав потребителей»",
         "number": "221-I", "date": "1996-04-26",
         "lexuz_url": "https://lex.uz/docs/14643"}
ZRU819 = {"name": "Закон Республики Узбекистан «О техническом регулировании»",
          "number": "ЗРУ-819", "date": "2023-02-27",
          "lexuz_url": "https://lex.uz/docs/6392314"}
PKM75 = {"name": "Правила розничной торговли в Республике Узбекистан "
                 "(приложение № 1 к постановлению КМ № 75)",
         "number": "75", "date": "2003-02-13",
         "lexuz_url": "https://lex.uz/docs/243233"}

AGENCY_CONSUMER = "Агентство по защите прав потребителей при Антимонопольном комитете"

# (type, act, unit, addressees, category, title, quote, sanction, agency)
SPECS = [
    # --- Реализация (продажа любого товара) ---
    ("realization", ZOZPP, "ст. 6", ["seller"],
     "маркировка и защита прав потребителей",
     "Предоставлять покупателю полную и достоверную информацию о товаре",
     "Изготовитель (исполнитель, продавец) обязан своевременно предоставлять потребителю "
     "необходимую, достоверную и доступную информацию о реализуемых им товарах (работах, "
     "услугах). При этом данная информация может доводиться до потребителей на этикетках, "
     "маркировках, технической документации товаров или иным способом, принятым для "
     "отдельных видов товаров (работ, услуг).",
     {"article": "КоАО, ст. 178", "fine_bru": "3–7 БРВ (граждане), 7–10 БРВ (должностные лица)",
      "extra": "с конфискацией предметов правонарушения",
      "url": "https://lex.uz/docs/97661"},
     AGENCY_CONSUMER),
    ("realization", ZOZPP, "ст. 18", ["seller"],
     "маркировка и защита прав потребителей",
     "Обеспечивать обмен и возврат непродовольственного товара надлежащего качества (10 дней)",
     "Потребитель вправе в течение десяти дней со дня покупки обменять непродовольственный "
     "товар надлежащего качества на аналогичный у продавца, где он был приобретен, а в "
     "случае отсутствия такого товара в продаже — получить денежную компенсацию.",
     {"article": "КоАО, ст. 178", "fine_bru": "3–5 БРВ (граждане), 5–10 БРВ (должностные лица)",
      "extra": "за неисполнение предписаний об устранении нарушений прав потребителей",
      "url": "https://lex.uz/docs/97661"},
     AGENCY_CONSUMER),
    ("realization", ZOZPP, "ст. 10", ["seller"],
     "маркировка и защита прав потребителей",
     "Выдавать покупателю кассовый или товарный чек при продаже",
     "При совершении купли-продажи потребителю выдается кассовый или товарный чек. "
     "Продажа товара без выдачи кассового или товарного чека запрещается.",
     {"article": "Налоговый кодекс, ст. 221", "fine_bru": None,
      "extra": "торговля без ККТ/без выдачи чека — штраф 5 000 000 сумов; "
               "незарегистрированная ККТ — 7 000 000 сумов",
      "url": "https://lex.uz/docs/4674893"},
     "Налоговые органы"),
    ("realization", PKM75, "п. 20", ["seller"],
     "маркировка и защита прав потребителей",
     "Оформлять единообразные ценники на все реализуемые товары",
     "Продавец-работник обязан обеспечить наличие единообразных и четко оформленных "
     "ценников на реализуемые товары с указанием наименования товара, его сорта, марки, "
     "модели, типа, цены за вес, меру или единицу товара.",
     None,
     AGENCY_CONSUMER),
    # --- Продукт (требования к самому товару) ---
    ("product", ZOZPP, "ст. 12", ["manufacturer"],
     "технические требования и безопасность",
     "Обеспечивать безопасность товара в течение срока службы или годности",
     "Изготовитель (исполнитель) обязан обеспечить безопасность товара (работы, услуги) "
     "в течение установленного срока его службы или срока годности, а если он не "
     "установлен — в течение десяти лет со дня продажи товара (работы) потребителю.",
     {"article": "ЗоЗПП, ст. 20", "fine_bru": None,
      "extra": "имущественная ответственность за вред, причинённый опасным товаром",
      "url": "https://lex.uz/docs/14643"},
     AGENCY_CONSUMER),
    ("product", ZRU819, "ст. 24", ["manufacturer", "importer"],
     "оценка соответствия, декларация и сертификация",
     "Пройти обязательное подтверждение соответствия перед выпуском продукции в обращение",
     "Объектом обязательного подтверждения соответствия может быть только продукция, "
     "выпускаемая в обращение на территории Республики Узбекистан.",
     {"article": "ЗРУ-819, ст. 46", "fine_bru": None,
      "extra": "штраф до 50% стоимости реализованной продукции, не соответствующей "
               "обязательным требованиям (повторно в течение года — до 100%)",
      "url": "https://lex.uz/docs/6392314"},
     "Узбекское агентство по техническому регулированию"),
    ("product", ZRU819, "ст. 42", ["manufacturer"],
     "маркировка и защита прав потребителей",
     "Наносить на продукцию номер партии или серии для идентификации",
     "Производитель обязан поставить на продукцию номер партии или серии, позволяющий "
     "идентифицировать продукцию в соответствии с нормативными документами в области "
     "технического регулирования.",
     {"article": "ЗРУ-819, ст. 46", "fine_bru": None,
      "extra": "штраф до 50% стоимости реализованной продукции, не соответствующей "
               "обязательным требованиям (повторно — до 100%)",
      "url": "https://lex.uz/docs/6392314"},
     "Узбекское агентство по техническому регулированию"),
]

SUBJECT = ProductPassport(name="Общие требования к товару и продаже", hs_code=None)


def build(spec) -> ProductRequirement:
    typ, act, unit, addressees, category, title, quote, sanction, agency = spec
    return ProductRequirement.model_validate({
        "title": title, "nature": "obligation", "type": typ,
        "category": category, "summary": title,
        "legal_quote_ru": quote, "act": act, "unit": unit,
        "addressees": addressees, "scope": {"level": "all"},
        "sanction": sanction, "agency": agency,
        "discovered_via": "product-realization-agent", "needs_review": False,
    })


def main(dry_run: bool = False):
    ix = ix_client()
    try:
        jb = jb_client()
    except RuntimeError:
        jb = None
    lexuz = LexuzClient(cache_dir=Path("research/.cache/lexuz"))
    loader = Loader(ix, load_domains())
    queue = Path("research/act_queue.jsonl")

    run_id = None
    if not dry_run:
        h = hashlib.sha256(repr(SPECS).encode()).hexdigest()
        existing = ix.table("import_runs").select("id").eq("file_hash", h).limit(1).execute().data
        if existing:
            run_id = existing[0]["id"]
        else:
            run_id = _first(ix.table("import_runs").insert({
                "file_name": "product--common-product-realization--agent.md",
                "file_hash": h, "subject_kind": "product",
                "subject_slug": "common-product-realization", "model": "agent-research",
                "status": "loaded",
                "raw_json": {"note": "сид product/realization из ЗоЗПП, ЗРУ-819, ПКМ-75"},
            }).execute())["id"]

    loaded = merged = review = 0
    for idx, spec in enumerate(SPECS):
        req = build(spec)
        gate = verify_item(req, lexuz, llm=None)
        tag = f"{req.type:>12} {req.unit:>7} {req.title[:46]!r}"
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
            sanction = req.sanction.model_dump() if req.sanction else None
            merge_requirement(ix, existing, [("all_products", None)], sanction, item_id)
            merged += 1
            print(f"  [MERGED] {tag} → {key}")
            continue
        act_row = resolve_act(req.act, gate.doc_id, jb, ix, queue)
        paragraph_row = ensure_paragraph(
            ix, act_row, gate.ref, req.legal_quote_ru, gate.doc_id,
            quote_uz=(req.legal_quote_uz if gate.verified_lang == "uz" else None))
        req_id = loader.load_requirement(req, "product", gate, act_row, paragraph_row, SUBJECT, {})
        item_id = loader.save_item(run_id, idx, req, "loaded", requirement_id=req_id)
        ix.table("requirement_sources").insert(
            {"requirement_id": req_id, "import_item_id": item_id}).execute()
        loaded += 1
        print(f"  [LOADED] {tag} conf={gate.confidence} → {key}")

    print(f"\nитог: loaded={loaded} merged={merged} review={review}")


if __name__ == "__main__":
    main(dry_run="--dry-run" in sys.argv)
