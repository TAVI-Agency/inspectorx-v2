"""Шаги 'scope' и 'lifecycle' Build-конвейера (Задача 20, ADR-0003 «Блок 2»,
ADR-0004 «Товарный каталог»).

## 'scope' — Classifier (mid-тир), БЕЗ Verifier

Читает ПЕРВОИСТОЧНИК нормы — `ctx.data['norm_fragment'].content` (тот же
принцип, что и у Rule-maker в `steps_rule.py`: машинное решение обязано
опираться на исходный текст, а не на `summary`) — и относит требование к
конкретному типу товара/услуги каталога `catalog.product_types` (ADR-0004,
«Ключевое правило»: карточки требований привязываются ТОЛЬКО к
`product_type_id`), либо к `all_products`/`all_services`, если норма
действует на все товары/услуги без разбора.

Кандидаты привязки — НЕ хардкод в системном промпте, а живой список из
`BuildStore.list_group_product_types(group_ref)` (типы, чей код начинается с
`group_ref` — тот же `group_ref`, что и у `Cartographer.build_map`, весь
Build-прогон идёт по ОДНОЙ группе, см. `cartographer.py`): конструктор шага
принимает `group_ref` явным параметром — тот же паттерн, что и `jurisdiction`
у `NormStep` (`steps_norm.py`) — `pipeline.items`/`ItemContext` эту величину
не несут (тот же пробел, что и с `jurisdiction`/`rationale`, см. докстринг
`steps_norm.py:_map_item_from_ctx`), устранение — вне рамок этой задачи.

Результат — `ctx.data['scope'] = {"kind": ..., "product_type_id": ...}`:
- `kind='product_type'` -> `product_type_id` ОБЯЗАН быть одним из id
  кандидатов — иначе невалидный ответ;
- `kind='all_products'`/`'all_services'` -> `product_type_id=None`, кандидаты
  не сверяются (норма общего действия, а не привязанная к конкретному типу).

Невалидный ответ (не тот `kind`, либо `product_type_id` не из кандидатов при
`kind='product_type'`) -> один ретрай с указанием ошибки -> всё ещё невалиден
-> `StepResult(fail)` (тот же паттерн, что и `category_slug` в
`steps_classify.py`).

Verifier на этот шаг НЕ вешаем — решение контроллера задачи (в плане/CSV у
'scope' нет verifier-строки): `StepResult.verdicts` у 'scope' всегда пуст.

## 'lifecycle' — Classifier (cheap-тир) + Verifier профилем «Норма»

Тоже читает `ctx.data['norm_fragment'].content` (+ `valid_from`/`valid_to`
самого фрагмента, если LegalX их вернул — подсказка модели, а не источник
истины) и извлекает ТОЛЬКО даты жизненного цикла требования — `effective_from`
(вступление в силу), `transition_until` (конец переходного периода),
`valid_to` (утрата силы), `repealed_by_ref` (акт-отменитель) — БЕЗ статуса:
`active`/`repealed`/`pending` — вычисляемое поле БД (Задача 9,
`20260731...lifecycle_status` view), не результат LLM.

Каждое из трёх датовых полей — `'YYYY-MM-DD'` либо `null`; все `null`
одновременно — валидный исход (норма бессрочна и не отменена), не ошибка.
Невалидный формат (не `YYYY-MM-DD`/`null`, включая календарно невозможные
даты вроде месяца 99) -> один ретрай с указанием ошибки -> всё ещё невалиден
-> `StepResult(fail)`, Verifier вообще не вызывается (тот же порядок, что и
Rule-maker -> Verifier в `steps_rule.py`: сначала валидный вывод producer'а,
потом независимая проверка).

Verifier проверяет извлечённые даты независимо от источника (`fragment` —
JSON дат, `source` — исходный текст нормы, тот же приём, что у `SummaryStep`
в `steps_norm.py`); `passed=False` -> `StepResult(fail)`. Producer — тир
`cheap`, Verifier — `verifier_model_for('cheap') == 'expensive'` (правило
Блока 2, `agents.py`).

## Почему шаги ловят исключения сами

Тот же принцип, что и во всех остальных шагах (`steps_norm.py`/
`steps_classify.py`/`steps_rule.py`): `Orchestrator._run_from`
(`orchestrator.py`) вызывает `step_fn(ctx)` БЕЗ try/except вокруг вызова —
необработанное исключение прервало бы весь `run_group`, а не только текущий
айтем. `AgentLLMError`/`ValueError` здесь перехватываются и превращаются в
обычный `StepResult(fail)`.

## Регистрация

Тот же паттерн отсрочки, что и у всех предыдущих шагов: `_default_llm_runner`
падает `NotImplementedError` только при РЕАЛЬНОМ вызове модели, не при
импорте/регистрации. `ScopeStep` при регистрации по умолчанию получает
заглушечный `group_ref=""` (`_STUB_GROUP_REF`) — реальный `group_ref`
подставляется живым прогоном (Задача 27), который конструирует шаг заново со
значением из карты, а не берёт синглтон из реестра как есть (тот же
компромисс, что и `DEFAULT_JURISDICTION` у `NormStep`).
"""
from __future__ import annotations

