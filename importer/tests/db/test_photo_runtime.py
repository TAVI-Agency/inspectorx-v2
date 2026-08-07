"""Рантайм фотоконтроля (Задача 8 Волны 1): квота, идемпотентность, возврат,
репер и RLS — на живой локальной Supabase."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

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


def _request_photo(client, uid, product_id, key):
    """Фотопуть: досъёмка возможна только у source_kind='photo' (минимум 4 кадра)."""
    return client.rpc("request_photo_inspection", {
        "p_product_id": product_id, "p_level": "consumer", "p_markets": ["UZ"],
        "p_source_kind": "photo",
        "p_asset_paths": [f"{uid}/shoot/{i}.jpg" for i in range(4)],
        "p_idempotency_key": key,
    }).execute().data


def _retake(client, uid, inspection_id, key):
    return client.rpc("request_photo_retake", {
        "p_inspection_id": inspection_id,
        "p_new_asset_paths": [f"{uid}/shoot/{key}.jpg"],
        "p_idempotency_key": key,
    }).execute().data


def _finalize_done(service, inspection_id):
    service.rpc("finalize_photo_inspection", {
        "p_inspection_id": inspection_id, "p_outcome": "done",
        "p_payload": {"overall": "ok", "decided": 1, "checked": 1,
                      "findings": [], "not_checkable": [], "facts": [],
                      "model_calls": [], "assets": []}}).execute()


def _quota(service, uid):
    row = service.table("photo_quota").select("*").eq("user_id", uid).execute().data[0]
    return row["reserved"], row["used"], row["refunds_used"]


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


def test_retake_and_rejudge_do_not_touch_quota(subscriber, service,
                                               current_ruleset, tobacco_product_id):
    """Досъёмка резерва не делает — значит и списывать с неё нечего.
    До фикса finalize бил её `used + 1` (done) и жёг слот возврата (failed)."""
    client, uid = subscriber
    parent = _request_photo(client, uid, tobacco_product_id, key="free-1")
    _finalize_done(service, parent)
    assert _quota(service, uid) == (0, 1, 0)

    # ревизия 2: успешный прогон досъёмки квоту не двигает
    r2 = _retake(client, uid, parent, key="free-1-r2")
    assert _quota(service, uid) == (0, 1, 0)
    _finalize_done(service, r2)
    assert _quota(service, uid) == (0, 1, 0)

    # ревизия 3: падение по возвратной причине не съедает слот возврата
    r3 = _retake(client, uid, r2, key="free-1-r3")
    service.rpc("finalize_photo_inspection",
                {"p_inspection_id": r3, "p_outcome": "failed",
                 "p_reason": "worker_timeout"}).execute()
    assert _quota(service, uid) == (0, 1, 0)


def test_ruleset_change_makes_the_same_files_a_new_run(subscriber, service,
                                                       current_ruleset, tobacco_product_id):
    """Соль набора правил в ключе (её добавляет сервер, клиент отпечатка не
    знает): после передеплоя правил тот же комплект файлов проверяется заново,
    а не отдаёт вердикт по отменённому набору."""
    client, uid = subscriber
    first = _request(client, uid, tobacco_product_id, key="ruleset-salt")
    assert _request(client, uid, tobacco_product_id, key="ruleset-salt") == first

    other = "b" * 64
    try:
        service.table("ruleset_versions").update({"is_current": False}).eq(
            "sha256", current_ruleset).execute()
        service.table("ruleset_versions").upsert(
            {"sha256": other, "version": "test-b", "packs": {}, "checks_count": 1,
             "is_current": True}).execute()
        second = _request(client, uid, tobacco_product_id, key="ruleset-salt")
        assert second != first          # тот же клиентский ключ — но новый прогон
        row = service.table("photo_inspections").select("ruleset_sha256").eq(
            "id", second).execute().data[0]
        assert row["ruleset_sha256"] == other
    finally:
        # current_ruleset — session-скоуп: возвращаем текущей прежнюю версию
        service.table("ruleset_versions").update({"is_current": False}).eq(
            "sha256", other).execute()
        service.table("ruleset_versions").update({"is_current": True}).eq(
            "sha256", current_ruleset).execute()


def test_retake_is_idempotent_and_scoped_to_its_inspection(subscriber, service,
                                                           current_ruleset, tobacco_product_id):
    """Повтор сабмита досъёмки возвращает ту же ревизию (до фикса — голый 23505
    по unique (user_id, idempotency_key)); тот же кадр в ДРУГОЙ проверке —
    самостоятельная ревизия, а не чужая."""
    client, uid = subscriber
    a = _request_photo(client, uid, tobacco_product_id, key="scope-a")
    _finalize_done(service, a)
    r1 = _retake(client, uid, a, key="shot-1")
    assert _retake(client, uid, a, key="shot-1") == r1

    b = _request_photo(client, uid, tobacco_product_id, key="scope-b")
    _finalize_done(service, b)
    r2 = _retake(client, uid, b, key="shot-1")      # тот же ключ, другая проверка
    assert r2 and r2 != r1


def test_second_retake_from_the_same_parent_is_rejected(subscriber, service,
                                                        current_ruleset, tobacco_product_id):
    """Цепочка ревизий — линия, не дерево: вторая досъёмка от того же родителя
    перезаписала бы superseded_by и потеряла первую ревизию для витрины."""
    client, uid = subscriber
    parent = _request_photo(client, uid, tobacco_product_id, key="fork-1")
    _finalize_done(service, parent)
    assert _retake(client, uid, parent, key="fork-r1")
    with pytest.raises(Exception, match="already_superseded"):
        _retake(client, uid, parent, key="fork-r2")


def test_rejudge_of_superseded_parent_is_rejected(subscriber, service,
                                                  current_ruleset, tobacco_product_id):
    """Тот же гвард в create_photo_revision (пересуд правленого факта)."""
    client, uid = subscriber
    parent = _request_photo(client, uid, tobacco_product_id, key="fork-rev")
    _finalize_done(service, parent)
    payload = {"overall": "ok", "decided": 1, "checked": 1,
               "findings": [], "not_checkable": [], "facts": []}
    first = service.rpc("create_photo_revision", {
        "p_parent_id": parent, "p_payload": payload}).execute().data
    assert first
    with pytest.raises(Exception, match="already_superseded"):
        service.rpc("create_photo_revision", {
            "p_parent_id": parent, "p_payload": payload}).execute()


def test_reaper_kills_stale_running_with_refund(subscriber, service,
                                                current_ruleset, tobacco_product_id):
    client, uid = subscriber
    ins_id = _request(client, uid, tobacco_product_id, key="stale-1")
    assert _quota(service, uid) == (1, 0, 0)
    service.table("photo_inspections").update(
        {"status": "running",
         "heartbeat_at": "2020-01-01T00:00:00Z"}).eq("id", ins_id).execute()
    service.rpc("reap_stale_inspections", {}).execute()
    row = service.table("photo_inspections").select("status,last_error").eq(
        "id", ins_id).execute().data[0]
    assert row == {"status": "failed", "last_error": "worker_timeout"}
    # имя теста обещает возврат — проверяем его: резерв снят, used не вырос
    assert _quota(service, uid) == (0, 0, 1)


def test_reaper_kills_running_without_heartbeat(subscriber, service,
                                                current_ruleset, tobacco_product_id):
    """`heartbeat_at is null` (воркер умер до первого пульса): без coalesce
    условие давало null и строка висела в running вечно с живым резервом."""
    client, uid = subscriber
    ins_id = _request(client, uid, tobacco_product_id, key="stale-nohb")
    # created_at старим на 10 минут (порог running — 3), НЕ выходя за границу
    # календарного месяца: период квоты считается от created_at
    aged = (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat()
    service.table("photo_inspections").update(
        {"status": "running", "heartbeat_at": None, "created_at": aged}
    ).eq("id", ins_id).execute()

    assert service.rpc("reap_stale_inspections", {}).execute().data >= 1
    row = service.table("photo_inspections").select("status,last_error").eq(
        "id", ins_id).execute().data[0]
    assert row == {"status": "failed", "last_error": "worker_timeout"}
    assert _quota(service, uid) == (0, 0, 1)


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
