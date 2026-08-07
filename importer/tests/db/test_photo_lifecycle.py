"""Устаревание вердиктов фотоконтроля (Задача 16, Волна 1, этап 7): изменение
нормы метит РОВНО затронутые проверки stale_since + заводит уведомление
checklist_version — идемпотентно, ни один вердикт не меняется."""
from __future__ import annotations

import pytest

from .conftest import _finished_inspection_with_finding, requires_db

pytestmark = [pytest.mark.integration, requires_db]


def test_change_event_marks_exactly_affected_verdicts(subscriber, service,
                                                      current_ruleset, tobacco_product_id):
    client, uid = subscriber
    req_id = service.table("requirements").select("id").eq(
        "status", "published").limit(1).execute().data[0]["id"]
    ins_id, fid = _finished_inspection_with_finding(
        client, uid, service, tobacco_product_id, requirement_id=req_id)
    other_id, _ = _finished_inspection_with_finding(
        client, uid, service, tobacco_product_id, requirement_id=None, key="other")

    ev = service.table("change_events").insert({
        "event_type": "amended", "title": "тестовое изменение",
        "effective_date": "2026-08-01"}).execute().data[0]
    service.table("requirement_change_impacts").insert({
        "change_event_id": ev["id"], "requirement_id": req_id,
        "status": "confirmed"}).execute()

    service.rpc("flag_stale_photo_inspections", {}).execute()

    row = service.table("photo_inspections").select("stale_since").eq(
        "id", ins_id).execute().data[0]
    assert row["stale_since"] == "2026-08-01"
    other = service.table("photo_inspections").select("stale_since").eq(
        "id", other_id).execute().data[0]
    assert other["stale_since"] is None        # не затронутые не тронуты

    notes = service.table("user_notifications").select("*").eq(
        "user_id", uid).eq("kind", "checklist_version").execute().data
    assert len(notes) == 1
    # повторный прогон идемпотентен
    service.rpc("flag_stale_photo_inspections", {}).execute()
    notes = service.table("user_notifications").select("*").eq(
        "user_id", uid).eq("kind", "checklist_version").execute().data
    assert len(notes) == 1
    # вердикт не изменён: findings нетронуты
    f = service.table("photo_findings").select("status").eq("id", fid).execute().data[0]
    assert f["status"] == "fail"