import json
import re
from datetime import date

from importer.build.agents import (
    Classifier,
    ModelsConfig,
    Verdict,
    Verifier,
    load_models_config,
    verifier_model_for,
)
from importer.build.legalx import NormFragment
from importer.build.llm_client import AgentLLMClient, AgentLLMError, RunnerAgentLLM
from importer.build.orchestrator import BuildStore
from importer.build.profiles import Profile
from importer.build.steps import ItemContext, StepResult, register_step

# ══════════════════════════════════════════════════════════════════════════
# 'scope'
# ══════════════════════════════════════════════════════════════════════════

_SCOPE_KINDS = ("product_type", "all_products", "all_services")

SCOPE_PROFILE = Profile(
    name="scope",  # вне ProfileName Literal в profiles.py — тот же прецедент,
    # что и 'rule' в steps_rule.py: реестр профилей опционален (докстринг
    # profiles.py), Literal не проверяется в рантайме.
    system_prompt=(
        "Ты определяешь область действия требования комплаенс-чеклиста по "
        "тексту нормы права: конкретный тип товара/услуги ИЗ СПИСКА "
        "кандидатов (kind='product_type', product_type_id — id кандидата), "
        "либо 'all_products'/'all_services', если норма действует на все "
        "товары или все услуги без разбора (тогда product_type_id — null)."
    ),
    response_schema={
        "type": "object",
        "properties": {
            "kind": {"type": "string", "enum": list(_SCOPE_KINDS)},
            "product_type_id": {"type": ["string", "null"]},
        },
        "required": ["kind", "product_type_id"],
    },
    tier="mid",
)


def _validate_scope(data: object, valid_ids: set[str]) -> dict | None:
    """Достаёт `{"kind", "product_type_id"}` из ответа классификатора либо
    `None`, если ответ не проходит контракт — сигнал «невалидный ответ ->
    ретрай»: `kind` не из `_SCOPE_KINDS`, либо `kind='product_type'` с
    `product_type_id`, которого нет среди кандидатов."""
    if not isinstance(data, dict):
        return None
    kind = data.get("kind")
    if kind not in _SCOPE_KINDS:
        return None
    if kind == "product_type":
        product_type_id = data.get("product_type_id")
        if not isinstance(product_type_id, str) or product_type_id not in valid_ids:
            return None
        return {"kind": kind, "product_type_id": product_type_id}
    return {"kind": kind, "product_type_id": None}


