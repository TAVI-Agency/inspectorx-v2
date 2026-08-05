"""Шаг 'load' Build-конвейера (Задача 26, ADR-0003 «Блок 2»).

Пишет `ctx.data['card']` (собранный шагом 'assemble', `assembler.py`) в БД
через `BuildStore.save_requirement_draft` — чистые данные, ноль LLM-вызовов
в этом шаге вообще.

## Идемпотентность перепрогонов — `external_key`

`external_key = f"{group_ref}:{jurisdiction}:{slug(expected_item)}"`.
`group_ref`/`jurisdiction` — параметры конструктора (тот же пробел и тот же
паттерн решения, что и `ScopeStep.group_ref`/`NormStep.jurisdiction` в
`steps_scope_lifecycle.py`/`steps_norm.py`: ни `ItemRecord`, ни
`ItemContext.data` эти значения не несут). `slug(...)` — стабильный ХЭШ
нормализованного `expected_item` (`_slugify` ниже), НЕ транслитерация
кириллицы в читаемый URL-слаг: `expected_item` почти всегда русский текст,
наивный regex `[^a-z0-9]+` схлопнул бы ЛЮБУЮ кириллическую строку в один и
тот же слаг («item») — коллизия external_key у РАЗНЫХ требований одной
группы. Технический хэш решает это корректно и остаётся детерминированным
(тот же `expected_item` при перезапуске конвейера даёт тот же `external_key`
→ `save_requirement_draft` апсертит в ТУ ЖЕ строку `requirements`, а не
плодит дубли).

## Upsert + replace-семантика

`save_requirement_draft` (Protocol `BuildStore`, `orchestrator.py`) апсертит
`requirements` по `external_key`, а `requirement_contents`/`_details`/
`_applicability`/`_rules` — ПОЛНОСТЬЮ заменяет набор строк требования (не
merge построчно): повторный `load` того же айтема с изменившейся карточкой
не оставляет «осиротевших» старых строк (например, старый uz-перевод после
того, как язык перевода сменился).

**Фикс-раунд ревью Задачи 26 (Important): published не откатывается.**
Карточка от 'assemble' несёт `status='draft'` ВСЕГДА, но апсерт может
попасть в уже `published` строку (тот же `external_key` — например,
ре-ревью флоу Задачи 27+ гоняет 'load' повторно по уже опубликованному
требованию, обновляя контент). `save_requirement_draft` в этом случае
**не откатывает статус** обратно в `draft` — контент обновляется как
обычно (ре-ревью флоу контролирует корректность контента выше по потоку),
только `status` строки остаётся `published`; факт сохранения помечается
через `store.set_item_note(item_id, 'existing published, status preserved')`.

## Дедуп-скип

Если `ctx.data['dedup']['duplicate_of']` задан (шаг 'dedup', Задача 25) —
'load' НЕ пишет вторую карточку под то же требование: помечает
`pipeline.items.last_error = 'duplicate_of=<id>'` через новый метод
`BuildStore.set_item_note` (отдельный от `update_item_status(...,
last_error=...)`, потому что это не ошибка последней попытки шага, а
постоянная пометка айтема) и всё равно переводит статус в `draft_loaded` —
тот же терминальный для этого шага статус, что и у обычной загрузки: айтем
прошёл конвейер целиком, просто не породил новую строку `requirements`.

## `status='draft'` ВСЕГДА

Карточка приходит от 'assemble' уже с `status='draft'` (см.
`assembler.py:AssembleStep._build_card`) — публикация (`draft -> published`)
не входит в эту задачу (Задача 27, менеджер исключений/пилотный прогон).

## `authority_name` -> `authority_id`

`card['requirement']['authority_name']` (строка либо `None`) резолвится в
`authority_id` через `BuildStore.find_or_create_authority` ПЕРЕД записью —
`requirements.authority_id` это FK, не текстовое поле.

## `pipeline.items.requirement_id`

После успешной записи шаг привязывает айтем к созданному/обновлённому
требованию — `BuildStore.update_item_status` расширен необязательным
kwarg'ом `requirement_id` (та же сигнатура, что и `last_error`, обратная
совместимость с существующими вызовами без него сохранена).
"""
from __future__ import annotations

import hashlib

