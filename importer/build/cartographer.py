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

Режим `--research` (Задача 4, «ночь 11.09.2026»): если в конструктор
передан `toolkit` (`ResearchToolkit`, `importer/build/research.py`), веб-
доступ из докстринга выше становится реальным — `build_map` сначала одним
дешёвым LLM-вызовом просит план поисковых запросов (`_plan_queries`),
прогоняет его через `toolkit.gather(...)`, и только потом строит карту
вторым LLM-вызовом, промпт которого несёт найденные источники (блок
«Источники») и просит проставить у каждого айтема `sources` — URL, на
которые он опирается. Без `toolkit` (по умолчанию) поведение не меняется:
один LLM-вызов, промпт без источников — сохранённая совместимость с
Волной 2 (`task-15-brief.md`)."""
from __future__ import annotations

import json
from dataclasses import dataclass, field

from importer.build.agents import ModelsConfig, load_models_config
from importer.build.llm_client import AgentLLMClient, AgentLLMError
from importer.build.orchestrator import BuildStore
from importer.build.research import ResearchSource, ResearchToolkit

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
    # число реально собранных источников в режиме `--research` (Задача 4);
    # 0 без toolkit — дефолт, чтобы старые `CartographerReport(...)` в
    # тестах/коде не ломались новым полем.
    sources_used: int = 0


class Cartographer:
    def __init__(
        self,
        store: BuildStore,
        llm: AgentLLMClient,
        *,
        tier: str = CARTOGRAPHER_TIER,
        models: ModelsConfig | None = None,
        toolkit: ResearchToolkit | None = None,
    ):
        self._store = store
        self._llm = llm
        self._tier = tier
        self._models = models or load_models_config()
        self._toolkit = toolkit

    def build_map(self, group_ref: str, jurisdiction: str) -> CartographerReport:
        model = self._models.tiers[self._tier]
        valid_slugs = set(self._store.list_category_slugs())

        sources: list[ResearchSource] = []
        if self._toolkit is not None:
            queries = self._plan_queries(group_ref, jurisdiction, model)
            sources = self._toolkit.gather(queries)

        prompt = self._build_prompt(group_ref, jurisdiction, valid_slugs, sources)
        answer = self._llm.complete(prompt, model)
        raw_items = self._parse_answer(answer)

        if self._toolkit is not None:
            known_urls = {s.url for s in sources}
            raw_items = [self._apply_sources(entry, known_urls) for entry in raw_items]

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
            sources_used=len(sources),
        )

    # ── внутреннее ───────────────────────────────────────────────────────

    def _plan_queries(self, group_ref: str, jurisdiction: str, model: str) -> list[str]:
        """Отдельный (дешёвый по объёму ответа) LLM-вызов за планом поисковых
        запросов. Ответ должен быть СТРОГО JSON-массивом строк; любое
        отклонение (не-JSON, не-массив, нестроковые/пустые элементы) —
        откат на единственный запрос по названию группы и юрисдикции, а не
        падение всего `build_map` (план запросов — вспомогательный шаг,
        не основной ответ Cartographer'а)."""
        prompt = (
            f"{_SYSTEM_PROMPT}\n\nГруппа: {group_ref}\nЮрисдикция: {jurisdiction}\n\n"
            "Составь до 6 поисковых запросов к официальным источникам (нормативные акты, "
            "регуляторы, техрегламенты) для разведки требований к этой группе: половина на "
            "русском, половина на узбекском (латиница). Ответь СТРОГО JSON-массивом строк."
        )
        answer = self._llm.complete(prompt, model)
        try:
            data = json.loads(answer)
        except json.JSONDecodeError:
            data = None
        if not isinstance(data, list) or not all(isinstance(q, str) and q.strip() for q in data):
            return [f"{group_ref} требования {jurisdiction}"]
        return [q.strip() for q in data][: self._toolkit.max_queries]

    @staticmethod
    def _apply_sources(entry: dict, known_urls: set[str]) -> dict:
        """`sources` айтема — только URL, реально собранные `toolkit.gather`;
        всё остальное (выдумки LLM, опечатки) отбрасывается молча — это
        защита от фиктивных ссылок в карте, которая идёт владельцу на
        апрув."""
        raw_sources = entry.get("sources", [])
        filtered = [u for u in raw_sources if isinstance(u, str) and u in known_urls]
        return {**entry, "sources": filtered}

    @staticmethod
    def _build_prompt(
        group_ref: str,
        jurisdiction: str,
        valid_slugs: set[str],
        sources: list[ResearchSource] = (),
    ) -> str:
        slugs_line = ", ".join(sorted(valid_slugs)) or "(список пуст)"
        schema = (
            '{"expected_item": "...", "category_slug": "...", "rationale": "...", '
            '"benchmark_countries": ["..."]'
        )
        sources_block = ""
        if sources:
            schema += ', "sources": ["url", ...]'
            numbered = "\n".join(
                f"[{i}] {s.title} — {s.url}\n{s.excerpt}\n---"
                for i, s in enumerate(sources, start=1)
            )
            sources_block = (
                "\n\nИсточники (пронумерованы; опирайся на них, для каждого айтема "
                f'укажи url источников в поле "sources"):\n{numbered}'
            )
        schema += "}"
        return (
            f"{_SYSTEM_PROMPT}\n\n"
            f"Группа: {group_ref}\n"
            f"Юрисдикция: {jurisdiction}\n"
            f"Известные category_slug (используй ТОЛЬКО их, не выдумывай новые): {slugs_line}"
            f"{sources_block}\n\n"
            "Построй карту требований в две стадии:\n"
            "1) мировая практика — исследуй ~50 стран-бенчмарков по этой "
            "товарной/сервисной группе (крупнейшие торговые юрисдикции и "
            "профильные регуляторы для этой группы);\n"
            "2) для каждой найденной практики сформулируй expected_item — "
            f"конкретное требование, ожидаемое именно в юрисдикции {jurisdiction}.\n\n"
            f"Ответь СТРОГО JSON-массивом объектов вида {schema}. Ничего, кроме "
            "JSON-массива, в ответе быть не должно."
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
