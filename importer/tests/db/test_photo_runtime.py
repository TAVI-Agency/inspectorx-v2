"""Рантайм фотоконтроля (Задача 8 Волны 1): квота, идемпотентность, возврат,
репер и RLS — на живой локальной Supabase."""
from __future__ import annotations

import pytest

from .conftest import requires_db

pytestmark = [pytest.mark.integration, requires_db]

PATHS = ["{uid}/00000000-0000-0000-0000-000000000000/0.pdf"]


def _request(client, uid, product_id, key="k1"):
    return client.rpc("request_photo_inspection", {
        "p_product_id": product_id, "p_level": "consumer", "p_markets": ["UZ"],
        "p_source_kind": "master_pdf",
        "p_asset_paths": [p.format(uid=uid) for p in PATHS],
        "p_idempotency_key": key,
    }).execute().data


def test_request_reserves_quota_and_is_idempotent(subscriber, service,
                                                  current_ruleset, tobacco_product_id):
    client, uid = subscriber
    ins_id = _request(client, uid, tobacco_product_id, key="idem-1")
    assert ins_id
    quota = service.table("photo_quota").select("*").eq("user_id", uid).execute().data[0]
    assert (quota["reserved"], quota["used"]) == (1, 0)
    again = _request(client, uid, tobacco_product_id, key="idem-1")
    assert again == ins_id                      # тот же ключ → та же проверка
    quota = service.table("photo_quota").select("*").eq("user_id", uid).execute().data[0]
    assert quota["reserved"] == 1               # резерв не удвоился


def test_foreign_path_prefix_is_rejected(subscriber, current_ruleset, tobacco_product_id):
    client, uid = subscriber
    with pytest.raises(Exception, match="foreign_path"):
        client.rpc("request_photo_inspection", {
            "p_product_id": tobacco_product_id, "p_level": "consumer",
            "p_markets": ["UZ"], "p_source_kind": "master_pdf",
            "p_asset_paths": ["someone-else/x/0.pdf"],
            "p_idempotency_key": "k-foreign"}).execute()


def test_finalize_done_spends_reserve(subscriber, service, current_ruleset, tobacco_product_id):
    client, uid = subscriber
    ins_id = _request(client, uid, tobacco_product_id, key="idem-done")
    service.rpc("finalize_photo_inspection", {
        "p_inspection_id": ins_id, "p_outcome": "done",
        "p_payload": {"overall": "review", "decided": 3, "checked": 79,
                      "findings": [], "not_checkable": [], "facts": [],
                      "model_calls": [], "assets": []}}).execute()
    quota = service.table("photo_quota").select("*").eq("user_id", uid).execute().data[0]
    assert (quota["reserved"], quota["used"]) == (0, 1)


def test_refund_only_for_closed_reason_list_and_capped(subscriber, service,
                                                       current_ruleset, tobacco_product_id):
    client, uid = subscriber
    a = _request(client, uid, tobacco_product_id, key="r1")
    service.rpc("finalize_photo_inspection",
                {"p_inspection_id": a, "p_outcome": "failed",
                 "p_reason": "worker_timeout"}).execute()
    quota = service.table("photo_quota").select("*").eq("user_id", uid).execute().data[0]
    assert (quota["reserved"], quota["used"], quota["refunds_used"]) == (0, 0, 1)
    b = _request(client, uid, tobacco_product_id, key="r2")
    service.rpc("finalize_photo_inspection",
                {"p_inspection_id": b, "p_outcome": "failed",
                 "p_reason": "no_text_layer"}).execute()   # отказ по данным — НЕ возвращается
    quota = service.table("photo_quota").select("*").eq("user_id", uid).execute().data[0]
    assert (quota["reserved"], quota["used"], quota["refunds_used"]) == (0, 1, 1)


def test_reaper_kills_stale_running_with_refund(subscriber, service,
                                                current_ruleset, tobacco_product_id):
    client, uid = subscriber
    ins_id = _request(client, uid, tobacco_product_id, key="stale-1")
    service.table("photo_inspections").update(
        {"status": "running",
         "heartbeat_at": "2020-01-01T00:00:00Z"}).eq("id", ins_id).execute()
    service.rpc("reap_stale_inspections", {}).execute()
    row = service.table("photo_inspections").select("status,last_error").eq(
        "id", ins_id).execute().data[0]
    assert row == {"status": "failed", "last_error": "worker_timeout"}


def test_rls_hides_foreign_inspections_and_blocks_writes(subscriber, service,
                                                         current_ruleset, tobacco_product_id):
    client, uid = subscriber
    ins_id = _request(client, uid, tobacco_product_id, key="rls-1")
    from supabase import create_client
    from .conftest import STACK
    stranger = create_client(STACK["API_URL"], STACK["ANON_KEY"])
    assert stranger.table("photo_inspections").select("id").eq(
        "id", ins_id).execute().data == []
    with pytest.raises(Exception):
        client.table("photo_inspections").insert(
            {"user_id": uid, "product_key": "tobacco", "packaging_level": "consumer",
             "source_kind": "photo", "idempotency_key": "hack",
             "ruleset_sha256": current_ruleset}).execute()
