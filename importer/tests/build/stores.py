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

    # ── Задача 26: Assembler/Load — таблицы public.* поверх словарей ──────
    authorities: dict[str, dict] = field(default_factory=dict)
    requirements: dict[str, dict] = field(default_factory=dict)
    # ключ — (requirement_id, lang), тот же составной PK, что и в БД
    requirement_contents: dict[tuple[str, str], dict] = field(default_factory=dict)
    requirement_details: dict[tuple[str, str], dict] = field(default_factory=dict)
    requirement_applicability: dict[str, list[dict]] = field(default_factory=dict)
    requirement_rules: dict[str, list[dict]] = field(default_factory=dict)
    _by_external_key: dict[str, str] = field(default_factory=dict)

    # ── Задача 29: трейсинг LLM-вызовов и стоимость по ролям ───────────────
    llm_calls: list[dict] = field(default_factory=list)

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

    def list_run_item_texts(self, run_id: str) -> list[dict]:
        """Тот же контракт, что `SupabaseBuildStore.list_run_item_texts`
        (Задача 25, фикс-раунд ревью Задачи 27) — `text =
        coalesce(item.summary_text, item.expected_item)` (см. докстринг
        `BuildStore.list_run_item_texts` в `orchestrator.py`): симметричное
        сравнение summary-vs-summary для dedup, `expected_item` — только
        фолбэк, если 'summary' ещё не отработал.

        Фильтр `status in ('draft_loaded', 'published')` (Critical
        фикс-раунда ревью Задачи 25) — та же семантика, что и у
        `SupabaseBuildStore`: `pending`/`in_progress`/`needs_attention`/
        `no_norm` не кандидаты. Порядок — порядок вставки в `self.items`
        (обычный `dict` в Python 3.7+ его сохраняет), что уже эквивалентно
        `order("updated_at")` у `SupabaseBuildStore` для целей теста
        «первый найденный дубль побеждает»."""
        return [
            {"item_id": item.id, "text": item.summary_text or item.expected_item}
            for item in self.items.values()
            if item.run_id == run_id and item.status in ("draft_loaded", "published")
        ]

    def set_item_summary(self, item_id: str, summary: str) -> None:
        self.items[item_id].summary_text = summary

    def update_item_status(
        self, item_id, status, *, last_error=None, requirement_id=None
    ) -> ItemRecord:
        item = self.items[item_id]
        item.status = status
        if last_error is not None:
            item.last_error = last_error
        if requirement_id is not None:
            item.requirement_id = requirement_id
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

    # ── Задача 27: coverage/публикация/менеджер исключений ────────────────

    def get_run(self, run_id: str) -> dict:
        return dict(self.runs[run_id])

    def list_run_items(self, run_id: str) -> list[ItemRecord]:
        return [item for item in self.items.values() if item.run_id == run_id]

    def save_coverage_report(self, run_id: str, markdown: str) -> None:
        self.runs[run_id]["coverage_report"] = markdown

    def list_item_verdicts(self, item_id: str) -> list[tuple[str, Verdict]]:
        """`[(step, Verdict), ...]` в порядке вставки в `self.verdicts`
        (обычный список — append-only, тот же хронологический порядок, что
        и `order("created_at")` у `SupabaseBuildStore`)."""
        result: list[tuple[str, Verdict]] = []
        for stored_item_id, step, verdicts in self.verdicts:
            if stored_item_id == item_id:
                result.extend((step, v) for v in verdicts)
        return result

    def publish_requirement(self, requirement_id: str) -> None:
        self.requirements[requirement_id]["status"] = "published"
        self.requirements[requirement_id]["published_at"] = datetime.now(timezone.utc).isoformat()

    # ── Задача 26: Assembler/Load ─────────────────────────────────────────

    def find_or_create_authority(self, name: str) -> str:
        for authority_id, row in self.authorities.items():
            if row.get("name_ru") == name:
                return authority_id
        authority_id = self._gen_id("authority")
        self.authorities[authority_id] = {"id": authority_id, "name_ru": name}
        return authority_id

    def set_item_note(self, item_id: str, note: str) -> None:
        self.items[item_id].last_error = note

    def save_requirement_draft(self, card: dict, *, item_id: str) -> str:
        requirement = dict(card["requirement"])
        external_key = requirement.get("external_key")

        existing_id = self._by_external_key.get(external_key) if external_key else None
        if existing_id is not None:
            requirement_id = existing_id
            existing_row = self.requirements[requirement_id]
            if existing_row.get("status") == "published":
                # published сохраняется — контент обновляем, статус не
                # трогаем (докстринг BuildStore.save_requirement_draft).
                requirement = {**requirement, "status": "published"}
                self.set_item_note(item_id, "existing published, status preserved")
            self.requirements[requirement_id] = {
                **existing_row, **requirement, "id": requirement_id,
            }
        else:
            requirement_id = self._gen_id("requirement")
            self.requirements[requirement_id] = {**requirement, "id": requirement_id}
            if external_key:
                self._by_external_key[external_key] = requirement_id

        # replace-семантика (докстринг steps_load.py) — полностью пересобираем
        # per-lang строки этого требования на каждый вызов, не merge построчно.
        self._replace_lang_rows(
            self.requirement_contents, requirement_id, card.get("contents") or {}
        )
        self._replace_lang_rows(
            self.requirement_details, requirement_id, card.get("details") or {}
        )

        applicability = card.get("applicability")
        self.requirement_applicability[requirement_id] = (
            [dict(applicability)] if applicability else []
        )

        self.requirement_rules[requirement_id] = list(card.get("rules") or [])

        return requirement_id

    # ── Задача 29: трейсинг LLM-вызовов и стоимость по ролям ───────────────

    def save_llm_call(
        self,
        run_id: str,
        role: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        cost_usd: float,
        *,
        item_id: str | None = None,
    ) -> None:
        self.llm_calls.append({
            "run_id": run_id,
            "item_id": item_id,
            "role": role,
            "model": model,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cost_usd": cost_usd,
        })

    def list_llm_calls(self, run_id: str) -> list[dict]:
        return [dict(call) for call in self.llm_calls if call["run_id"] == run_id]

    @staticmethod
    def _replace_lang_rows(
        table: dict[tuple[str, str], dict], requirement_id: str, new_rows: dict[str, dict]
    ) -> None:
        for key in [k for k in table if k[0] == requirement_id]:
            table.pop(key)
        for lang, row in new_rows.items():
            table[(requirement_id, lang)] = {**row, "requirement_id": requirement_id, "lang": lang}
