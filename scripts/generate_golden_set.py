#!/usr/bin/env python3
"""Генератор DRAFT golden set (Задача 28, ~20 требований) —
`importer/golden/golden_set.yaml`.

## Почему DRAFT и почему автоматически

Брифовский Шаг 1 предполагал ручную разметку golden set вместе с
Абдурахмоном (он подтверждает пачкой). Переопределение контроллера
(task-28-brief.md): разметка «вместе с» невозможна в этой сессии — вместо
неё сет строится АВТОМАТИЧЕСКИ из уже опубликованного, ПРОВЕРЕННОГО контента
локальной БД (сид v1 + аптека + кафе) — эти карточки прошли проверку до
публикации, это и есть ручной эталон. Файл несёт шапку
`status: draft — ожидает подтверждения владельцем (гейт ②)`: подтверждение
пачкой владельцем — на самом гейте, не в этом скрипте.

## Источник данных

Локальная БД ПОСЛЕ `supabase db start && supabase db reset --local`, читаем
через `supabase db query --local -o json --agent=no` (тот же приём, что и
`scripts/generate_catalog_seed.mjs` — см. его докстринг, задача 5). Прямых
запросов к прод-БД скрипт не делает вообще — только `--local`.

## Отбор ~20 требований — SELECTION_PLAN

Диверсификация (решение контроллера, шаг 1 брифа): ≥3 категории NTM, товары
И услуги, с санкциями и без, с датами ЖЦ если есть. Фактическая проверка
26.08.2026 показала: датовых полей (`effective_from`/`transition_until`/
`valid_to`) НЕТ ни у одного published-требования (0 из 259) — это честный
пробел контента, не баг генератора; `lifecycle_dates` во всех 20 айтемах —
`null`-тройка, см. заголовок YAML.

`SELECTION_PLAN` ниже — явный список `requirement_id`, отобранных вручную по
итогам разведочного анализа локальной БД (распределение по категориям,
товар/услуга, санкции, наличие цитаты акта — см. отчёт задачи). Сами ЗНАЧЕНИЯ
полей (`expected_item`, `category_slug`, цитата, санкции, применимость)
скрипт КАЖДЫЙ РАЗ читает заново из БД — не хардкодит текст, только состав
множества id. Это сознательный компромисс между «полностью программной
диверсификацией» (нестабильна: разные прогоны выбирали бы разные айтемы при
равном приоритете, что плохо для golden set, который должен быть стабильным
эталоном между прогонами eval) и «полностью ручной вставкой значений»
(потеряла бы связь с живыми данными БД). Если состав пула сильно изменится
(новая пилотная группа, ре-сид), список нужно пересмотреть — скрипт явно
падает, если хотя бы один id из плана исчез из published-контента.

8 категорий охвачены (customs/tbt/origin/currency/marking/fiscal/licensing/
sps) — из восьми, которые вообще определены в `requirement_categories`;
13 товаров (сигареты, единственный HS6 пилотной группы 2402/2404 с богатым
контентом) + 7 услуг (аптека ОКЭД 47.73 давшая почти весь пул услуг с
санкциями + одна карточка кафе ОКЭД 56.10 без санкции, для контраста);
5 из 20 несут санкцию (санкции сейчас сконцентрированы в услугах — у
товарного сигаретного контента миграции v1 колонка `sanctions` почти везде
пуста); 3 из 20 (`origin`-категория + одна `licensing`-карточка) НЕ несут
`source_act` — реальный пробел «перенос из v1 без указанного источника», а
не искусственный пропуск: golden set обязан отражать реальность, включая
её дыры (иначе eval будет мерить несуществующий идеальный мир).

Запуск: `.venv-importer/bin/python scripts/generate_golden_set.py`
"""
from __future__ import annotations

import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_PATH = REPO_ROOT / "importer" / "golden" / "golden_set.yaml"

# (id, requirement_id, category_slug-ожидание — только для читаемости плана,
# фактическое значение читается из БД и обязано совпасть, иначе AssertionError)
SELECTION_PLAN: list[tuple[str, str, str]] = [
    ("g01", "10ada300-ac64-dd8e-fc42-7c1191591a6b", "customs"),
    ("g02", "685bc4dc-b805-25d9-c1fb-2d3fb17cf1ef", "customs"),
    ("g03", "4218bf4c-6c1f-7ca4-c7c4-78b09347f6a9", "tbt"),
    ("g04", "640a34db-798e-c499-eae9-38021ec5852a", "tbt"),
    ("g05", "60510014-d12e-3e07-a359-4ccd3d88c886", "origin"),
    ("g06", "d41fae17-6261-6450-bbb7-afdbd982fbd0", "origin"),
    ("g07", "3dbba131-2a9e-7242-4b37-795cf2a9c4de", "currency"),
    ("g08", "e079f7cf-673f-dc52-9909-6a7768e30261", "currency"),
    ("g09", "933571b3-6cfe-a070-63cd-9b26aff21d01", "marking"),
    ("g10", "ff506fbc-4e73-e17b-fdac-429f234f3f3c", "marking"),
    ("g11", "1c9d4884-f341-0b57-aa53-1372bebe85a9", "fiscal"),
    ("g12", "1be3e249-699e-37b0-fc10-26df5c7beab7", "licensing"),
    ("g13", "25cc8e11-3a82-d618-6df4-deb953f932e7", "sps"),
    ("g14", "d9bc0854-ec95-3bc3-5e53-a313bb744b2a", "marking"),
    ("g15", "a6941960-ee38-e21e-9d65-caeea6da2b97", "fiscal"),
    ("g16", "0b91bfb2-55ed-0be1-0880-6b2a4b23b4b3", "licensing"),
    ("g17", "a9fb161f-363a-7ef4-ef84-984daced669e", "licensing"),
    ("g18", "01298207-f442-e82f-5a56-0e60fe7b8488", "licensing"),
    ("g19", "a5abcabc-97eb-1d69-de1f-6a8d6e364dcf", "sps"),
    ("g20", "f4bebc31-336e-2184-16df-b4e6e77c28b6", "sps"),
]

