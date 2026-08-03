"""Фейковый `MonitoringStore` для тестов Impact-маппера (Задача 40), истории
изменений и discovery (Задача 41) — без сети и без БД, только словари в
памяти. Тот же паттерн, что и `importer/tests/build/stores.py`:
`InMemoryMonitoringStore` — полная реализация `MonitoringStore` Protocol
(`importer/monitoring/impact_mapper.py`), плюс несколько вспомогательных
методов-фикстур (`add_event`/`add_citation`/`add_published_requirement`/
`add_applicable_user`/`add_pipeline_item`/`add_approved_map`), которых у
Protocol нет — только для удобства сборки сценариев теста.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from importer.monitoring.impact_mapper import (
    ApprovedMapRecord,
    ChangeEventRecord,
    HistorySourceEvent,
    ImpactRecord,
)


@dataclass
class InMemoryMonitoringStore:
    # id -> сырая строка change_events (мутируется: processed_at)
    events: dict[str, dict] = field(default_factory=dict)
    # legalx_act_id -> [requirement_id, ...] — путь (а) точного маппинга
    # (эмулирует join acts.jurisbase_act_id -> act_paragraphs ->
    # requirement_citations, см. докстринг impact_mapper.py)
    citations: dict[str, list[str]] = field(default_factory=dict)
    # jurisdiction -> [{"id", "title"}, ...] — вход Classifier-кандидатов и
    # контекста In-house lawyer
    published_requirements: dict[str, list[dict]] = field(default_factory=dict)
    # requirement_id -> {"review_flag", "flagged_at", "flagged_by_event_id"}
    requirements: dict[str, dict] = field(default_factory=dict)
    # append-only список строк requirement_change_impacts
    impacts: list[dict] = field(default_factory=list)
    # requirement_id -> [{"user_id", "product_id", "service_id"}, ...] — кто
    # подписан на этот requirement через chosen_products (эмуляция join)
    applicable_users: dict[str, list[dict]] = field(default_factory=dict)
    # append-only список созданных user_notifications
    notifications: list[dict] = field(default_factory=list)
    # requirement_id -> pipeline item id (эмуляция pipeline.items.requirement_id)
    pipeline_items_by_requirement: dict[str, str] = field(default_factory=dict)
    # append-only список строк requirement_revisions (Задача 41)
    revisions: list[dict] = field(default_factory=list)
    # jurisdiction -> [{"id", "group_ref", "jurisdiction", "payload"}, ...] —
    # approved-карты pipeline.maps (Задача 41, вход discovery)
    approved_maps: dict[str, list[dict]] = field(default_factory=dict)
    # append-only список discovery-прогонов: {"id", "map_id"} (эмуляция pipeline.runs)
    discovery_runs: list[dict] = field(default_factory=list)
    # append-only список discovery-кандидатов: {"id", "run_id", "map_id",
    # "expected_item", "category_slug", "status"} (эмуляция pipeline.items)
    discovery_items: list[dict] = field(default_factory=list)
    _next_id: int = 0

    def _gen_id(self, prefix: str) -> str:
        self._next_id += 1
        return f"{prefix}-{self._next_id}"

    # ── фикстуры теста (НЕ часть MonitoringStore Protocol) ────────────────

    def add_event(
        self,
        *,
        event_type: str,
        jurisdiction: str = "UZ",
        effective_date: str | None = None,
        summary: str | None = None,
        payload: dict | None = None,
        event_id: str | None = None,
        processed: bool = False,
        title: str | None = None,
        was_text: str | None = None,
        now_text: str | None = None,
        created_at: str | None = None,
    ) -> str:
        eid = event_id or self._gen_id("event")
        self.events[eid] = {
            "id": eid,
            "event_type": event_type,
            "jurisdiction": jurisdiction,
            "effective_date": effective_date,
            "summary": summary,
            "payload": payload or {},
            "processed_at": (
                datetime.now(timezone.utc).isoformat() if processed else None
            ),
            # Задача 41 (change_history/discovery): в реальной схеме
            # `title` — NOT NULL (`20260711120000_initial_schema.sql`) —
            # фолбэк ниже держит тот же инвариант для фикстуры, тестам,
            # которым конкретный текст безразличен, не нужно его передавать.
            "title": title if title is not None else f"событие {event_type}",
            "was_text": was_text,
            "now_text": now_text,
            "created_at": created_at or datetime.now(timezone.utc).isoformat(),
        }
        return eid

    def add_citation(self, legalx_act_id: str, requirement_id: str) -> None:
        self.citations.setdefault(legalx_act_id, []).append(requirement_id)

    def add_published_requirement(
        self, jurisdiction: str, requirement_id: str, title: str
    ) -> None:
        self.published_requirements.setdefault(jurisdiction, []).append(
            {"id": requirement_id, "title": title}
        )

    def add_applicable_user(
        self,
        requirement_id: str,
        user_id: str,
        *,
        product_id: str | None = None,
        service_id: str | None = None,
    ) -> None:
        self.applicable_users.setdefault(requirement_id, []).append(
            {"user_id": user_id, "product_id": product_id, "service_id": service_id}
        )

    def add_pipeline_item(self, requirement_id: str, item_id: str) -> None:
        self.pipeline_items_by_requirement[requirement_id] = item_id

    def add_approved_map(
        self,
        *,
        jurisdiction: str,
        payload: list[dict],
        group_ref: str = "group",
        map_id: str | None = None,
    ) -> str:
        mid = map_id or self._gen_id("map")
        self.approved_maps.setdefault(jurisdiction, []).append(
            {"id": mid, "group_ref": group_ref, "jurisdiction": jurisdiction, "payload": payload}
        )
        return mid

    # ── MonitoringStore Protocol ───────────────────────────────────────────

    def list_unprocessed_events(self) -> list[ChangeEventRecord]:
        return [
            ChangeEventRecord(
                id=row["id"],
                event_type=row["event_type"],
                jurisdiction=row["jurisdiction"],
                effective_date=row["effective_date"],
                summary=row["summary"],
                payload=row["payload"],
            )
            for row in self.events.values()
            if row["processed_at"] is None
        ]

    def find_duplicate_processed_event(
        self,
        legalx_act_id: str | None,
        event_type: str,
        effective_date: str | None,
        jurisdiction: str,
    ) -> bool:
        if not legalx_act_id:
            return False
        for row in self.events.values():
            if row["processed_at"] is None:
                continue
            if (
                row["payload"].get("act_id") == legalx_act_id
                and row["event_type"] == event_type
                and row["effective_date"] == effective_date
                and row["jurisdiction"] == jurisdiction
            ):
                return True
        return False

    def mark_processed(self, event_id: str) -> None:
        self.events[event_id]["processed_at"] = datetime.now(timezone.utc).isoformat()

    def find_requirements_by_citation(self, legalx_act_id: str) -> list[str]:
        return list(self.citations.get(legalx_act_id, []))

    def list_published_requirements(self, jurisdiction: str) -> list[dict]:
        return [dict(row) for row in self.published_requirements.get(jurisdiction, [])]

    def save_impacts(
        self, change_event_id: str, requirement_ids: list[str]
    ) -> list[ImpactRecord]:
        result = []
        for rid in requirement_ids:
            existing = next(
                (
                    imp
                    for imp in self.impacts
                    if imp["change_event_id"] == change_event_id
                    and imp["requirement_id"] == rid
                ),
                None,
            )
            if existing is None:
                existing = {
                    "id": self._gen_id("impact"),
                    "change_event_id": change_event_id,
                    "requirement_id": rid,
                    "status": "pending_review",
                }
                self.impacts.append(existing)
            result.append(ImpactRecord(**existing))
        return result

    def flag_requirement(self, requirement_id: str, change_event_id: str) -> None:
        self.requirements.setdefault(requirement_id, {})
        self.requirements[requirement_id].update(
            {
                "review_flag": "flagged_by_change",
                "flagged_at": datetime.now(timezone.utc).isoformat(),
                "flagged_by_event_id": change_event_id,
            }
        )

    def fanout_notifications(self, impact_ids: list[str]) -> int:
        created = 0
        for impact in self.impacts:
            if impact["id"] not in impact_ids:
                continue
            for user in self.applicable_users.get(impact["requirement_id"], []):
                already = any(
                    n["user_id"] == user["user_id"] and n["impact_id"] == impact["id"]
                    for n in self.notifications
                )
                if already:
                    continue
                self.notifications.append(
                    {
                        "user_id": user["user_id"],
                        "impact_id": impact["id"],
                        "requirement_id": impact["requirement_id"],
                        "product_id": user.get("product_id"),
                        "service_id": user.get("service_id"),
                        "kind": "change",
                    }
                )
                created += 1
        return created

    def enqueue_rereview(self, requirement_id: str) -> str | None:
        return self.pipeline_items_by_requirement.get(requirement_id)

    # ── Задача 41: история изменений ────────────────────────────────────────

    def list_change_events_for_requirement(
        self, requirement_id: str
    ) -> list[HistorySourceEvent]:
        event_ids = list(
            dict.fromkeys(
                imp["change_event_id"]
                for imp in self.impacts
                if imp["requirement_id"] == requirement_id
            )
        )
        events = [
            HistorySourceEvent(
                change_event_id=eid,
                event_type=row["event_type"],
                effective_date=row["effective_date"],
                created_at=row["created_at"],
                summary=row["summary"],
                title=row["title"],
                was_text=row["was_text"],
                now_text=row["now_text"],
            )
            for eid in event_ids
            for row in [self.events[eid]]
        ]
        return sorted(events, key=lambda e: e.created_at)

    def list_existing_revision_event_ids(self, requirement_id: str) -> set[str]:
        return {
            rev["change_event_id"]
            for rev in self.revisions
            if rev["requirement_id"] == requirement_id
        }

    def save_revision(
        self,
        requirement_id: str,
        *,
        change_event_id: str,
        change_note: str | None,
        snapshot: dict,
        created_at: str,
    ) -> str:
        existing_nos = [
            rev["revision_no"] for rev in self.revisions if rev["requirement_id"] == requirement_id
        ]
        revision_no = max(existing_nos, default=0) + 1
        row = {
            "id": self._gen_id("revision"),
            "requirement_id": requirement_id,
            "revision_no": revision_no,
            "change_event_id": change_event_id,
            "change_note": change_note,
            "snapshot": snapshot,
            "created_at": created_at,
        }
        self.revisions.append(row)
        return row["id"]

    # ── Задача 41: discovery новых актов ────────────────────────────────────

    def list_new_events_without_impacts(self) -> list[ChangeEventRecord]:
        impacted_event_ids = {imp["change_event_id"] for imp in self.impacts}
        return [
            ChangeEventRecord(
                id=row["id"],
                event_type=row["event_type"],
                jurisdiction=row["jurisdiction"],
                effective_date=row["effective_date"],
                summary=row["summary"],
                payload=row["payload"],
            )
            for row in self.events.values()
            if row["event_type"] == "new"
            and row["processed_at"] is not None
            and row["id"] not in impacted_event_ids
        ]

    def list_approved_maps(self, jurisdiction: str) -> list[ApprovedMapRecord]:
        return [
            ApprovedMapRecord(
                id=row["id"],
                group_ref=row["group_ref"],
                jurisdiction=row["jurisdiction"],
                payload=row["payload"],
            )
            for row in self.approved_maps.get(jurisdiction, [])
        ]

    def find_existing_discovery_item(self, map_id: str, expected_item: str) -> str | None:
        for item in self.discovery_items:
            if item["map_id"] == map_id and item["expected_item"] == expected_item:
                return item["id"]
        return None

    def create_discovery_run(self, map_id: str) -> str:
        run_id = self._gen_id("discovery-run")
        self.discovery_runs.append({"id": run_id, "map_id": map_id})
        return run_id

    def create_discovery_item(self, run_id: str, expected_item: str, category_slug: str) -> str:
        run = next(run for run in self.discovery_runs if run["id"] == run_id)
        item_id = self._gen_id("discovery-item")
        self.discovery_items.append(
            {
                "id": item_id,
                "run_id": run_id,
                "map_id": run["map_id"],
                "expected_item": expected_item,
                "category_slug": category_slug,
                "status": "pending",
            }
        )
        return item_id
