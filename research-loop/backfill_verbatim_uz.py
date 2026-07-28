"""Добивка библиотеки узбекских оригиналов: verbatim_uz по уже загруженным пунктам.

Зачем. Фаза 1 UZ-first пишет verbatim_uz только когда требование пришло С узбекской
цитатой (gate.verified_lang == "uz"). Входной поток — русские DR-отчёты, поэтому в
проде 0 из 200 параграфов имеют узбекский оригинал. Этот скрипт добирает их задним
числом: берёт пункт, находит УЗБЕКСКУЮ версию того же акта по шапке страницы и
кладёт дословный текст пункта в verbatim_uz.

Почему это не «мимо гейта». Гейт проверяет утверждение МОДЕЛИ против первоисточника.
Здесь модели нет вообще: текст берётся с официальной страницы lex.uz по тому же
номеру пункта, что уже сохранён в базе. Записывается только в пустое поле.

Границы. Добить можно лишь пункт с машинным ref (art.14, p.20, ch.3, app1/p.5…) —
такие ссылки find_paragraph умеет искать на странице. Пункты из переноса v1 с
текстовой ссылкой («обязательная маркировка», «п. 36») пропускаются: машинно их на
странице акта не найти, им нужна ручная или агентная переработка.

Запуск (по умолчанию — всухую, ничего не пишет):
    .venv-importer/bin/python research-loop/backfill_verbatim_uz.py
    .venv-importer/bin/python research-loop/backfill_verbatim_uz.py --apply
    ... --limit 20        # сначала на выборке
Отчёт по каждому пункту — research-loop/backfill-verbatim-uz.jsonl
"""
import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from importer.db import ix_client  # noqa: E402
from importer.lexuz import LexuzClient, LexuzUnreachable  # noqa: E402
from importer.refs import lexuz_doc_id  # noqa: E402

REPORT = Path(__file__).parent / "backfill-verbatim-uz.jsonl"

# Формы ref, которые понимает find_paragraph (см. importer/refs.py::parse_unit_ref).
_MACHINE_REF = re.compile(r"^(art|p|ch|app\d*)[./\-]", re.IGNORECASE)


def is_machine_ref(ref: str | None) -> bool:
    """Ссылку на пункт можно найти на странице акта машинно?"""
    return bool(ref) and bool(_MACHINE_REF.match(str(ref)))


def pick_uz_doc(versions: dict) -> str | None:
    """Узбекская версия акта: кириллица канонична для наших цитат, латиница — запасная."""
    return versions.get("uz_cyr") or versions.get("uz_lat")


def _doc_id(row: dict, acts: dict) -> str | None:
    act = acts.get(row.get("act_id")) or {}
    return lexuz_doc_id(act.get("url") or "") or lexuz_doc_id(row.get("deep_link_url") or "")


def plan(paragraphs: list[dict], acts: dict) -> tuple[list[dict], Counter]:
    """Делит пункты на добиваемые и пропущенные (с названной причиной)."""
    candidates, skipped = [], Counter()
    for row in paragraphs:
        if row.get("verbatim_uz"):
            skipped["already_filled"] += 1
        elif not is_machine_ref(row.get("paragraph_ref")):
            skipped["legacy_ref"] += 1
        elif not _doc_id(row, acts):
            skipped["no_lexuz_doc"] += 1
        else:
            candidates.append(row)
    return candidates, skipped


def backfill(ix, lexuz: LexuzClient, candidates: list[dict], acts: dict,
             *, apply: bool = False, report=None) -> Counter:
    """Для каждого пункта: UZ-версия акта → текст пункта → verbatim_uz (только в пустое)."""
    res = Counter()
    for row in candidates:
        ref = row["paragraph_ref"]
        doc_id = _doc_id(row, acts)
        note = {"paragraph_id": row["id"], "ref": ref, "doc_id": doc_id}
        try:
            html = lexuz.fetch(doc_id)
            if LexuzClient.is_russian(html):
                uz_doc = pick_uz_doc(LexuzClient.language_versions(html))
                if not uz_doc:
                    res["uz_version_not_found"] += 1
                    _note(report, note | {"outcome": "uz_version_not_found"})
                    continue
                page = lexuz.fetch(uz_doc)
            else:
                uz_doc, page = doc_id, html  # страница акта сама узбекская
        except LexuzUnreachable as e:
            res["unreachable"] += 1
            _note(report, note | {"outcome": "unreachable", "detail": str(e)[:200]})
            continue

        text = LexuzClient.find_paragraph(page, ref)
        if not text:
            res["paragraph_not_found"] += 1
            _note(report, note | {"outcome": "paragraph_not_found", "uz_doc_id": uz_doc})
            continue

        if apply:
            ix.table("act_paragraphs").update({"verbatim_uz": text}) \
                .eq("id", row["id"]).execute()
        res["filled"] += 1
        _note(report, note | {"outcome": "filled", "uz_doc_id": uz_doc,
                              "chars": len(text), "applied": apply})
    return res


def _note(report, payload: dict) -> None:
    if report is not None:
        report.write(json.dumps(payload, ensure_ascii=False) + "\n")


def _fetch_all(ix, table: str, columns: str) -> list[dict]:
    return ix.table(table).select(columns).limit(10_000).execute().data


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--apply", action="store_true", help="писать в БД (по умолчанию всухую)")
    ap.add_argument("--limit", type=int, help="взять только N пунктов (проба)")
    args = ap.parse_args()

    ix = ix_client()
    paragraphs = _fetch_all(ix, "act_paragraphs",
                            "id,act_id,paragraph_ref,verbatim_uz,deep_link_url")
    acts = {a["id"]: a for a in _fetch_all(ix, "acts", "id,title,url")}
    candidates, skipped = plan(paragraphs, acts)
    if args.limit:
        candidates = candidates[:args.limit]

    print(f"параграфов всего: {len(paragraphs)} | к добивке: {len(candidates)}")
    for reason, n in skipped.most_common():
        print(f"  пропущено {reason}: {n}")

    lexuz = LexuzClient(cache_dir=Path("research/.cache/lexuz"))
    with REPORT.open("w", encoding="utf-8") as fh:
        res = backfill(ix, lexuz, candidates, acts, apply=args.apply, report=fh)

    print(f"\n{'ЗАПИСАНО' if args.apply else '[всухую] нашлось'}: {res['filled']}")
    for reason in ("uz_version_not_found", "paragraph_not_found", "unreachable"):
        if res[reason]:
            print(f"  {reason}: {res[reason]}")
    print(f"отчёт по пунктам: {REPORT}")


if __name__ == "__main__":
    main()