_PLACEHOLDER_ACT = "Источник не указан (перенос из v1)"

_QUERY = """
select
  r.id::text as requirement_id,
  rc.title as expected_item,
  r.category_slug as category_slug,
  r.origin::text as req_origin,
  r.effective_from::text as effective_from,
  r.transition_until::text as transition_until,
  r.valid_to::text as valid_to,
  app.scope,
  app.code as applicability_code,
  coalesce(p.name_ru, s.name_ru) as product_or_service_name,
  case when p.name_ru is not null then 'product'
       when s.name_ru is not null then 'service'
       else null end as product_kind,
  sanc.sanctions_json,
  cite.source_act_json
from public.requirements r
join public.requirement_contents rc
  on rc.requirement_id = r.id and rc.lang = 'ru'
left join lateral (
  select ra.scope::text as scope, ra.code
  from public.requirement_applicability ra
  where ra.requirement_id = r.id and ra.scope::text in ('hs_code', 'oked_code')
  order by ra.scope::text, ra.code
  limit 1
) app on true
left join public.products p on app.scope = 'hs_code' and p.hs_code = app.code
left join public.services s on app.scope = 'oked_code' and s.oked_code = app.code
left join lateral (
  select rd.sanctions as sanctions_json
  from public.requirement_details rd
  where rd.requirement_id = r.id and rd.lang = 'ru'
  limit 1
) sanc on true
left join lateral (
  select jsonb_build_object('act', a.title, 'article', ap.paragraph_ref) as source_act_json
  from public.requirement_citations rcit
  join public.act_paragraphs ap on ap.id = rcit.paragraph_id
  join public.acts a on a.id = ap.act_id
  where rcit.requirement_id = r.id
  order by rcit.is_primary desc, rcit.sort_order asc
  limit 1
) cite on true
where r.status = 'published'
order by r.id;
"""


def _db_query(sql: str) -> list[dict]:
    """Запрос к ЛОКАЛЬНОЙ БД через `supabase db query --local` (тот же
    приём, что и `scripts/generate_catalog_seed.mjs`) — никогда не прод."""
    proc = subprocess.run(
        ["supabase", "db", "query", sql, "--local", "-o", "json", "--agent=no"],
        cwd=REPO_ROOT, capture_output=True, text=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            "supabase db query --local упал — поднят ли локальный стек? "
            f"(supabase db start && supabase db reset --local)\nstderr: {proc.stderr}"
        )
    return json.loads(proc.stdout)


def _clean_act_title(raw: str | None) -> str | None:
    """Нормализует заголовок акта из цитаты: берёт только ПЕРВЫЙ акт, если
    их перечислено несколько (`"1. ПКМ-290, ТР\\n2. ПКМ-43 ..."`), и снимает
    ведущую нумерацию `"N. "` — canonical-ответ несёт один акт, не список."""
    if not raw:
        return None
    first_line = raw.strip().split("\n")[0]
    return re.sub(r"^\d+\.\s*", "", first_line).strip()


def _source_act(source_act_json: dict | None) -> dict:
    if not source_act_json:
        return {"act": None, "article": None}
    act = _clean_act_title(source_act_json.get("act"))
    if act is None or act == _PLACEHOLDER_ACT:
        # «Источник не указан (перенос из v1)» — это НЕ цитата, а честная
        # пометка её отсутствия (см. докстринг модуля) — golden set хранит
        # это как null, а не как псевдо-реквизит.
        return {"act": None, "article": None}
    return {"act": act, "article": source_act_json.get("article")}


def _sanction_article(sanctions_json) -> str | None:
    if not sanctions_json:
        return None
    first = sanctions_json[0]
    return first.get("article") if isinstance(first, dict) else None


def _canonical_question(title: str) -> str:
    """Шаблонный (детерминированный, без LLM) вопрос из заголовка
    требования — см. докстринг модуля, брифовское «сформулируй из title
    детерминированно-шаблонно»."""
    return f'Какая норма права устанавливает требование: «{title}»?'


