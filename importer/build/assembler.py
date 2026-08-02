"""Шаг 'assemble' Build-конвейера (Задача 26, ADR-0003 «Блок 2»,
`docs/TARGET_FORMAT.md` §4 «Анатомия требования»).

## Что делает Assembler

Собирает ПОЛНУЮ карточку требования (`ctx.data['card']`) из кусков,
накопленных шагами 'norm'..'dedup' (Задачи 17–25) + недостающих атрибутов
уровня 0, которых НИ ОДИН из предыдущих шагов не производит:

- `title_verb` — заголовок-глагол («Получить ветеринарный сертификат до
  ввоза»);
- `deontic` — obligation/prohibition/permission;
- `addressee_roles` — непустой список ролей ИЗ `public.party_role`
  (`initial_schema`: producer/importer/exporter/seller/carrier/all — ровно
  этот набор, БЕЗ `service_provider`, добавленного более поздней миграцией
  `20260712100000_services_module.sql`, — решение контроллера задачи);
- `authority_name` — название ведомства либо `null`, если по тексту
  определить нельзя (нет отдельного гейта на этот случай: `authority_id`
  в БД nullable, TARGET_FORMAT перечисляет ведомство как «обязательно», но
  контроллер задачи явно снял это требование как gap-триггер — см. ниже);
- `sanction_summary_line` — санкция ОДНОЙ строкой.

Один LLM-вызов (Classifier, тир 'mid') со схемой на все пять полей сразу;
вход — суть требования (`summary`), первоисточник (`norm_fragment.content`)
и структурированные санкции (`ctx.data['sanctions']`), чтобы модель не
изобретала сумму штрафа, а форматировала то, что уже нашёл шаг 'sanctions'.
Невалидный ответ → один ретрай с перечнем пробелов → всё ещё невалиден →
`StepResult(fail)` с тем же перечнем в `error` (НЕ исключение — решение
контроллера задачи, `task-26-brief.md` формулирует это как «исключение», но
уточнение контроллера явно поправляет: `StepResult` fail, не raise, тот же
режим отказа, что и у всех остальных producer-без-Verifier шагов, см.
`steps_scope_lifecycle.py:ScopeStep`/`steps_rule.py:RuleStep`).

## Обязательные поля уровня 0 (gap-триггеры)

TARGET_FORMAT §4 перечисляет уровень 0 как «заголовок-глагол, деонтика,
адресат, ведомство, санкция одной строкой» — все «да» (обязательны). На
практике `requirements.authority_id` в схеме БД nullable (FK `on delete set
null`, без `not null`), и уточнение контроллера задачи прямо снимает
ведомство с списка триггеров пробела: «нет ведомства — это ок». Реальные
gap-триггеры — `title_verb` и `sanction_summary_line` (плюс базовая
структурная валидность `deontic`/`addressee_roles`, чтобы не положить в БД
заведомо испорченный enum/массив). `sanction_summary_line` при отсутствии
санкций (`ctx.data['sanctions_not_found']` либо пустой список) код
ПЕРЕЗАПИСЫВАЕТ канонической фразой «санкция не установлена» независимо от
того, что вернула модель — тот же принцип «статус не собирается, а
вычисляется», что и у lifecycle-статуса (TARGET_FORMAT §4 «Дополнение
02.08.2026 а»): единственный устойчивый инвариант («санкций нет» — уже
известный код-факт из шага 'sanctions') не должен зависеть от того, что
придумает LLM на пустом месте.

## Пейволл-раскладка (TARGET_FORMAT §4, «Дополнение… в»)

`card['contents']['ru']` — ТОЛЬКО тизер (title + sanction_summary,
бесплатно). Всё «мясо» (description/how_to_comply/documents/sanctions/
court_cases/templates/lawyer_instruction/status_note) — `card['details']['ru']`
(платная граница — RLS на уровне таблицы `requirement_details`, не эта
задача, см. `docs/adr/0001…` пейволла). Пустые блоки (`court_cases`/
`templates`/`lawyer_instruction`/`status_note`) остаются `None`/`[]` РОВНО
как их положили шаги 22/23 (`steps_cases.py`/`steps_samples_lawyer.py`) —
код здесь НЕ схлопывает `None` и `[]` в одно значение: разница
«не применимо» vs «искали, не нашли» полезна как метаданные, витрина обе
формы показывает одинаково («Данных пока нет»).

## Второй язык (`ctx.data['translations']`, если шаг 'translate' переводил)

**Фикс-раунд ревью Задачи 26 (Important)**: первая версия переиспользовала
RU `title_verb`/`sanction_summary_line` буквально в `card['contents'][lang]`,
помечая их `translation_origin='machine'` — непереведённый текст под меткой
«машинный перевод» вводит в заблуждение (пользователь на UZ/EN версии видел
бы русский заголовок, подписанный как переведённый). Исправлено: Assembler
**НЕ создаёт** `card['contents'][lang]` вовсе. Тизер второго языка
отсутствует — витрина фолбэкнется на `contents['ru']` (решение
контроллера); настоящий перевод title/sanction_summary остаётся
ОТЛОЖЕННЫМ follow-up'ом (см. ниже), а не хаком с ложной меткой.

`card['details'][lang]` строится **ТОЛЬКО** из полей, которые
`ctx.data['translations']` реально несёт (`steps_translate.py:_build_payload`
переводит именно эти четыре: summary/lawyer_instruction/status_note/
sanctions[].measure) — `description`/`how_to_comply`/`lawyer_instruction`/
`status_note`/`sanctions` (санкции — те же article/amount, что и в RU, ТОЛЬКО
`extra` заменён на перевод, см. `_translate_sanctions`). `documents`/
`court_cases`/`templates` в `details[lang]` НЕ переносятся из RU (та же
причина, что и у `contents[lang]` — это непереведённый RU-текст: названия
шаблонов, судебных дел, заметки): `documents` остаётся `[]` (NOT NULL
DEFAULT в схеме — не может быть `None`), `court_cases`/`templates` —
`None` («данных пока нет на этом языке», честно, а не переиспользованный
чужой язык). `translation_origin='machine'` — эти поля ДЕЙСТВИТЕЛЬНО
переведены.

Пробел (title/sanction_summary второго языка, `contents[lang]` отсутствует
целиком) остаётся ОТКРЫТЫМ: 'translate' (Задача 24) в STEP_ORDER идёт ДО
'assemble' (Задача 26), значит title_verb/sanction_summary_line физически
не существуют в момент перевода. Кандидат-решение — перенести 'assemble'
перед 'translate' в STEP_ORDER (список шагов фиксирован брифом Задачи 14—
менять его сейчас, ОТДЕЛЬНОЙ ревизией мастер-плана, НЕ этим фикс-раундом) —
NOT DONE здесь по прямому решению контроллера ревью.

русские тексты (`contents['ru']`, `details['ru']`) — `translation_origin=None`
(наши, не переводы, а не третье значение enum — их NULL, не `'verbatim'`:
`verbatim` зарезервирован под дословный текст источника, см.
`20260717120000_translation_origin.sql`).

## Дедуп-скип

Если `ctx.data['dedup']['duplicate_of']` задан (шаг 'dedup', Задача 25,
нашёл дубль среди уже загруженных айтемов прогона) — Assembler пропускает
работу целиком: `StepResult(ok)`, `ctx.data['card'] = None`, ноль обращений
к LLM. Публикация/мердж дубля в существующее требование — обязанность шага
'load' (`steps_load.py`), этот шаг лишь не производит вторую карточку под
то же требование.

## `citations` — ИЗВЕСТНЫЙ ПРОБЕЛ, не заполняется

`requirement_citations.paragraph_id` — жёсткий FK (`not null`, `on delete
restrict`) на `public.act_paragraphs`, ЛОКАЛЬНУЮ таблицу InspectorX.
`ctx.data['norm_fragment']` — результат LegalX (`docs/adr/0005`), ДРУГОЙ
Supabase-проект (`docs/adr/0002-ecosystem-topology.md`): `fragment_id`
LegalX не тот же идентификатор, что `act_paragraphs.id` InspectorX,
прямой связи нет. Синхронизация LegalX-фрагмент → локальный `act_paragraphs`
— отдельный ETL, которого сейчас нигде в конвейере нет; выдумывать
`paragraph_id` здесь означало бы либо нарушить FK, либо вставить
произвольную locale-строку не под тем актом. `card['citations']` остаётся
пустым списком; `steps_load.py` эту секцию не трогает. Список «Produces» в
брифе Задачи 26 и не требует `requirement_citations` (перечисляет только
requirements/contents/details/applicability/rules) — согласуется с этим
решением.
"""
from __future__ import annotations

