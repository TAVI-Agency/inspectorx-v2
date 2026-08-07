"""Задача 14: очередь юриста по находкам фотоконтроля, заключения, подпись.
Тот же паттерн скипа/фикстур, что у test_photo_runtime.py / test_photo_lifecycle.py
(маркер integration, живой ЛОКАЛЬНЫЙ Supabase). Хелпер _finished_inspection_with_finding
живёт в conftest.py — переиспользован Задачей 16."""
from __future__ import annotations

import pytest

from .conftest import _finished_inspection_with_finding, requires_db

pytestmark = [pytest.mark.integration, requires_db]


def test_escalation_puts_finding_into_lawyer_queue(subscriber, service,
                                                    current_ruleset, tobacco_product_id):
    client, uid = subscriber
    ins_id, fid = _finished_inspection_with_finding(client, uid, service, tobacco_product_id)
    client.rpc("record_finding_action",
               {"p_finding_id": fid, "p_action": "escalated"}).execute()
    rows = service.table("photo_finding_queue").select("*").execute().data
    assert any(r["finding_id"] == fid for r in rows)   # service видит без предиката юриста


def test_accept_requires_reason(subscriber, service, current_ruleset, tobacco_product_id):
    client, uid = subscriber
    _, fid = _finished_inspection_with_finding(client, uid, service, tobacco_product_id)
    with pytest.raises(Exception):
        client.rpc("record_finding_action",
                   {"p_finding_id": fid, "p_action": "accepted_with_reason"}).execute()


def test_sign_requires_verified_lawyer(subscriber, service, current_ruleset, tobacco_product_id):
    client, uid = subscriber
    ins_id, _ = _finished_inspection_with_finding(client, uid, service, tobacco_product_id)
    with pytest.raises(Exception, match="not_a_verified_lawyer"):
        client.rpc("sign_photo_inspection", {"p_inspection_id": ins_id}).execute()
