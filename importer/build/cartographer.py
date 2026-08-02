"""Cartographer (Задача 15, ADR-0003): двухуровневая карта требований для
товарной/сервисной группы — стоп-точка ① конвейера (`global-constraints.md`).

`Cartographer.build_map(group_ref, jurisdiction)` — один deep-research
LLM-вызов expensive-тира: промпт просит модель сначала изучить мировую
практику (~50 стран-бенчмарков по этой группе), затем сформулировать,
какие из найденных требований конкретно применимы в заданной юрисдикции.
Веб-доступ в код НЕ встраивается — промпт сформулирован так, будто модель
уже умеет искать в вебе (реальная обвязка — на живом бэкенде, подключение
которого решение контроллера отнесло к пилотному прогону Задачи 27, см.
`task-15-brief.md`); здесь это обычный вызов через `AgentLLMClient`.

Ответ — JSON-массив объектов `{expected_item, category_slug, rationale,
benchmark_countries}` (схема зафиксирована брифом Задачи 15). Валидация
после ответа: `category_slug`, которого нет в `BuildStore.list_category_slugs()`
(= `public.requirement_categories`, ось NTM), — айтем НЕ идёт в карту, а
откладывается в `CartographerReport.candidate_categories` («кандидат новой
категории», решение грила №3 — таксономию расширяет только явный апрув
владельца, не сама LLM). Карта при этом всё равно сохраняется как `draft`,
пусть и неполной — остальные валидные айтемы не должны ждать разбора
кандидатов.

Апрув/реджект карты — не методы Cartographer, а прямые вызовы
`BuildStore.set_map_status` (дёргает CLI `build approve-map` /
`build reject-map`, `importer/cli.py`): Cartographer только строит и
(пере)сохраняет `draft`.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field

from importer.build.agents import ModelsConfig, load_models_config
from importer.build.llm_client import AgentLLMClient, AgentLLMError
from importer.build.orchestrator import BuildStore

# Cartographer — дорогой, редкий вызов (раз на группу×юрисдикцию, не на
# айтем), поэтому фиксированный тир, а не Profile.tier конкретного шага.
CARTOGRAPHER_TIER = "expensive"

_REQUIRED_FIELDS = ("expected_item", "category_slug", "rationale", "benchmark_countries")

_SYSTEM_PROMPT = (
    "Ты — Cartographer, эксперт по мировой практике технического "
    "регулирования внешней торговли (санитарные и фитосанитарные меры, "
    "техрегламенты и сертификация, маркировка и упаковка, лицензии и "
    "разрешения, налоги и фискальные сборы, валютный контроль, таможенные "
    "процедуры, правила происхождения). У тебя есть доступ к открытым "
    "источникам в вебе."
)


class CartographerLLMError(AgentLLMError):
    """Ответ Cartographer-LLM не распарсился или не соответствует схеме
    `[{expected_item, category_slug, rationale, benchmark_countries}]`."""


@dataclass
class CartographerReport:
    """Итог `build_map`: сохранённая draft-карта + отсеянные валидацией
    айтемы (кандидаты новых категорий), которые НЕ попали в `payload`."""

    map_id: str
    group_ref: str
    jurisdiction: str
    items_count: int
    candidate_categories: list[dict] = field(default_factory=list)


class Cartographer:
    def __init__(
        self,
        store: BuildStore,
        llm: AgentLLMClient,
        *,
        tier: str = CARTOGRAPHER_TIER,
        models: ModelsConfig | None = None,
    ):
        self._store = store
        self._llm = llm
        self._tier = tier
        self._models = models or load_models_config()

    def build_map(self, group_ref: str, jurisdiction: str) -> CartographerReport:
        model = self._models.tiers[self._tier]
        valid_slugs = set(self._store.list_category_slugs())

        prompt = self._build_prompt(group_ref, jurisdiction, valid_slugs)
        answer = self._llm.complete(prompt, model)
        raw_items = self._parse_answer(answer)

        accepted: list[dict] = []
        candidates: list[dict] = []
        for entry in raw_items:
            if entry["category_slug"] in valid_slugs:
                accepted.append(entry)
            else:
                candidates.append(entry)

        map_id = self._store.save_map(group_ref, jurisdiction, accepted)
        return CartographerReport(
            map_id=map_id,
            group_ref=group_ref,
            jurisdiction=jurisdiction,
            items_count=len(accepted),
            candidate_categories=candidates,
        )

    # ── внутреннее ───────────────────────────────────────────────────────

    @staticmethod
    def _build_prompt(group_ref: str, jurisdiction: str, valid_slugs: set[str]) -> str:
        slugs_line = ", ".join(sorted(valid_slugs)) or "(список пуст)"
        return (
            f"{_SYSTEM_PROMPT}\n\n"
            f"Группа: {group_ref}\n"
            f"Юрисдикция: {jurisdiction}\n"
            f"Известные category_slug (используй ТОЛЬКО их, не выдумывай новые): {slugs_line}\n\n"
            "Построй карту требований в две стадии:\n"
            "1) мировая практика — исследуй ~50 стран-бенчмарков по этой "
            "товарной/сервисной группе (крупнейшие торговые юрисдикции и "
            "профильные регуляторы для этой группы);\n"
            "2) для каждой найденной практики сформулируй expected_item — "
            f"конкретное требование, ожидаемое именно в юрисдикции {jurisdiction}.\n\n"
            "Ответь СТРОГО JSON-массивом объектов вида "
            '{"expected_item": "...", "category_slug": "...", "rationale": "...", '
            '"benchmark_countries": ["..."]}. Ничего, кроме JSON-массива, в ответе быть не должно.'
        )

    @staticmethod
    def _parse_answer(answer: str) -> list[dict]:
        try:
            data = json.loads(answer)
        except json.JSONDecodeError as exc:
            raise CartographerLLMError(f"Cartographer: LLM вернула не-JSON: {answer!r}") from exc
        if not isinstance(data, list):
            raise CartographerLLMError(
                f"Cartographer: ожидался JSON-массив карты, получено: {answer!r}"
            )
        for entry in data:
            if not isinstance(entry, dict) or any(f not in entry for f in _REQUIRED_FIELDS):
                raise CartographerLLMError(
                    f"Cartographer: элемент карты не соответствует схеме "
                    f"{_REQUIRED_FIELDS}: {entry!r}"
                )
        return data