def build_items(rows_by_id: dict[str, dict]) -> list[dict]:
    items = []
    missing = [rid for _, rid, _ in SELECTION_PLAN if rid not in rows_by_id]
    if missing:
        raise AssertionError(
            f"SELECTION_PLAN несёт {len(missing)} requirement_id, которых нет "
            f"среди published в локальной БД: {missing} — состав пула изменился "
            "(ре-сид?), план нужно пересмотреть (см. докстринг модуля)"
        )

    for golden_id, req_id, expected_category in SELECTION_PLAN:
        row = rows_by_id[req_id]
        actual_category = row["category_slug"]
        if actual_category != expected_category:
            raise AssertionError(
                f"{golden_id} ({req_id}): SELECTION_PLAN ожидал категорию "
                f"{expected_category!r}, в БД сейчас {actual_category!r} — "
                "категория требования изменилась, план нужно пересмотреть"
            )
        items.append({
            "id": golden_id,
            "expected_item": row["expected_item"],
            "category_slug": actual_category,
            "canonical_question": _canonical_question(row["expected_item"]),
            "source_act": _source_act(row["source_act_json"]),
            "lifecycle_dates": {
                "effective_from": row["effective_from"],
                "transition_until": row["transition_until"],
                "valid_to": row["valid_to"],
            },
            "sanction_article": _sanction_article(row["sanctions_json"]),
            "origin": {
                "requirement_id": req_id,
                "kind": row["product_kind"],
                "code": row["applicability_code"],
                "name": row["product_or_service_name"],
            },
        })
    return items


def _counters(items: list[dict]) -> dict:
    categories: dict[str, int] = {}
    for item in items:
        slug = item["category_slug"] or "uncategorized"
        categories[slug] = categories.get(slug, 0) + 1
    by_kind: dict[str, int] = {}
    for item in items:
        kind = item["origin"]["kind"] or "unknown"
        by_kind[kind] = by_kind.get(kind, 0) + 1
    with_sanction = sum(1 for i in items if i["sanction_article"])
    with_source_act = sum(1 for i in items if i["source_act"]["act"])
    with_lifecycle_dates = sum(
        1 for i in items
        if any(i["lifecycle_dates"].values())
    )
    return {
        "total": len(items),
        "categories": dict(sorted(categories.items())),
        "distinct_categories": len(categories),
        "by_kind": dict(sorted(by_kind.items())),
        "with_sanction": with_sanction,
        "without_sanction": len(items) - with_sanction,
        "with_source_act": with_source_act,
        "without_source_act": len(items) - with_source_act,
        "with_lifecycle_dates": with_lifecycle_dates,
    }


def generate() -> dict:
    rows = _db_query(_QUERY)
    if not rows:
        raise RuntimeError(
            "public.requirements пуст в локальной БД — выполните "
            "supabase db start && supabase db reset --local"
        )
    rows_by_id = {row["requirement_id"]: row for row in rows}
    items = build_items(rows_by_id)
    counters = _counters(items)
    if counters["distinct_categories"] < 3:
        raise AssertionError(
            f"golden set покрывает {counters['distinct_categories']} категорий "
            "NTM — брифовское требование ≥3 не выполнено"
        )
    if "product" not in counters["by_kind"] or "service" not in counters["by_kind"]:
        raise AssertionError(
            f"golden set обязан включать И товары, И услуги — фактически {counters['by_kind']}"
        )

    doc = {
        "status": "draft — ожидает подтверждения владельцем (гейт ②)",
        "generated_at": datetime.now(timezone.utc).date().isoformat(),
        "source": (
            "локальная Supabase (supabase db reset --local), published UZ — "
            "сид v1 (сигареты) + аптека ОКЭД 47.73 + кафе ОКЭД 56.10. "
            "Авто-DRAFT (переопределение шага 1 контроллером, "
            "task-28-brief.md): разметка «вместе с Абдурахмоном» в этой "
            "сессии невозможна — сет собран из уже проверенного и "
            "опубликованного контента (это и есть ручной эталон), "
            "подтверждение пачкой владельцем — на гейте ②."
        ),
        "counters": counters,
        "items": items,
    }
    return doc


def main() -> None:
    doc = generate()
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_PATH.open("w", encoding="utf-8") as f:
        yaml.safe_dump(doc, f, allow_unicode=True, sort_keys=False, width=100)
    print(f"golden set: {doc['counters']['total']} требований -> {OUTPUT_PATH}")
    print(f"категории ({doc['counters']['distinct_categories']}): {doc['counters']['categories']}")
    print(f"товар/услуга: {doc['counters']['by_kind']}")
    print(
        f"с санкцией: {doc['counters']['with_sanction']}, "
        f"без: {doc['counters']['without_sanction']}"
    )
    print(
        f"с source_act: {doc['counters']['with_source_act']}, "
        f"без: {doc['counters']['without_source_act']}"
    )
    print(f"с датами ЖЦ: {doc['counters']['with_lifecycle_dates']} (сейчас в БД их 0 — см. докстринг)")


if __name__ == "__main__":
    main()