import json
from decimal import Decimal

from importer.build.agents import Classifier, ModelsConfig, load_models_config
from importer.build.llm_client import AgentLLMClient, AgentLLMError, RunnerAgentLLM
from importer.build.profiles import Profile
from importer.build.steps import ItemContext, StepResult, register_step
from importer.build.steps_norm import DEFAULT_JURISDICTION

# requirements.operation (operation_domain enum) — NOT NULL БЕЗ дефолта в
# схеме (20260711120000_initial_schema.sql), но НИ ОДИН шаг STEP_ORDER
# 17–25 эту ось не классифицирует — известный пробел (то же семейство, что
# jurisdiction/rationale в steps_norm.py:_map_item_from_ctx). 'product' —
# самое частое значение существующих строк (см. 20260711130000_v1_content.sql).
DEFAULT_OPERATION = "product"

# TARGET_FORMAT §4, уровень 0 — валидные значения ИЗ initial_schema (решение
# контроллера: НЕ 'service_provider', добавленный более поздней миграцией
# 20260712100000_services_module.sql — см. докстринг модуля).
_VALID_DEONTIC = ("obligation", "prohibition", "permission")
_VALID_PARTY_ROLES = ("producer", "importer", "exporter", "seller", "carrier", "all")

SANCTION_NOT_ESTABLISHED = "санкция не установлена"

