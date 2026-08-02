#!/usr/bin/env python3
"""Синтетический сквозной прогон Build-конвейера — Задача 27.

## Почему СИНТЕТИЧЕСКИЙ, а не «пилот с реальным LLM»

Переопределение шага 3 брифа (решение контроллера, task-27-brief.md): живого
LLM-ключа нет. Вместо реального контентного пилота с апрувом Абдурахмона —
СИНТЕТИЧЕСКИЙ сквозной прогон на ЛОКАЛЬНОМ Supabase: настоящий
`SupabaseBuildStore` и настоящая локальная БД (`supabase db reset --local`),
но LLM и LegalX — детерминированные скрипты, не сеть. Цель — доказать, что
сквозная сшивка конвейера (Задача 27: `load_default_steps`-гэп,
`build_step_registry`, coverage, автопубликация, менеджер исключений)
физически работает от карты до строк `public.requirements`, а не проверить
качество контента. Настоящий контентный пилот с реальным LLM — отдельный
гейт после получения ключа (вне этой задачи).

## Почему часть шагов идёт в обход `importer.cli.main`, а не строго через CLI

Задача явно требует: «Апрув карты в синтетическом прогоне выполняется через
CLI approve-map (тех-прогон, задокументируй)» — только это явно предписано.
Карта («build map») ЗАПИСЫВАЕТСЯ РУКАМИ через `store.save_map` (тоже прямое
указание брифа) — реальный `build map` дёргает Cartographer с deep-research
LLM, которого нет. `build run`, в свою очередь, у боевого CLI строит реестр
шагов через `_build_llm_runner` (`importer/cli.py`) — заглушку, которая
падает `NotImplementedError` при первом же реальном вызове модели: для
СКРИПТОВАННОГО прогона нужна инъекция своего runner'а в Python, а не через
argv, поэтому `run` здесь — прямой вызов `Orchestrator(store,
steps=build_step_registry(...)).run_group(...)`, а не `cli.main([...])`.
`coverage`/`publish`, наоборот, НЕ требуют скриптованных бэкендов (только
`store`) — гоняются через настоящий `cli.main([...])`, показывая, что эти
две CLI-команды Задачи 27 реально работают на живом прогоне.

## Данные пилота — группа 2204/UZ (вино, не 2402/сигареты)

Контроллер: «2402 локально не засеяна» — верно для `catalog.product_types`
(локальный сид `20260803110000_catalog_seed.sql` несёт только группу 2204 —
вина, HS 220410/220421/220422/220429/220430). 2204/UZ — рукописная
draft-карта на 3 айтема:

1. «Указание страны происхождения на контрэтикетке импортного вина» —
   канонический айтем, проходит весь конвейер до draft_loaded/published;
2. «Маркировка страны происхождения на этикетке ввозимого вина» — ПЕРЕФРАЗ
   того же требования: шаг 'dedup' обязан признать его дублем айтема 1
   (проверка dedup);
3. «Цифровая прослеживаемость партии вина через единый реестр (нормы нет в
   законодательстве Узбекистана)» — намеренно НЕ содержит ключевых слов
   («этикетк»/«происхожд»), по которым `FakeLegalX` находит норму: шаг
   'norm' обязан вернуть `no_norm` (проверка терминального исхода без
   найденной нормы).

## Скрипты вместо сети

- `FakeLegalX` — свой мини-мок `LegalXClient` (НЕ `legalx_mock.MockLegalX`,
  у которого фикстуры только про сигареты — для группы 2204 они бы не
  сработали): по ключевым словам запроса либо отдаёт единственный
  синтетический `NormFragment` про маркировку вина, либо пусто.
  `search_cases` не вызывается в этом прогоне вовсе (сан кции намеренно не
  находятся — см. ниже) — оставлен пустым для полноты контракта.
- Scripted LLM runner (`_make_scripted_runner`) — единый диспетчер по
  УНИКАЛЬНЫМ маркерам текста промпта (system_prompt каждого профиля/шаблон
  обёртки Verifier/Classifier/Summarizer/Translator — см. комментарии в коде
  диспетчера); на любой нераспознанный промпт — `AssertionError` с текстом
  промпта, чтобы пилот падал ГРОМКО, а не тихо возвращал мусор.
- `FakeEmbedder` (`importer/build/embeddings.py`, уже существует, не новый
  код) — детерминированный bag-of-words хэш: айтемы 1 и 2 получают
  ОДИНАКОВЫЙ scripted-саммари текст -> идентичный вектор -> cosine=1.0 ->
  дедуп находит дубль БЕЗ обращения к LLM (порог `DUP_THRESHOLD_HIGH=0.9`).
- Санкции намеренно «не найдены» для ВСЕХ айтемов (упрощение синтетического
  прогона, не баг): `FakeLegalX.search_norms` отдаёт пусто на запрос с
  префиксом «ответственность за нарушение» -> шаг 'sanctions' сигналит
  `sanctions_not_found` -> шаг 'cases' пропускается совсем (ноль вызовов) ->
  `sanction_summary_line` в карточке — каноническая фраза «санкция не
  установлена» (код, не LLM, см. `assembler.py`).

## Запуск

Предпосылка — локальный Supabase поднят И актуален (все миграции этой ветки,
включая `20260803200000_pipeline_coverage_report.sql`, накатаны):

    supabase db start   # если ещё не поднят
    supabase db reset --local

Затем:

    .venv-importer/bin/python scripts/pilot_synthetic.py

Скрипт САМ проверяет, что `IX_SUPABASE_URL` указывает на `127.0.0.1`/
`localhost` (стоп, если нет) — писать в прод запрещено (global-constraints.md).
Идемпотентно по карте (повторный запуск переиспользует уже approved карту,
не пытается создать вторую) — по `pipeline.runs`/`items` НЕ идемпотентен
(каждый запуск создаёт новый прогон), но `public.requirements` идемпотентны
по `external_key`, повторные запуски не плодят дублей требований.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

GROUP_REF = "2204"
JURISDICTION = "UZ"

WINE_PRODUCT_TYPE_ID = "987847f1-cef0-a234-9dd5-e9b8cd6fd257"  # 220410 «вина игристые»

ITEM_1 = "Указание страны происхождения на контрэтикетке импортного вина"
ITEM_2 = "Маркировка страны происхождения на этикетке ввозимого вина"  # дубль ITEM_1
ITEM_3 = (
    "Цифровая прослеживаемость партии вина через единый реестр "
    "(нормы нет в законодательстве Узбекистана)"
)

# ВАЖНО про дедуп (объясняет, почему саммари — буквально ITEM_1, а не своя
# формулировка): `BuildStore.list_run_item_texts` (см. докстринг в
# orchestrator.py) — ИЗВЕСТНОЕ ограничение: кандидаты отдаются по
# `expected_item` (входной текст карты), НЕ по `summary`, которого
# `pipeline.items` не хранит. Шаг 'dedup' сравнивает ТЕКУЩИЙ айтем по его
# `summary` с КАНДИДАТАМИ по их `expected_item` — асимметрично. Чтобы дедуп
# айтема 2 (перефраз айтема 1 другими словами — "маркировка"/"этикетке"/
# "ввозимого" вместо "указание"/"контрэтикетке"/"импортного") детерминированно
# сработал через простой bag-of-words `FakeEmbedder` (без стемминга/синонимов),
# canned-саммари здесь — РОВНО текст ITEM_1: он и есть "канонический" вариант
# формулировки этого требования, к которому должны сойтись оба похожих
# айтема — реалистичный исход саммаризации короткого однострочного
# требования, а не хак ради теста.
WINE_SUMMARY_RU = ITEM_1
WINE_SUMMARY_UZ = (
    "Import qilingan sharob kontr-etiketkasida kelib chiqish davlati "
    "o'zbek va rus tillarida ko'rsatilishi shart."
)


def _load_local_supabase_env() -> dict[str, str]:
    """Читает `supabase status -o json` и возвращает `{IX_SUPABASE_URL,
    IX_SUPABASE_SERVICE_KEY}` ЛОКАЛЬНОГО стека. Падает громко, если локальный
    Supabase не поднят (`supabase db start`/`supabase status` не отвечают)."""
    result = subprocess.run(
        ["supabase", "status", "-o", "json"], capture_output=True, text=True, cwd=ROOT,
    )
    if result.returncode != 0:
        raise SystemExit(
            "supabase status упал — локальный стек не поднят? "
            f"stderr: {result.stderr}"
        )
    status = json.loads(result.stdout)
    url = status["API_URL"]
    key = status["SECRET_KEY"]
    if "127.0.0.1" not in url and "localhost" not in url:
        # Защита от прод-Supabase (global-constraints.md: «В прод-БД
        # напрямую не писать») — синтетический прогон обязан идти ТОЛЬКО в
        # локальную БД.
        raise SystemExit(f"IX_SUPABASE_URL={url!r} не похож на локальный — стоп")
    return {"IX_SUPABASE_URL": url, "IX_SUPABASE_SERVICE_KEY": key}


# python-dotenv (importer/db.py:load_dotenv) по умолчанию НЕ перезаписывает
# уже выставленные переменные окружения (override=False) — поэтому эти
# присвоения ДОЛЖНЫ произойти ДО первого импорта importer.db/importer.cli.
os.environ.update(_load_local_supabase_env())
print(f"[env] IX_SUPABASE_URL={os.environ['IX_SUPABASE_URL']} (локальный стек, подтверждено)")

from importer.build.embeddings import FakeEmbedder  # noqa: E402
from importer.build.legalx import CourtCase, NormFragment  # noqa: E402
from importer.build.orchestrator import Orchestrator, SupabaseBuildStore  # noqa: E402
from importer.build.registry import build_step_registry  # noqa: E402
from importer.db import ix_client  # noqa: E402
from importer.cli import main as cli_main  # noqa: E402


# ══════════════════════════════════════════════════════════════════════════
# мок-LegalX
# ══════════════════════════════════════════════════════════════════════════

SANCTIONS_QUERY_PREFIX = "ответственность за нарушение"

_WINE_FRAGMENT = NormFragment(
    fragment_id="synthetic-wine-fragment-1",
    act_id="synthetic-wine-act-1",
    act_title="Технический регламент о маркировке пищевой продукции (синтетика пилота)",
    article_ref="ст. 5",
    anchor="p5",
    content=(
        "Импортированное вино маркируется на контрэтикетке с указанием "
        "страны происхождения на государственном и русском языках."
    ),
    act_status="active",
    valid_from=None,
    valid_to=None,
    score=1.0,
)


class FakeLegalX:
    """Скриптованный `LegalXClient` пилота — НЕ `legalx_mock.MockLegalX`
    (тот на фикстурах про сигареты, для группы 2204 они бы не совпали).
    Детерминированно: находит норму про маркировку вина по ключевым словам,
    санкции — намеренно нигде не находит (упрощение, см. докстринг модуля)."""

    def __init__(self):
        self.calls: list[tuple[str, str]] = []

    def search_norms(
        self, query: str, jurisdiction: str, domains: list[str] | None = None, limit: int = 10,
    ) -> list[NormFragment]:
        self.calls.append((query, jurisdiction))
        if jurisdiction != "UZ":
            return []
        if query.startswith(SANCTIONS_QUERY_PREFIX):
            return []  # санкции намеренно не ищем в этом синтетическом прогоне
        lowered = query.lower()
        if "этикетк" in lowered or "происхожд" in lowered:
            return [_WINE_FRAGMENT]
        return []  # айтем 3 — намеренно отсутствующая норма (no_norm)

    def search_cases(
        self, article: str, topic: str | None = None, limit: int = 5,
    ) -> list[CourtCase]:
        # Не вызывается в этом прогоне (sanctions_not_found -> 'cases'
        # пропускает поиск целиком) — оставлен для полноты Protocol.
        return []


# ══════════════════════════════════════════════════════════════════════════
# scripted LLM runner
# ══════════════════════════════════════════════════════════════════════════

_REQUIREMENT_RE = re.compile(r"Требование: (.+)")


def _extract_requirement(prompt: str) -> str:
    m = _REQUIREMENT_RE.search(prompt)
    return m.group(1).strip() if m else ""


@dataclass
class ScriptedRunnerStats:
    calls: list[tuple[str, str]]

    def print_summary(self) -> None:
        print(f"[llm] всего скриптованных вызовов: {len(self.calls)}")


def make_scripted_runner() -> tuple[Callable[[str, str], str], ScriptedRunnerStats]:
    """Единый диспетчер по УНИКАЛЬНЫМ маркерам текста промпта — см. докстринг
    модуля. Каждая ветка ниже привязана к конкретному generic-агенту/шагу;
    нераспознанный промпт -> `AssertionError` (пилот обязан падать громко,
    не тихо генерировать мусор)."""
    stats = ScriptedRunnerStats(calls=[])

    def runner(prompt: str, model: str) -> str:
        stats.calls.append((model, prompt[:80].replace("\n", " ")))

        # question_writer.py:_build_prompt — генерация уточняющих вопросов.
        if "Question Writer, эксперт" in prompt:
            requirement = _extract_requirement(prompt)
            return json.dumps([
                {
                    "text": f"Какая норма устанавливает: {requirement}?",
                    "expected_schema": {"type": "object", "properties": {"content": {"type": "string"}}},
                },
                {
                    "text": f"Какой орган контролирует исполнение требования: {requirement}?",
                    "expected_schema": {"type": "object", "properties": {"content": {"type": "string"}}},
                },
            ], ensure_ascii=False)

        # agents.py:Retriever._reformulate_or_signal_no_norm — во ВСЕХ трёх
        # сценариях этого прогона (санкции айтемов 1-2, отсутствующая норма
        # айтема 3) сигналим "нормы нет", переформулировку не пробуем.
        if "Исходный запрос:" in prompt:
            return json.dumps({"no_norm": True})

        # agents.py:Verifier.run — общий маркер, одинаков для ЛЮБОГО шага
        # (norm/summary/category/lifecycle/sanctions/samples/translate).
        if "Проверь независимо" in prompt:
            return json.dumps({"passed": True, "reason": "синтетический прогон: подтверждено скриптом"})

        # agents.py:Summarizer.run — шаг 'summary' (steps_norm.py).
        if "Сформулируй краткое резюме." in prompt:
            return WINE_SUMMARY_RU

        # steps_classify.py:CLASSIFY_PROFILE — шаг 'category'.
        if "Ты классифицируешь требование" in prompt:
            return json.dumps({"category_slug": "tbt"})

        # steps_scope_lifecycle.py:SCOPE_PROFILE — шаг 'scope'.
        if "Ты определяешь область действия" in prompt:
            return json.dumps({"kind": "product_type", "product_type_id": WINE_PRODUCT_TYPE_ID})

        # steps_scope_lifecycle.py:LIFECYCLE_PROFILE — шаг 'lifecycle'.
        if "извлекаешь из фрагмента нормы права ТОЛЬКО даты" in prompt:
            return json.dumps({
                "effective_from": None, "transition_until": None,
                "valid_to": None, "repealed_by_ref": None,
            })

        # steps_samples_lawyer.py:SAMPLES_JUDGE_PROFILE — шаг 'samples' (судья).
        if "решаешь, нужен ли для этого требования" in prompt:
            return json.dumps({"needed": False, "document_type": None})

        # steps_samples_lawyer.py:LAWYER_PROFILE — шаг 'lawyer'.
        if "юрист-инхаус" in prompt:
            return json.dumps({
                "verdict": "Требование применимо к импортёру алкогольной продукции.",
                "steps": ["Нанести на контрэтикетку страну происхождения на узбекском и русском языках"],
                "status_note": None,
            }, ensure_ascii=False)

        # steps_translate.py:_translate — шаг 'translate'.
        if "Переведи следующие ИИ-тексты" in prompt:
            return json.dumps({
                "summary": WINE_SUMMARY_UZ,
                "lawyer_instruction": {
                    "steps": ["Kontr-etiketkaga kelib chiqish davlatini o'zbek va rus tillarida qo'shish"],
                    "verdict": "Talab importyor uchun amal qiladi.",
                },
                "status_note": None,
                "sanctions_measures": [],
            }, ensure_ascii=False)

        # assembler.py:ASSEMBLE_PROFILE — шаг 'assemble'.
        if "добираешь недостающие ОБЯЗАТЕЛЬНЫЕ атрибуты" in prompt:
            return json.dumps({
                "title_verb": "Указать страну происхождения на контрэтикетке импортного вина",
                "deontic": "obligation",
                "addressee_roles": ["importer"],
                "authority_name": "Агентство по техническому регулированию при Минторговли РУз",
                "sanction_summary_line": "санкция не установлена",
            }, ensure_ascii=False)

        raise AssertionError(f"pilot_synthetic: нет сценария для промпта: {prompt[:300]!r}")

    return runner, stats


# ══════════════════════════════════════════════════════════════════════════
# прогон
# ══════════════════════════════════════════════════════════════════════════


def _print_header(title: str) -> None:
    print()
    print("=" * 78)
    print(title)
    print("=" * 78)


def main() -> None:
    ix = ix_client()
    store = SupabaseBuildStore(ix)

    # ── шаг 1: карта — руками через store.save_map (НЕ Cartographer/LLM) ──
    _print_header("Шаг 1: карта 2204/UZ — записана руками через store.save_map")
    payload = [
        {"expected_item": ITEM_1, "category_slug": "tbt"},
        {"expected_item": ITEM_2, "category_slug": "tbt"},
        {"expected_item": ITEM_3, "category_slug": "tbt"},
    ]
    existing = (
        ix.schema("pipeline").table("maps").select("id, status")
        .eq("group_ref", GROUP_REF).eq("jurisdiction", JURISDICTION)
        .execute().data
    )
    if existing and existing[0]["status"] == "approved":
        map_id = existing[0]["id"]
        print(f"[map] переиспользуем уже одобренную карту {map_id} (повторный запуск скрипта)")
    else:
        map_id = store.save_map(GROUP_REF, JURISDICTION, payload)
        print(f"[map] карта {map_id} записана как draft, {len(payload)} айтема(ов)")

    # ── шаг 2: апрув — ЧЕРЕЗ РЕАЛЬНЫЙ CLI (тех-прогон стоп-точки ①) ───────
    _print_header("Шаг 2: апрув карты — через importer.cli build approve-map")
    cli_main(["build", "approve-map", "--map", map_id])

    # ── шаг 3: run — Orchestrator напрямую (скриптованный runner/LegalX) ──
    _print_header("Шаг 3: build run — Orchestrator(steps=build_step_registry(...))")
    runner, stats = make_scripted_runner()
    legalx = FakeLegalX()
    registry = build_step_registry(
        store, runner, legalx,
        group_ref=GROUP_REF, jurisdiction=JURISDICTION,
        embedder=FakeEmbedder(),
    )
    orchestrator = Orchestrator(store, steps=registry)
    # publish=False — публикацию делаем ОТДЕЛЬНЫМ явным шагом ниже (через
    # CLI `build publish`), чтобы в отчёте были видны все 5 действий брифа
    # (map/approve-map/run/coverage/publish) как различимые шаги.
    report = orchestrator.run_group(map_id, publish=False)
    stats.print_summary()
    print(
        f"[run] run_id={report.run_id} total={report.total_items} "
        f"draft_loaded={report.draft_loaded} no_norm={report.no_norm} "
        f"needs_attention={report.needs_attention} published={report.published}"
    )
    print(f"[legalx] всего вызовов search_norms: {len(legalx.calls)}")

    # ── шаг 4: coverage — ЧЕРЕЗ РЕАЛЬНЫЙ CLI ───────────────────────────────
    _print_header("Шаг 4: build coverage --run <id> — через importer.cli")
    cli_main(["build", "coverage", "--run", report.run_id])

    # ── шаг 5: publish — ЧЕРЕЗ РЕАЛЬНЫЙ CLI ────────────────────────────────
    _print_header("Шаг 5: build publish --run <id> — через importer.cli")
    cli_main(["build", "publish", "--run", report.run_id])

    # ── проверка: статусы items + requirements в БД ────────────────────────
    _print_header("Проверка: pipeline.items этого прогона")
    items = store.list_run_items(report.run_id)
    for item in items:
        print(f"  {item.id}  status={item.status:<16} req={item.requirement_id}  "
              f"last_error={item.last_error!r}  {item.expected_item[:60]!r}")

    _print_header("Проверка: public.requirements (external_key LIKE '2204:UZ:%')")
    rows = (
        ix.table("requirements").select("id, status, external_key, category_slug, deontic, published_at")
        .like("external_key", f"{GROUP_REF}:{JURISDICTION}:%")
        .execute().data
    )
    for row in rows:
        print(f"  {row['id']}  status={row['status']:<10} external_key={row['external_key']} "
              f"category={row['category_slug']} deontic={row['deontic']} published_at={row['published_at']}")
        contents = (
            ix.table("requirement_contents").select("lang, title, sanction_summary")
            .eq("requirement_id", row["id"]).execute().data
        )
        for c in contents:
            print(f"    contents[{c['lang']}]: title={c['title']!r} sanction_summary={c['sanction_summary']!r}")
        details = (
            ix.table("requirement_details").select("lang, description, translation_origin")
            .eq("requirement_id", row["id"]).execute().data
        )
        for d in details:
            print(f"    details[{d['lang']}]: description={d['description']!r} "
                  f"translation_origin={d['translation_origin']!r}")
        applicability = (
            ix.table("requirement_applicability").select("scope, product_type_id")
            .eq("requirement_id", row["id"]).execute().data
        )
        for a in applicability:
            print(f"    applicability: scope={a['scope']} product_type_id={a['product_type_id']}")

    print()
    print("готово.")


if __name__ == "__main__":
    main()
