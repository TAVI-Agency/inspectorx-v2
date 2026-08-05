"""`SupabaseMonitoringStore.resolve_item_map_ref` (гейт живого прогона,
`docs/LAUNCH_CHECKLIST.md`, пункт 2) — реальный (не `InMemoryMonitoringStore`)
3-хоповый резолв `pipeline.items.id -> run_id -> pipeline.runs.map_id ->
pipeline.maps(group_ref, jurisdiction)`, тот же `FakeClient`/`.schema()`/
`.rpc()`, что и `test_supabase_store.py` (без сети и без БД)."""
from __future__ import annotations

from importer.monitoring.impact_mapper import SupabaseMonitoringStore
from importer.tests.fakes import FakeClient

PIPELINE_TABLES = ("items", "runs", "maps")


def make_store(**seed) -> tuple[SupabaseMonitoringStore, FakeClient]:
    store_dict = {t: [] for t in PIPELINE_TABLES}
    store_dict.update(seed)
    ix = FakeClient(store_dict)
    return SupabaseMonitoringStore(ix), ix


def test_resolve_item_map_ref_happy_path_returns_map_id_group_ref_jurisdiction():
    store, _ = make_store(
        items=[{"id": "item-1", "run_id": "run-1"}],
        runs=[{"id": "run-1", "map_id": "map-1"}],
        maps=[{"id": "map-1", "group_ref": "2204", "jurisdiction": "UZ"}],
    )

    result = store.resolve_item_map_ref("item-1")

    assert result == ("map-1", "2204", "UZ")


def test_resolve_item_map_ref_returns_none_when_item_missing():
    store, _ = make_store()
    assert store.resolve_item_map_ref("no-such-item") is None


def test_resolve_item_map_ref_returns_none_when_run_missing():
    store, _ = make_store(items=[{"id": "item-1", "run_id": "run-missing"}])
    assert store.resolve_item_map_ref("item-1") is None


def test_resolve_item_map_ref_returns_none_when_map_missing():
    store, _ = make_store(
        items=[{"id": "item-1", "run_id": "run-1"}],
        runs=[{"id": "run-1", "map_id": "map-missing"}],
    )
    assert store.resolve_item_map_ref("item-1") is None