ASSEMBLE_PROFILE = Profile(
    name="assemble",  # вне ProfileName Literal в profiles.py — тот же
    # прецедент, что и 'scope'/'rule'/'lawyer' в соседних шаговых модулях.
    system_prompt=(
        "Ты добираешь недостающие ОБЯЗАТЕЛЬНЫЕ атрибуты уровня 0 карточки "
        "требования комплаенс-чеклиста (docs/TARGET_FORMAT.md §4) по сути "
        "требования и тексту нормы: title_verb — короткий заголовок-глагол "
        '(например "Получить ветеринарный сертификат до ввоза"); deontic — '
        "obligation (обязанность) / prohibition (запрет) / permission "
        "(разрешение-льгота); addressee_roles — непустой список ролей "
        "адресата СТРОГО из producer/importer/exporter/seller/carrier/all; "
        "authority_name — название ведомства, ответственного за исполнение, "
        "или null, если по тексту нормы это определить нельзя; "
        "sanction_summary_line — санкция ОДНОЙ строкой вида "
        '"штраф до N ЕДИНИЦ", используя приведённые ниже структурированные '
        "санкции (не придумывай сумму от себя — бери её из данных), либо "
        f'"{SANCTION_NOT_ESTABLISHED}", если санкций нет.'
    ),
    response_schema={
        "type": "object",
        "properties": {
            "title_verb": {"type": "string"},
            "deontic": {"type": "string", "enum": list(_VALID_DEONTIC)},
            "addressee_roles": {
                "type": "array",
                "items": {"type": "string", "enum": list(_VALID_PARTY_ROLES)},
                "minItems": 1,
            },
            "authority_name": {"type": ["string", "null"]},
            "sanction_summary_line": {"type": "string"},
        },
        "required": [
            "title_verb", "deontic", "addressee_roles",
            "authority_name", "sanction_summary_line",
        ],
    },
    tier="mid",
)


