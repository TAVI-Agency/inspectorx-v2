"""Единый фейковый `BuildStore` для тестов Build-конвейера — без сети и без
БД, только словари в памяти.

Переиспользуется `test_orchestrator.py` (Задача 14) и `test_cartographer.py`
(Задача 15): до фикс-раунда ревью Задачи 15 у каждого файла был свой
дублёр, и они разошлись — `InMemoryStore` из `test_orchestrator.py` не умел
map-методы Cartographer'а (`save_map`/`set_map_status`/
`list_category_slugs`), а `FakeStore` из `test_cartographer.py` не был
полной реализацией `BuildStore` Protocol. Единый дублёр нужен, чтобы
связку "Cartographer строит карту → владелец её апрувит → Orchestrator по
ней реально прогоняет" можно было проверить одним тестом на одном сторе
(см. `test_cartographer.py:
test_cartographer_map_can_be_approved_and_run_by_orchestrator`), а не
верить каждому дублёру по отдельности.

Семантика map-методов повторяет `SupabaseBuildStore`
(`importer/build/orchestrator.py`): `save_map` — upsert по уникальному
`(group_ref, jurisdiction)` (существующий `draft` перезаписывается тем же
`id`, существующий `approved` → `MapAlreadyApprovedError`); `set_map_status`
заполняет `approved_at`/`approved_by` только при переходе в `'approved'`.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime, timezone

from importer.build.agents import Verdict
from importer.build.orchestrator import MapAlreadyApprovedError, MapRecord
from importer.build.steps import ItemRecord

# Как в public.requirement_categories (миграция
# 20260803140000_requirement_categories.sql) — дефолт для тестов, которым
# не важен конкретный набор слагов; переопределяется через конструктор
# (`InMemoryStore(category_slugs=[...])`) там, где важен.
DEFAULT_CATEGORY_SLUGS = [
    "sps", "tbt", "marking", "licensing", "fiscal", "currency", "customs", "origin",
]


@dataclass
class InMemoryStore:
    """Фейковый `BuildStore`: полная реализация Protocol (Задачи 14 + 15)."""

    category_slugs: list[str] = field(default_factory=lambda: list(DEFAULT_CATEGORY_SLUGS))
    # group_ref -> кандидаты catalog.product_types (Задача 20, шаг 'scope') —
    # инжектируется явно в конструктор теста, дефолт пуст (без группы —
    # пустой список кандидатов, а не KeyError).
    product_types_by_group: dict[str, list[dict]] = field(default_factory=dict)
    maps: dict[str, MapRecord] = field(default_factory=dict)
    items: dict[str, ItemRecord] = field(default_factory=dict)
    runs: dict[str, dict] = field(default_factory=dict)
    verdicts: list[tuple[str, str, list[Verdict]]] = field(default_factory=list)
    # (item_id, status) в порядке вызовов — чтобы проверять переходы, не только итог
    status_history: list[tuple[str, str]] = field(default_factory=list)
    _by_map_key: dict[tuple[str, str], str] = field(default_factory=dict)
    _next_id: int = 0

    def _gen_id(self, prefix: str) -> str:
        self._next_id += 1
        return f"{prefix}-{self._next_id}"

    # ── карты (Задача 15: Cartographer) ──────────────────────────────────

    def list_category_slugs(self) -> list[str]:
        return list(self.category_slugs)

    def list_group_product_types(self, group_ref: str) -> list[dict]:
        return list(self.product_types_by_group.get(group_ref, []))

    def load_map(self, map_id: str) -> MapRecord:
        return self.maps[map_id]

    def save_map(self, group_ref: str, jurisdiction: str, payload: list[dict]) -> str:
        key = (group_ref, jurisdiction)
        existing_id = self._by_map_key.get(key)
        if existing_id is not None:
            existing = self.maps[existing_id]
            if existing.status == "approved":
                raise MapAlreadyApprovedError(
                    f"карта {group_ref}/{jurisdiction} (id={existing_id}) уже approved — "
                    "повторный build_map запрещён"
                )
            self.maps[existing_id] = replace(existing, payload=payload, status="draft")
            return existing_id
        map_id = self._gen_id("map")
        self._by_map_key[key] = map_id
        self.maps[map_id] = MapRecord(
            id=map_id, group_ref=group_ref, jurisdiction=jurisdiction,
            status="draft", payload=payload,
        )
        return map_id

    def set_map_status(
        self, map_id: str, status: str, *, approved_by: str | None = None
    ) -> MapRecord:
        record = self.maps[map_id]
        updated = replace(
            record,
            status=status,
            approved_by=approved_by if status == "approved" else record.approved_by,
            approved_at=(
                datetime.now(timezone.utc).isoformat()
                if status == "approved" else record.approved_at
            ),
        )
        self.maps[map_id] = updated
        return updated

    # ── прогон (Задача 14: Orchestrator) ─────────────────────────────────

    def create_run(self, map_id: str) -> str:
        run_id = self._gen_id("run")
        self.runs[run_id] = {"map_id": map_id, "status": "running"}
        return run_id

    def create_items(self, run_id: str, payload: list[dict]) -> list[ItemRecord]:
        created = []
        for entry in payload:
            item_id = self._gen_id("item")
            item = ItemRecord(
                id=item_id,
                run_id=run_id,
                expected_item=entry["expected_item"],
                category_slug=entry.get("category_slug"),
            )
            self.items[item_id] = item
            created.append(item)
        return created

    def update_item_status(self, item_id, status, *, last_error=None) -> ItemRecord:
        item = self.items[item_id]
        item.status = status
        if last_error is not None:
            item.last_error = last_error
        self.status_history.append((item_id, status))
        return item

    def bump_retry(self, item_id: str) -> int:
        item = self.items[item_id]
        item.retry_count += 1
        return item.retry_count

    def save_verdicts(self, item_id, step, verdicts) -> None:
        self.verdicts.append((item_id, step, verdicts))

    def finish_run(self, run_id: str, status: str) -> None:
        self.runs[run_id]["status"] = status