class ScopeStep:
    """Шаговый callable 'scope' (см. докстринг модуля)."""

    def __init__(
        self,
        llm: AgentLLMClient,
        store: BuildStore,
        *,
        group_ref: str,
        models: ModelsConfig | None = None,
        profile: Profile = SCOPE_PROFILE,
    ):
        self._llm = llm
        self._store = store
        self._group_ref = group_ref
        self._models = models or load_models_config()
        self._profile = profile
        self._classifier = Classifier(llm, self._models)

    def __call__(self, ctx: ItemContext) -> StepResult:
        fragment = ctx.data.get("norm_fragment")
        if fragment is None:
            return StepResult(
                status="fail",
                error=(
                    "шаг 'scope': в item_ctx нет 'norm_fragment' — шаг 'norm' "
                    "ещё не отработал"
                ),
            )
        try:
            return self._run(ctx, fragment)
        except (AgentLLMError, ValueError) as exc:
            return StepResult(status="fail", error=f"шаг 'scope': {exc}")

    def _run(self, ctx: ItemContext, fragment: NormFragment) -> StepResult:
        candidates = self._store.list_group_product_types(self._group_ref)
        valid_ids = {c["id"] for c in candidates}

        profile = self._make_profile(candidates)
        result = self._classifier.run(fragment.content, profile)
        scope = _validate_scope(result, valid_ids)

        if scope is None:
            retry_profile = self._make_profile(
                candidates,
                error_message=(
                    f"Предыдущий ответ {result!r} невалиден: 'kind' обязан быть "
                    "одним из 'product_type'/'all_products'/'all_services'; при "
                    "kind='product_type' 'product_type_id' обязан быть ОДНИМ ИЗ "
                    "id кандидатов ниже, никакое другое значение не допускается."
                ),
            )
            result = self._classifier.run(fragment.content, retry_profile)
            scope = _validate_scope(result, valid_ids)

        if scope is None:
            return StepResult(
                status="fail",
                error=(
                    "шаг 'scope': классификатор дважды вернул невалидный ответ "
                    f"({result!r}) — не тот kind, либо product_type_id не из кандидатов"
                ),
            )

        ctx.data["scope"] = scope
        return StepResult(status="ok")

    def _make_profile(self, candidates: list[dict], error_message: str = "") -> Profile:
        """Профиль с кандидатами привязки в промпте — из `candidates`
        (живой список стора), не хардкод."""
        candidates_str = "; ".join(
            f"id={c['id']} код={c.get('hs_code') or c.get('unspsc_code')} "
            f"название={c['name_ru']}"
            for c in candidates
        ) or "(кандидатов нет — используй только all_products/all_services)"

        system_prompt = self._profile.system_prompt
        if error_message:
            system_prompt = f"{system_prompt}\n\n{error_message}"
        system_prompt += f"\n\nКандидаты привязки: {candidates_str}"

        return Profile(
            name=self._profile.name,
            system_prompt=system_prompt,
            response_schema=self._profile.response_schema,
            tier=self._profile.tier,
        )


# ══════════════════════════════════════════════════════════════════════════
# 'lifecycle'
# ══════════════════════════════════════════════════════════════════════════

_LIFECYCLE_DATE_FIELDS = ("effective_from", "transition_until", "valid_to")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

LIFECYCLE_PROFILE = Profile(
    name="lifecycle",  # тот же прецедент, что и 'scope'/'rule' — вне Literal
    system_prompt=(
        "Ты извлекаешь из фрагмента нормы права ТОЛЬКО даты жизненного цикла "
        "требования — БЕЗ статуса (действует/утратило силу вычисляется "
        "отдельно, не тобой): effective_from (дата вступления в силу), "
        "transition_until (дата окончания переходного периода, если "
        "установлен), valid_to (дата утраты силы, если установлена), "
        "repealed_by_ref (ссылка на акт-отменитель, если применимо). Каждое "
        "датовое поле — строго 'YYYY-MM-DD' либо null. Если норма бессрочна "
        "и не отменена — все поля null. Ничего не придумывай: дата попадает "
        "в ответ, только если она явно указана в тексте фрагмента."
    ),
    response_schema={
        "type": "object",
        "properties": {
            "effective_from": {"type": ["string", "null"]},
            "transition_until": {"type": ["string", "null"]},
            "valid_to": {"type": ["string", "null"]},
            "repealed_by_ref": {"type": ["string", "null"]},
        },
        "required": ["effective_from", "transition_until", "valid_to", "repealed_by_ref"],
    },
    tier="cheap",
)


def _is_valid_date_or_null(value: object) -> bool:
    if value is None:
        return True
    if not isinstance(value, str) or not _DATE_RE.match(value):
        return False
    try:
        date.fromisoformat(value)
    except ValueError:
        return False  # синтаксически похоже на дату, но календарно невозможна
    return True


def _validate_lifecycle(data: object) -> dict | None:
    """Достаёт даты жизненного цикла из ответа экстрактора либо `None`, если
    ответ не проходит контракт (не объект, отсутствует датовое поле,
    невалидный формат хотя бы одной даты, `repealed_by_ref` не строка/null)
    — сигнал «невалидный ответ -> ретрай»."""
    if not isinstance(data, dict):
        return None
    for field_name in _LIFECYCLE_DATE_FIELDS:
        if field_name not in data or not _is_valid_date_or_null(data[field_name]):
            return None
    repealed_by_ref = data.get("repealed_by_ref")
    if repealed_by_ref is not None and not isinstance(repealed_by_ref, str):
        return None
    return {
        "effective_from": data["effective_from"],
        "transition_until": data["transition_until"],
        "valid_to": data["valid_to"],
        "repealed_by_ref": repealed_by_ref,
    }