def _validate_level0(data: object) -> tuple[dict | None, list[str]]:
    """Достаёт `{title_verb, deontic, addressee_roles, authority_name,
    sanction_summary_line}` из ответа Assembler'а либо `None` + перечень
    пробелов — сигнал «невалидный ответ -> ретрай -> (если снова невалиден)
    fail с этим же перечнем в error» (докстринг модуля: ведомство В ЭТОТ
    перечень не попадает — nullable, не gap-триггер)."""
    if not isinstance(data, dict):
        return None, ["весь ответ не JSON-объект"]

    gaps: list[str] = []

    title_verb = data.get("title_verb")
    if not isinstance(title_verb, str) or not title_verb.strip():
        gaps.append("заголовок-глагол (title_verb)")

    deontic = data.get("deontic")
    if deontic not in _VALID_DEONTIC:
        gaps.append("деонтика (deontic)")

    addressee_roles = data.get("addressee_roles")
    valid_roles = (
        isinstance(addressee_roles, list)
        and len(addressee_roles) > 0
        and all(isinstance(r, str) and r in _VALID_PARTY_ROLES for r in addressee_roles)
    )
    if not valid_roles:
        gaps.append("адресат (addressee_roles)")

    authority_name = data.get("authority_name")
    if authority_name is not None and not isinstance(authority_name, str):
        gaps.append("ведомство (authority_name) — неверный тип ответа")

    sanction_summary_line = data.get("sanction_summary_line")
    if not isinstance(sanction_summary_line, str) or not sanction_summary_line.strip():
        gaps.append("санкция одной строкой (sanction_summary_line)")

    if gaps:
        return None, gaps

    return {
        "title_verb": title_verb.strip(),
        "deontic": deontic,
        "addressee_roles": addressee_roles,
        "authority_name": authority_name,
        "sanction_summary_line": sanction_summary_line.strip(),
    }, []


def _context_text(ctx: ItemContext) -> str:
    """Вход Assembler'а: суть + первоисточник + структурированные санкции
    (докстринг модуля — «не придумывай сумму от себя»)."""
    parts = [f"Требование: {ctx.item.expected_item}"]
    summary = ctx.data.get("summary")
    if summary:
        parts.append(f"Суть: {summary}")
    fragment = ctx.data.get("norm_fragment")
    if fragment is not None:
        parts.append(f"Текст нормы: {fragment.content}")
    sanctions = ctx.data.get("sanctions")
    if sanctions:
        parts.append(f"Санкции (структурированные): {json.dumps(sanctions, ensure_ascii=False)}")
    else:
        parts.append(f"Санкции: не найдены ({SANCTION_NOT_ESTABLISHED})")
    return "\n".join(parts)


def _format_amount(fine: dict) -> str:
    amount = fine.get("amount")
    if isinstance(amount, float) and amount.is_integer():
        amount = int(amount)
    unit = fine.get("unit", "")
    return f"{amount} {unit}".strip()


def _documents_from_templates(templates: list[dict] | None) -> list[dict]:
    """`requirement_details.documents` — NOT NULL DEFAULT '[]', никогда
    `None`. Источник — 'samples' (Задача 23): найденный образец документа И
    ЕСТЬ тот самый документ уровня 1 («что, где взять» — TARGET_FORMAT §4)."""
    if not templates:
        return []
    return [
        {"name": t["name"], "where_to_get": t.get("source_url"), "note": t.get("note")}
        for t in templates
    ]


def _sanctions_for_details(sanctions: list[dict]) -> list[dict]:
    """`requirement_details.sanctions` (полная форма уровня 1) — NOT NULL
    DEFAULT '[]'. `amount` — ТЕКСТ (сумма + единица), не число: колонка
    документирована как text в 20260711120000_initial_schema.sql."""
    return [
        {
            "amount": _format_amount(s["fine"]),
            "article": s.get("article"),
            "extra": s.get("measure"),
        }
        for s in sanctions
    ]