from importer.build.orchestrator import BuildStore
from importer.build.steps import ItemContext, StepResult, register_step
from importer.build.steps_norm import DEFAULT_JURISDICTION


def _slugify(text: str) -> str:
    """Стабильный ТЕХНИЧЕСКИЙ слаг для `external_key` (см. докстринг
    модуля) — не для показа пользователю, поэтому короткий хэш
    нормализованного текста, а не читаемая транслитерация кириллицы."""
    normalized = " ".join(text.strip().lower().split())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]


class LoadStep:
    """Шаговый callable 'load' (см. докстринг модуля)."""

    def __init__(
        self,
        store: BuildStore,
        *,
        group_ref: str,
        jurisdiction: str = DEFAULT_JURISDICTION,
    ):
        self._store = store
        self._group_ref = group_ref
        self._jurisdiction = jurisdiction

    def __call__(self, ctx: ItemContext) -> StepResult:
        try:
            return self._run(ctx)
        except (ValueError, KeyError) as exc:
            return StepResult(status="fail", error=f"шаг 'load': {exc}")

    def _run(self, ctx: ItemContext) -> StepResult:
        dedup = ctx.data.get("dedup") or {}
        duplicate_of = dedup.get("duplicate_of")
        if duplicate_of:
            self._store.set_item_note(ctx.item.id, f"duplicate_of={duplicate_of}")
            self._store.update_item_status(ctx.item.id, "draft_loaded")
            return StepResult(status="ok")

        card = ctx.data.get("card")
        if card is None:
            return StepResult(
                status="fail",
                error=(
                    "шаг 'load': в item_ctx нет 'card' — шаг 'assemble' ещё "
                    "не отработал"
                ),
            )

        requirement = dict(card["requirement"])
        authority_name = requirement.pop("authority_name", None)
        requirement["authority_id"] = (
            self._store.find_or_create_authority(authority_name)
            if authority_name
            else None
        )

        jurisdiction = requirement.get("jurisdiction", self._jurisdiction)
        requirement["external_key"] = (
            f"{self._group_ref}:{jurisdiction}:{_slugify(ctx.item.expected_item)}"
        )

        resolved_card = {**card, "requirement": requirement}
        requirement_id = self._store.save_requirement_draft(
            resolved_card, item_id=ctx.item.id
        )

        self._store.update_item_status(
            ctx.item.id, "draft_loaded", requirement_id=requirement_id
        )
        return StepResult(status="ok")


def _default_store() -> BuildStore:
    """Заглушка `BuildStore` для регистрации по умолчанию — тот же принцип
    отсрочки, что и `_DummyStore` в `steps_classify.py`/`steps_dedup.py`:
    падает только при РЕАЛЬНОМ обращении к хранилищу, не при импорте/
    регистрации шага. Живое подключение (`SupabaseBuildStore` с реальным
    `group_ref` карты) — Задача 27."""

    class _DummyStore:
        def set_item_note(self, item_id: str, note: str) -> None:
            raise NotImplementedError(
                "Живой BuildStore для шага 'load' ещё не подключён — "
                "заработает после пилотного прогона Задачи 27"
            )

        def update_item_status(self, item_id: str, status: str, **_kwargs) -> None:
            raise NotImplementedError(
                "Живой BuildStore для шага 'load' ещё не подключён — "
                "заработает после пилотного прогона Задачи 27"
            )

        def save_requirement_draft(self, card: dict, *, item_id: str) -> str:
            raise NotImplementedError(
                "Живой BuildStore для шага 'load' ещё не подключён — "
                "заработает после пилотного прогона Задачи 27"
            )

        def find_or_create_authority(self, name: str) -> str:
            raise NotImplementedError(
                "Живой BuildStore для шага 'load' ещё не подключён — "
                "заработает после пилотного прогона Задачи 27"
            )

    return _DummyStore()


# Заглушечный group_ref для регистрации по умолчанию — реальный прогон
# (Задача 27) конструирует LoadStep заново со значением из карты, не берёт
# синглтон из реестра как есть (тот же компромисс, что и `_STUB_GROUP_REF`
# в steps_scope_lifecycle.py).
_STUB_GROUP_REF = ""
register_step("load", LoadStep(_default_store(), group_ref=_STUB_GROUP_REF))