class LifecycleStep:
    """Шаговый callable 'lifecycle' (см. докстринг модуля)."""

    def __init__(
        self,
        llm: AgentLLMClient,
        *,
        models: ModelsConfig | None = None,
        profile: Profile = LIFECYCLE_PROFILE,
    ):
        self._llm = llm
        self._models = models or load_models_config()
        self._profile = profile
        self._extractor = Classifier(llm, self._models)

    def __call__(self, ctx: ItemContext) -> StepResult:
        fragment = ctx.data.get("norm_fragment")
        if fragment is None:
            return StepResult(
                status="fail",
                error=(
                    "шаг 'lifecycle': в item_ctx нет 'norm_fragment' — шаг "
                    "'norm' ещё не отработал"
                ),
            )
        try:
            return self._run(ctx, fragment)
        except (AgentLLMError, ValueError) as exc:
            return StepResult(status="fail", error=f"шаг 'lifecycle': {exc}")

    def _run(self, ctx: ItemContext, fragment: NormFragment) -> StepResult:
        text = self._fragment_text(fragment)

        lifecycle = self._extract(text, self._profile)
        if lifecycle is None:
            retry_profile = self._profile_with_error(
                "Предыдущий ответ содержал невалидный формат даты — каждое "
                "датовое поле обязано быть строго 'YYYY-MM-DD' либо null."
            )
            lifecycle = self._extract(text, retry_profile)

        if lifecycle is None:
            return StepResult(
                status="fail",
                error=(
                    "шаг 'lifecycle': экстрактор дважды вернул невалидный "
                    "формат дат (не 'YYYY-MM-DD'/null)"
                ),
            )

        producer_model = self._models.tiers[self._profile.tier]
        verifier_model = verifier_model_for(producer_model, self._models)
        verifier = Verifier(llm=self._llm, model=verifier_model)

        verdict: Verdict = verifier.run(
            question="Даты жизненного цикла точно соответствуют фрагменту нормы?",
            fragment=json.dumps(lifecycle, ensure_ascii=False, sort_keys=True),
            source=fragment.content,
            profile=self._profile,
        )

        if not verdict.passed:
            return StepResult(
                status="fail",
                verdicts=[verdict],
                error=verdict.reason or "шаг 'lifecycle': верификатор не подтвердил даты",
            )

        ctx.data["lifecycle"] = lifecycle
        return StepResult(status="ok", verdicts=[verdict])

    def _extract(self, text: str, profile: Profile) -> dict | None:
        result = self._extractor.run(text, profile)
        return _validate_lifecycle(result)

    @staticmethod
    def _fragment_text(fragment: NormFragment) -> str:
        """Текст нормы + даты самого фрагмента (если LegalX их вернул) как
        подсказка модели — источник истины всё равно текст, даты фрагмента
        лишь ориентир (докстринг модуля)."""
        parts = [fragment.content]
        if fragment.valid_from is not None:
            parts.append(f"(фрагмент нормы действует с {fragment.valid_from.isoformat()})")
        if fragment.valid_to is not None:
            parts.append(f"(фрагмент нормы действует по {fragment.valid_to.isoformat()})")
        return "\n".join(parts)

    def _profile_with_error(self, error_message: str) -> Profile:
        return Profile(
            name=self._profile.name,
            system_prompt=f"{self._profile.system_prompt}\n\n{error_message}",
            response_schema=self._profile.response_schema,
            tier=self._profile.tier,
        )


# ══════════════════════════════════════════════════════════════════════════
# Регистрация (см. докстринг модуля)
# ══════════════════════════════════════════════════════════════════════════


def _default_llm_runner(prompt: str, model: str) -> str:
    """Заглушка runner'а для регистрации по умолчанию — падает только при
    РЕАЛЬНОМ вызове модели, не при импорте/регистрации шага."""
    raise NotImplementedError(
        "Живой LLM-runner для шагов 'scope'/'lifecycle' ещё не подключён — "
        "заработает после пилотного прогона Задачи 27 (см. "
        "importer/build/llm_client.py:RunnerAgentLLM)"
    )


class _DummyStore:
    """Заглушка BuildStore для регистрации 'scope' без живого хранилища."""

    def list_group_product_types(self, group_ref: str) -> list[dict]:
        return []


# Заглушечный group_ref для регистрации по умолчанию — реальный прогон
# (Задача 27) конструирует ScopeStep заново со значением из карты, не берёт
# синглтон из реестра как есть (см. докстринг модуля).
_STUB_GROUP_REF = ""

_default_llm = RunnerAgentLLM(_default_llm_runner)
register_step("scope", ScopeStep(_default_llm, _DummyStore(), group_ref=_STUB_GROUP_REF))
register_step("lifecycle", LifecycleStep(_default_llm))