def _translate_sanctions(sanctions: list[dict], translated_measures: list[str]) -> list[dict]:
    """Тот же список санкций, что и `_sanctions_for_details`, но `extra`
    (мера) заменена на перевод ИЗ `ctx.data['translations']['sanctions_measures']`
    — тем же позиционным фильтром «только санкции с непустым measure», каким
    `steps_translate.py:_build_payload` строит исходный список для перевода
    (иначе позиции разъедутся: `sanctions_measures` короче полного списка
    санкций, если у части нет `measure`)."""
    measures_iter = iter(translated_measures)
    result = []
    for s in sanctions:
        measure = s.get("measure")
        extra = next(measures_iter, measure) if measure else None
        result.append({
            "amount": _format_amount(s["fine"]),
            "article": s.get("article"),
            "extra": extra,
        })
    return result


def _court_cases_for_details(court_cases: list[dict] | None) -> list[dict] | None:
    """`None`/`[]`/список — семантика сохраняется РОВНО как её положил шаг
    'cases' (докстринг модуля). Ключ `summary_line` (steps_cases.py) →
    `summary` (документированное имя колонки, `20260803160000_details_rules.sql`);
    `amount` — `Decimal|None` (legalx.py:CourtCase) → `str`, jsonb не
    сериализует Decimal напрямую."""
    if court_cases is None:
        return None
    result = []
    for c in court_cases:
        amount = c.get("amount")
        result.append({
            "case_url": c.get("case_url"),
            "case_title": c.get("case_title"),
            "summary": c.get("summary_line", c.get("summary")),
            "outcome": c.get("outcome"),
            "amount": str(amount) if isinstance(amount, Decimal) else amount,
        })
    return result


