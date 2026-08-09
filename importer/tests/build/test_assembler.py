"""Шаг 'assemble' (Задача 26, ADR-0003 «Блок 2»): Assembler по контракту
`docs/TARGET_FORMAT.md` §4.

Сценарии из докстринга `assembler.py`/task-26-brief.md:

- happy-path: карточка собрана полностью, пейволл-раскладка верна (тизер —
  ТОЛЬКО title+sanction_summary в `contents['ru']`, «мясо» — в
  `details['ru']`);
- отсутствие заголовка/санкции-строки (после ретрая) -> `StepResult(fail)`
  с перечнем пробелов в `error`, НЕ исключение;
- ретрай: первый ответ невалиден, второй валиден -> успех;
- dedup-скип: `ctx.data['dedup']['duplicate_of']` задан -> `card=None`, ноль
  обращений к LLM;
- `sanctions_not_found`/пустые санкции -> `sanction_summary` ВСЕГДА
  «санкция не установлена», код перезаписывает ответ LLM;
- переводы (`ctx.data['translations']`) -> `contents`/`details` второго
  языка, `translation_origin='machine'`; русские тексты — `None`.

LLM — только инжектируемый скрипт ответов (тот же паттерн, что и
`test_steps_scope_lifecycle.py`/`test_steps_rule.py`: ScriptedLLM, никакой сети).
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date

from importer.build.assembler import (
    ASSEMBLE_PROFILE,
    SANCTION_NOT_ESTABLISHED,
    AssembleStep,
)
from importer.build.legalx import NormFragment
from importer.build.steps import ItemContext, ItemRecord

# ── тестовые дублёры ────────────────────────────────────────────────────


@dataclass
class ScriptedLLM:
    """Мок AgentLLMClient: отдаёт ответы по очереди, фиксирует все (prompt, model)."""

    responses: list[str]
    calls: list[tuple[str, str]] = field(default_factory=list)

    def complete(self, prompt: str, model: str) -> str:
        self.calls.append((prompt, model))
        if not self.responses:
            raise AssertionError("ScriptedLLM: запросили ответ сверх скрипта — лишний вызов LLM")
        return self.responses.pop(0)


def fragment(**over) -> NormFragment:
    base = dict(
        fragment_id="frag-1", act_id="act-1", act_title="ПКМ-290",
        article_ref="п. 5", anchor="#p5",
        content="акцизная марка обязательна на пачках сигарет с фильтром",
        act_status="active", valid_from=date(2020, 1, 1), valid_to=None, score=1.0,
    )
    return NormFragment(**{**base, **over})


SANCTIONS = [
    {"article": "ст. 128 КоАО", "fine": {"amount": 50, "unit": "БРВ"}, "measure": "конфискация партии"},
]

RULES = [{"rule": {"field": "состав", "lang": "uz", "required": True}, "verified": True}]

LIFECYCLE = {
    "effective_from": "2026-01-01", "transition_until": None,
    "valid_to": None, "repealed_by_ref": None,
}

SCOPE = {"kind": "product_type", "product_type_id": "pt-1"}

LAWYER_INSTRUCTION = {
    "verdict": "Требование применимо, нужно получить марку до ввоза партии",
    "steps": ["Подать заявку в Комветнадзор", "Получить марку", "Нанести на упаковку"],
}


def item_ctx(
    *,
    summary: str | None = "Нужна акцизная марка на сигареты с фильтром до ввоза",
    with_norm_fragment: bool = True,
    sanctions: list[dict] | None = SANCTIONS,
    sanctions_not_found: bool = False,
    category_slug: str | None = "marking",
    rules: list[dict] | None = RULES,
    scope: dict | None = SCOPE,
    lifecycle: dict | None = LIFECYCLE,
    lawyer_instruction: dict | None = LAWYER_INSTRUCTION,
    status_note: str | None = None,
    court_cases: object = "UNSET",
    templates: object = "UNSET",
    translations: dict | None = None,
    dedup: dict | None = None,
    expected_item: str = "акцизная марка на пачке сигарет с фильтром",
) -> ItemContext:
    item = ItemRecord(id="item-1", run_id="run-1", expected_item=expected_item)
    ctx = ItemContext(item=item)
    if summary is not None:
        ctx.data["summary"] = summary
    if with_norm_fragment:
        ctx.data["norm_fragment"] = fragment()
    if sanctions is not None:
        ctx.data["sanctions"] = sanctions
    if sanctions_not_found:
        ctx.data["sanctions_not_found"] = True
    if category_slug is not None:
        ctx.data["category_slug"] = category_slug
    if rules is not None:
        ctx.data["rules"] = rules
    if scope is not None:
        ctx.data["scope"] = scope
    if lifecycle is not None:
        ctx.data["lifecycle"] = lifecycle
    if lawyer_instruction is not None:
        ctx.data["lawyer_instruction"] = lawyer_instruction
    ctx.data["status_note"] = status_note
    # court_cases/templates: None и "не задано вообще" — разные исходы,
    # поэтому дефолт — сентинел "UNSET", а не None.
    if court_cases != "UNSET":
        ctx.data["court_cases"] = court_cases
    if templates != "UNSET":
        ctx.data["templates"] = templates
    if translations is not None:
        ctx.data["translations"] = translations
    if dedup is not None:
        ctx.data["dedup"] = dedup
    return ctx


def level0_response(**over) -> str:
    base = dict(
        title_verb="Получить акцизную марку до ввоза партии",
        deontic="obligation",
        addressee_roles=["importer"],
        authority_name="Комветнадзор",
        sanction_summary_line="штраф до 50 БРВ",
    )
    return json.dumps({**base, **over}, ensure_ascii=False)


# ══════════════════════════════════════════════════════════════════════════
# happy path
# ══════════════════════════════════════════════════════════════════════════


def test_assemble_happy_path_builds_full_card():
    llm = ScriptedLLM(responses=[level0_response()])
    step = AssembleStep(llm)
    ctx = item_ctx(court_cases=None, templates=None)

    result = step(ctx)

    assert result.status == "ok"
    card = ctx.data["card"]
    assert card is not None
    assert len(llm.calls) == 1

    # requirement — уровень 0
    req = card["requirement"]
    assert req["status"] == "draft"
    assert req["deontic"] == "obligation"
    assert req["addressee_roles"] == ["importer"]
    assert req["authority_name"] == "Комветнадзор"
    assert req["category_slug"] == "marking"
    assert req["effective_from"] == "2026-01-01"

    # пейволл: тизер — ТОЛЬКО title+sanction_summary
    ru_contents = card["contents"]["ru"]
    assert set(ru_contents.keys()) == {"title", "sanction_summary", "translation_origin"}
    assert ru_contents["title"] == "Получить акцизную марку до ввоза партии"
    assert ru_contents["sanction_summary"] == "штраф до 50 БРВ"
    assert ru_contents["translation_origin"] is None  # наш текст, не перевод

    # мясо — в details
    ru_details = card["details"]["ru"]
    assert ru_details["description"] == ctx.data["summary"]
    assert ru_details["how_to_comply"] == LAWYER_INSTRUCTION["steps"]
    assert ru_details["lawyer_instruction"] == LAWYER_INSTRUCTION
    assert ru_details["sanctions"] == [
        {"amount": "50 БРВ", "article": "ст. 128 КоАО", "extra": "конфискация партии"}
    ]
    assert ru_details["translation_origin"] is None

    # applicability/rules
    assert card["applicability"]["scope"] == "product_type"
    assert card["applicability"]["product_type_id"] == "pt-1"
    assert card["rules"] == RULES

    # citations — известный пробел (докстринг assembler.py), всегда пуст
    assert card["citations"] == []


def test_assemble_happy_path_uses_mid_tier():
    llm = ScriptedLLM(responses=[level0_response()])
    step = AssembleStep(llm)

    step(item_ctx())

    assert ASSEMBLE_PROFILE.tier == "mid"
    assert llm.calls[0][1] == "claude-sonnet-5"  # models.yaml tiers.mid


def test_assemble_empty_blocks_stay_none_not_collapsed():
    """`court_cases`/`templates`/`lawyer_instruction`/`status_note` не заданы
    вообще (партиальный прогон без шагов 22/23) -> details несёт `None`,
    НЕ `[]` — контракт «Данных пока нет» (TARGET_FORMAT §4 «Дополнение… в»)."""
    llm = ScriptedLLM(responses=[level0_response()])
    step = AssembleStep(llm)
    ctx = item_ctx(
        lawyer_instruction=None, court_cases=None, templates=None, status_note=None,
    )

    result = step(ctx)

    assert result.status == "ok"
    details = ctx.data["card"]["details"]["ru"]
    assert details["lawyer_instruction"] is None
    assert details["status_note"] is None
    assert details["court_cases"] is None
    assert details["templates"] is None
    # NOT NULL DEFAULT '[]' поля — никогда None, даже без лоера
    assert details["how_to_comply"] == []
    assert details["documents"] == []


def test_assemble_court_cases_and_templates_found_are_mapped():
    llm = ScriptedLLM(responses=[level0_response()])
    step = AssembleStep(llm)
    templates = [{"name": "Форма 3-НДС", "source_url": "https://gov.uz/form3", "note": "официальный бланк"}]
    court_cases = [
        {
            "case_url": "https://sudx.uz/case/1", "case_title": "Дело №1",
            "summary_line": "штраф за отсутствие марки", "outcome": "штраф",
            "amount": 500000,
        }
    ]
    ctx = item_ctx(templates=templates, court_cases=court_cases)

    step(ctx)

    details = ctx.data["card"]["details"]["ru"]
    assert details["templates"] == templates
    assert details["documents"] == [
        {"name": "Форма 3-НДС", "where_to_get": "https://gov.uz/form3", "note": "официальный бланк"}
    ]
    # summary_line (steps_cases.py) -> summary (документированное имя колонки)
    assert details["court_cases"] == [
        {
            "case_url": "https://sudx.uz/case/1", "case_title": "Дело №1",
            "summary": "штраф за отсутствие марки", "outcome": "штраф",
            "amount": 500000,
        }
    ]


# ══════════════════════════════════════════════════════════════════════════
# обязательные поля уровня 0 — gap-триггеры
# ══════════════════════════════════════════════════════════════════════════


def test_assemble_missing_title_verb_retries_then_fails_with_gap_listed():
    llm = ScriptedLLM(responses=[
        level0_response(title_verb=""),
        level0_response(title_verb=""),
    ])
    step = AssembleStep(llm)
    ctx = item_ctx()

    result = step(ctx)

    assert result.status == "fail"
    assert "title_verb" in result.error
    assert len(llm.calls) == 2
    assert "card" not in ctx.data


def test_assemble_missing_sanction_summary_line_retries_then_fails():
    llm = ScriptedLLM(responses=[
        level0_response(sanction_summary_line=""),
        level0_response(sanction_summary_line=""),
    ])
    step = AssembleStep(llm)
    ctx = item_ctx()

    result = step(ctx)

    assert result.status == "fail"
    assert "sanction_summary_line" in result.error
    assert len(llm.calls) == 2


def test_assemble_invalid_response_recovers_on_retry():
    llm = ScriptedLLM(responses=[
        level0_response(title_verb=""),  # невалиден
        level0_response(),  # валиден
    ])
    step = AssembleStep(llm)
    ctx = item_ctx()

    result = step(ctx)

    assert result.status == "ok"
    assert len(llm.calls) == 2
    retry_prompt = llm.calls[1][0]
    assert "title_verb" in retry_prompt or "невалид" in retry_prompt.lower()


def test_assemble_missing_authority_name_is_not_a_gap():
    """`authority_name=null` — НЕ пробел (nullable в БД, уточнение
    контроллера задачи снимает ведомство с триггеров gap-fail)."""
    llm = ScriptedLLM(responses=[level0_response(authority_name=None)])
    step = AssembleStep(llm)
    ctx = item_ctx()

    result = step(ctx)

    assert result.status == "ok"
    assert ctx.data["card"]["requirement"]["authority_name"] is None


def test_assemble_invalid_deontic_is_a_gap():
    llm = ScriptedLLM(responses=[
        level0_response(deontic="not-a-real-deontic"),
        level0_response(deontic="not-a-real-deontic"),
    ])
    step = AssembleStep(llm)

    result = step(item_ctx())

    assert result.status == "fail"
    assert "deontic" in result.error


def test_assemble_empty_addressee_roles_is_a_gap():
    llm = ScriptedLLM(responses=[
        level0_response(addressee_roles=[]),
        level0_response(addressee_roles=[]),
    ])
    step = AssembleStep(llm)

    result = step(item_ctx())

    assert result.status == "fail"
    assert "addressee_roles" in result.error


# ══════════════════════════════════════════════════════════════════════════
# sanction_summary_line — код перезаписывает при отсутствии санкций
# ══════════════════════════════════════════════════════════════════════════


def test_sanctions_not_found_forces_canonical_sanction_summary():
    """Санкций нет -> `sanction_summary` ВСЕГДА «санкция не установлена»,
    даже если LLM вернула что-то другое — код не доверяет модели на
    единственном по-настоящему детерминированном факте."""
    llm = ScriptedLLM(responses=[level0_response(sanction_summary_line="что-то придуманное")])
    step = AssembleStep(llm)
    ctx = item_ctx(sanctions=[], sanctions_not_found=True)

    result = step(ctx)

    assert result.status == "ok"
    assert ctx.data["card"]["contents"]["ru"]["sanction_summary"] == SANCTION_NOT_ESTABLISHED
    assert ctx.data["card"]["details"]["ru"]["sanctions"] == []


def test_empty_sanctions_list_without_flag_also_forces_canonical_line():
    llm = ScriptedLLM(responses=[level0_response(sanction_summary_line="штраф до 10 БРВ")])
    step = AssembleStep(llm)
    ctx = item_ctx(sanctions=[])

    step(ctx)

    assert ctx.data["card"]["contents"]["ru"]["sanction_summary"] == SANCTION_NOT_ESTABLISHED


# ══════════════════════════════════════════════════════════════════════════
# dedup-скип
# ══════════════════════════════════════════════════════════════════════════


def test_dedup_duplicate_skips_assembly_entirely():
    llm = ScriptedLLM(responses=[])  # LLM вызываться не должна
    step = AssembleStep(llm)
    ctx = item_ctx(dedup={"duplicate_of": "item-original", "score": 0.95})

    result = step(ctx)

    assert result.status == "ok"
    assert ctx.data["card"] is None
    assert llm.calls == []


def test_dedup_without_duplicate_of_runs_normally():
    llm = ScriptedLLM(responses=[level0_response()])
    step = AssembleStep(llm)
    ctx = item_ctx(dedup={"duplicate_of": None})

    result = step(ctx)

    assert result.status == "ok"
    assert ctx.data["card"] is not None
    assert len(llm.calls) == 1


# ══════════════════════════════════════════════════════════════════════════
# переводы -> contents/details второго языка
# ══════════════════════════════════════════════════════════════════════════


TRANSLATIONS = {
    "lang": "uz",
    "summary": "Filtrli sigaretlar uchun aksiz markasi kerak",
    "lawyer_instruction": {
        "verdict": "Talab qo'llaniladi",
        "steps": ["Komvetnazoratga ariza berish", "Marka olish", "O'ramga qo'yish"],
    },
    "status_note": None,
    "sanctions_measures": ["partiyani musodara qilish"],
}


def test_translations_populate_details_second_lang_with_machine_origin():
    llm = ScriptedLLM(responses=[level0_response()])
    step = AssembleStep(llm)
    ctx = item_ctx(translations=TRANSLATIONS)

    step(ctx)

    card = ctx.data["card"]
    uz_details = card["details"]["uz"]
    assert uz_details["description"] == TRANSLATIONS["summary"]
    assert uz_details["lawyer_instruction"] == TRANSLATIONS["lawyer_instruction"]
    assert uz_details["how_to_comply"] == TRANSLATIONS["lawyer_instruction"]["steps"]
    assert uz_details["status_note"] is None
    assert uz_details["translation_origin"] == "machine"
    # measure переведена позиционно (одна санкция с measure -> один перевод)
    assert uz_details["sanctions"] == [
        {"amount": "50 БРВ", "article": "ст. 128 КоАО", "extra": "partiyani musodara qilish"}
    ]


def test_translations_second_lang_details_omit_untranslated_fields():
    """Фикс-раунд ревью Задачи 26 (Important): `documents`/`court_cases`/
    `templates` в details[lang] НЕ переносятся из RU — это непереведённый
    текст (названия шаблонов, судебные дела), а не то, что реально перевёл
    'translate'. `documents` — `[]` (NOT NULL DEFAULT в схеме, не `None`),
    `court_cases`/`templates` — `None` («данных пока нет на этом языке»)."""
    llm = ScriptedLLM(responses=[level0_response()])
    step = AssembleStep(llm)
    templates = [{"name": "Форма 3-НДС", "source_url": "https://gov.uz/form3", "note": "бланк"}]
    court_cases = [
        {
            "case_url": "https://sudx.uz/case/1", "case_title": "Дело №1",
            "summary_line": "штраф", "outcome": "штраф", "amount": 500000,
        }
    ]
    ctx = item_ctx(templates=templates, court_cases=court_cases, translations=TRANSLATIONS)

    step(ctx)

    uz_details = ctx.data["card"]["details"]["uz"]
    assert uz_details["documents"] == []
    assert uz_details["court_cases"] is None
    assert uz_details["templates"] is None
    # RU details по-прежнему несут непереведённые (свои) данные как есть
    ru_details = ctx.data["card"]["details"]["ru"]
    assert ru_details["documents"] != []
    assert ru_details["court_cases"] is not None
    assert ru_details["templates"] is not None


def test_translations_never_create_second_lang_contents():
    """Фикс-раунд ревью Задачи 26 (Important): непереведённый RU title/
    sanction_summary под меткой translation_origin='machine' вводит в
    заблуждение — Assembler НЕ создаёт card['contents'][lang] вовсе.
    Витрина фолбэкнется на contents['ru'] (решение контроллера)."""
    llm = ScriptedLLM(responses=[level0_response()])
    step = AssembleStep(llm)
    ctx = item_ctx(translations=TRANSLATIONS)

    step(ctx)

    card = ctx.data["card"]
    assert set(card["contents"].keys()) == {"ru"}
    assert "uz" not in card["contents"]


def test_ru_content_and_details_have_null_translation_origin():
    llm = ScriptedLLM(responses=[level0_response()])
    step = AssembleStep(llm)
    ctx = item_ctx(translations=TRANSLATIONS)

    step(ctx)

    card = ctx.data["card"]
    assert card["contents"]["ru"]["translation_origin"] is None
    assert card["details"]["ru"]["translation_origin"] is None


def test_no_translations_means_only_ru_lang_present():
    llm = ScriptedLLM(responses=[level0_response()])
    step = AssembleStep(llm)
    ctx = item_ctx(translations=None)

    step(ctx)

    card = ctx.data["card"]
    assert set(card["contents"].keys()) == {"ru"}
    assert set(card["details"].keys()) == {"ru"}


# ══════════════════════════════════════════════════════════════════════════
# без norm_fragment/summary — партиальный rerun
# ══════════════════════════════════════════════════════════════════════════


def test_assemble_works_without_norm_fragment_using_summary_only():
    """Партиальный `rerun_item`, начатый не с начала, может не иметь
    `norm_fragment` в контексте — шаг не должен падать `AttributeError`,
    только `summary`/`expected_item` уже достаточно для LLM-вызова."""
    llm = ScriptedLLM(responses=[level0_response()])
    step = AssembleStep(llm)
    ctx = item_ctx(with_norm_fragment=False)

    result = step(ctx)

    assert result.status == "ok"


# ══════════════════════════════════════════════════════════════════════════
# регистрация
# ══════════════════════════════════════════════════════════════════════════


def test_assemble_step_is_registered_in_steps_registry():
    from importer.build.steps import get_step

    assert callable(get_step("assemble"))


def test_load_default_steps_imports_assembler_module():
    from importer.build.steps import get_step, load_default_steps

    load_default_steps()  # идемпотентно

    assert callable(get_step("assemble"))
    assert callable(get_step("load"))
