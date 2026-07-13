"""Сид общих требований жизненного цикла бизнеса (scope=all_business).

Этапы premises/changes/termination пусты у большинства услуг (measure_prod), т.к.
DR-отчёты искали только профильные нормы. Помещение (пожарная+санитарная), изменения
(ГК: учред. документы, госрегистрация, реорганизация) и прекращение (ГК: ликвидация)
общие для всех бизнесов → scope=all_business заполняет этап для всего каталога услуг.
Цитаты — дословные фрагменты статей; в прод только через verify_item (правило цикла).

Запуск: .venv-importer/bin/python research-loop/seed_service_lifecycle.py [--dry-run]
"""
import hashlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from importer.db import ix_client, jb_client  # noqa: E402
from importer.dedup import external_key, find_existing, merge_requirement  # noqa: E402
from importer.loader import Loader, _first  # noqa: E402
from importer.lexuz import LexuzClient  # noqa: E402
from importer.mappings import STAGE_TO_CODE, load_domains  # noqa: E402
from importer.models import ServicePassport, ServiceRequirement  # noqa: E402
from importer.resolver import ensure_paragraph, resolve_act  # noqa: E402
from importer.verifier import verify_item  # noqa: E402

FIRE = {"name": "Закон Республики Узбекистан «О пожарной безопасности»",
        "number": "ЗРУ-226", "date": "2009-09-30", "lexuz_url": "https://lex.uz/docs/1521663"}
SANIT = {"name": "Закон «О санитарно-эпидемиологическом благополучии населения»",
         "number": "ЗРУ-393", "date": "2015-08-26", "lexuz_url": "https://lex.uz/docs/2732584"}
GK = {"name": "Гражданский кодекс Республики Узбекистан (часть первая)",
      "number": "ГК", "date": "1995-12-21", "lexuz_url": "https://lex.uz/docs/111181"}

# (stage, act, unit, title, quote — дословный фрагмент статьи)
SPECS = [
    # --- Помещение (premises) ---
    ("premises", SANIT, "ст. 16",
     "Соблюдать санитарные правила и нормы при эксплуатации помещений и объектов",
     "выполнять требования законодательства о санитарно-эпидемиологическом благополучии "
     "населения, а также постановлений и предписаний должностных лиц"),
    ("premises", FIRE, "ст. 10",
     "Разрабатывать и осуществлять меры пожарной безопасности, контролировать их выполнение",
     "разрабатывать и осуществлять меры пожарной безопасности, а также обеспечивать "
     "постоянный контроль за их выполнением"),
    ("premises", FIRE, "ст. 14",
     "Разработать и реализовать меры пожарной безопасности на объекте",
     "Мерами пожарной безопасности являются действия по обеспечению пожарной безопасности, "
     "в том числе по выполнению требований пожарной безопасности."),
    # --- Изменения (changes) ---
    ("changes", GK, "ст. 43",
     "Зарегистрировать изменения учредительных документов",
     "Изменения учредительных документов получают силу для третьих лиц с момента "
     "государственной регистрации"),
    ("changes", GK, "ст. 44",
     "Пройти государственную регистрацию юридического лица и внесение данных в реестр",
     "Юридическое лицо подлежит государственной регистрации в порядке, определяемом законодательством."),
    ("changes", GK, "ст. 49",
     "Оформить реорганизацию по решению учредителей (участников)",
     "Реорганизация юридического лица (слияние, присоединение, разделение, выделение, "
     "преобразование) может быть осуществлена по решению его учредителей"),
    # --- Прекращение (termination) ---
    ("termination", GK, "ст. 53",
     "Провести ликвидацию юридического лица при прекращении деятельности",
     "Ликвидация юридического лица влечет его прекращение"),
    ("termination", GK, "ст. 54",
     "Незамедлительно письменно сообщить о решении о ликвидации регистрирующему органу",
     "Учредители (участники) юридического лица или орган, принявшие решение о ликвидации "
     "юридического лица, обязаны незамедлительно письменно сообщить об этом органу"),
    ("termination", GK, "ст. 56",
     "Удовлетворить требования кредиторов в установленной очерёдности при ликвидации",
     "При ликвидации юридического лица в первую очередь удовлетворяются требования граждан, "
     "вытекающие из трудовых правоотношений"),
]

SUBJECT = ServicePassport(name="Общие требования бизнеса", okved="00.00")


def build(spec) -> ServiceRequirement:
    stage, act, unit, title, quote = spec
    return ServiceRequirement.model_validate({
        "title": title, "nature": "obligation", "stage": stage, "summary": title,
        "legal_quote_ru": quote, "act": act, "unit": unit,
        "addressees": ["all"], "scope": "all_business",
        "discovered_via": "business-lifecycle-agent", "needs_review": False,
    })


def main(dry_run: bool = False):
    ix = ix_client()
    try:
        jb = jb_client()
    except RuntimeError:
        jb = None
    lexuz = LexuzClient(cache_dir=Path("research/.cache/lexuz"))
    loader = Loader(ix, load_domains())
    stage_ids = {r["code"]: r["id"] for r in ix.table("lifecycle_stages").select("*").execute().data}
    queue = Path("research/act_queue.jsonl")

    run_id = None
    if not dry_run:
        h = hashlib.sha256(repr(SPECS).encode()).hexdigest()
        ex = ix.table("import_runs").select("id").eq("file_hash", h).limit(1).execute().data
        if ex:
            run_id = ex[0]["id"]
        else:
            run_id = _first(ix.table("import_runs").insert({
                "file_name": "service--business-lifecycle--general.md", "file_hash": h,
                "subject_kind": "service", "subject_slug": "business-lifecycle",
                "model": "general-acts", "status": "loaded",
                "raw_json": {"note": "seed общих требований бизнеса"}}).execute())["id"]

    loaded = merged = review = 0
    for idx, spec in enumerate(SPECS):
        req = build(spec)
        gate = verify_item(req, lexuz, llm=None)
        tag = f"{req.stage:>12} {req.unit:>7} {req.title[:44]!r}"
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
            merge_requirement(ix, existing, [("all_services", None)], None, item_id)
            merged += 1
            print(f"  [MERGED] {tag} → {key}")
            continue
        act_row = resolve_act(req.act, gate.doc_id, jb, ix, queue)
        paragraph_row = ensure_paragraph(ix, act_row, gate.ref, req.legal_quote_ru, gate.doc_id)
        req_id = loader.load_requirement(req, "service", gate, act_row, paragraph_row, SUBJECT, stage_ids)
        item_id = loader.save_item(run_id, idx, req, "loaded", requirement_id=req_id)
        ix.table("requirement_sources").insert(
            {"requirement_id": req_id, "import_item_id": item_id}).execute()
        loaded += 1
        print(f"  [LOADED] {tag} conf={gate.confidence} → {key}")

    print(f"\nитог: loaded={loaded} merged={merged} review={review}")


if __name__ == "__main__":
    main(dry_run="--dry-run" in sys.argv)