class AssembleStep:
    """Шаговый callable 'assemble' (см. докстринг модуля)."""

    def __init__(
        self,
        llm: AgentLLMClient,
        *,
        jurisdiction: str = DEFAULT_JURISDICTION,
        models: ModelsConfig | None = None,
        profile: Profile = ASSEMBLE_PROFILE,
    ):
        self._llm = llm
        self._jurisdiction = jurisdiction
        self._models = models or load_models_config()
        self._profile = profile
        self._classifier = Classifier(llm, self._models)

    def __call__(self, ctx: ItemContext) -> StepResult:
        dedup = ctx.data.get("dedup") or {}
        if dedup.get("duplicate_of"):
            # Дубль — карточка НЕ собирается (докстринг модуля): пропускаем
            # работу целиком, ни одного обращения к LLM.
            ctx.data["card"] = None
            return StepResult(status="ok")
        try:
            return self._run(ctx)
        except (AgentLLMError, ValueError) as exc:
            return StepResult(status="fail", error=f"шаг 'assemble': {exc}")

    def _run(self, ctx: ItemContext) -> StepResult:
        text = _context_text(ctx)

        level0, gaps = self._extract(text, self._profile)
        if level0 is None:
            retry_profile = self._profile_with_error(
                "Предыдущий ответ был невалиден — отсутствуют или некорректны "
                f"обязательные поля: {', '.join(gaps)}. Верни СТРОГО JSON со "
                "всеми полями по схеме, ничего не пропускай."
            )
            level0, gaps = self._extract(text, retry_profile)

        if level0 is None:
            return StepResult(
                status="fail",
                error=(
                    "шаг 'assemble': карточка без обязательных полей уровня 0 — "
                    f"{', '.join(gaps)}"
                ),
            )

        card = self._build_card(ctx, level0)
        ctx.data["card"] = card
        return StepResult(status="ok")

    def _extract(self, text: str, profile: Profile) -> tuple[dict | None, list[str]]:
        try:
            result = self._classifier.run(text, profile)
        except AgentLLMError as exc:
            return None, [f"ответ LLM не JSON: {exc}"]
        return _validate_level0(result)

    def _profile_with_error(self, error_message: str) -> Profile:
        return Profile(
            name=self._profile.name,
            system_prompt=f"{self._profile.system_prompt}\n\n{error_message}",
            response_schema=self._profile.response_schema,
            tier=self._profile.tier,
        )

    def _build_card(self, ctx: ItemContext, level0: dict) -> dict:
        summary = ctx.data.get("summary")
        lifecycle = ctx.data.get("lifecycle") or {}
        scope = ctx.data.get("scope") or {"kind": None, "product_type_id": None}
        rules = ctx.data.get("rules") or []
        lawyer_instruction = ctx.data.get("lawyer_instruction")
        status_note = ctx.data.get("status_note")
        sanctions = ctx.data.get("sanctions") or []
        sanctions_not_found = bool(ctx.data.get("sanctions_not_found")) or not sanctions
        court_cases = ctx.data.get("court_cases")
        templates = ctx.data.get("templates")

        sanction_summary_line = (
            SANCTION_NOT_ESTABLISHED if sanctions_not_found else level0["sanction_summary_line"]
        )

        details_ru = {
            "description": summary or None,
            "how_to_comply": list(lawyer_instruction["steps"]) if lawyer_instruction else [],
            "documents": _documents_from_templates(templates),
            "sanctions": _sanctions_for_details(sanctions),
            "court_cases": _court_cases_for_details(court_cases),
            "templates": templates,
            "lawyer_instruction": lawyer_instruction,
            "status_note": status_note,
            "translation_origin": None,
        }

        card: dict = {
            "requirement": {
                "status": "draft",
                "jurisdiction": self._jurisdiction,
                "category_slug": ctx.data.get("category_slug"),
                "deontic": level0["deontic"],
                "addressee_roles": level0["addressee_roles"],
                "authority_name": level0["authority_name"],
                "operation": DEFAULT_OPERATION,
                "origin": "ai_pipeline",
                "effective_from": lifecycle.get("effective_from"),
                "transition_until": lifecycle.get("transition_until"),
                "valid_to": lifecycle.get("valid_to"),
                "repealed_by_ref": lifecycle.get("repealed_by_ref"),
            },
            "contents": {
                "ru": {
                    "title": level0["title_verb"],
                    "sanction_summary": sanction_summary_line,
                    "translation_origin": None,
                },
            },
            "details": {"ru": details_ru},
            "applicability": {
                "scope": scope.get("kind"),
                "product_type_id": scope.get("product_type_id"),
            },
            "rules": rules,
            "citations": [],  # известный пробел — см. докстринг модуля
        }

        translations = ctx.data.get("translations")
        if translations:
            # Фикс-раунд ревью Задачи 26 (Important): НЕ создаём
            # card['contents'][lang] — title/sanction_summary второго языка
            # не существуют (translate идёт раньше assemble в STEP_ORDER,
            # см. докстринг модуля «Второй язык») и переиспользование RU
            # текста под меткой translation_origin='machine' вводит в
            # заблуждение. details[lang] несёт ТОЛЬКО поля, которые
            # ctx.data['translations'] реально перевёл — documents/
            # court_cases/templates НЕ переносятся из RU (тот же непереведённый
            # текст), остаются пустыми/None.
            lang = translations["lang"]
            translated_lawyer = translations.get("lawyer_instruction")
            card["details"][lang] = {
                "description": translations.get("summary"),
                "how_to_comply": list(translated_lawyer["steps"]) if translated_lawyer else [],
                "documents": [],
                "sanctions": _translate_sanctions(
                    sanctions, translations.get("sanctions_measures") or []
                ),
                "court_cases": None,
                "templates": None,
                "lawyer_instruction": translated_lawyer,
                "status_note": translations.get("status_note"),
                "translation_origin": "machine",
            }

        return card


def _default_llm_runner(prompt: str, model: str) -> str:
    """Заглушка runner'а для регистрации по умолчанию (см. докстринг
    модуля) — падает только при РЕАЛЬНОМ вызове модели, не при
    импорте/регистрации шага."""
    raise NotImplementedError(
        "Живой LLM-runner для шага 'assemble' ещё не подключён — заработает "
        "после пилотного прогона Задачи 27 (см. "
        "importer/build/llm_client.py:RunnerAgentLLM)"
    )


_default_llm = RunnerAgentLLM(_default_llm_runner)
register_step("assemble", AssembleStep(_default_llm))
