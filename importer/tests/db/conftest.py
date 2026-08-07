"""Интеграционные тесты фотоконтроля: живой ЛОКАЛЬНЫЙ Supabase.
Паттерн скипа — тот же, что у test_eval_golden.py (маркер integration)."""
from __future__ import annotations

import json
import subprocess
import uuid
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]


def _status() -> dict | None:
    try:
        proc = subprocess.run(["supabase", "status", "-o", "json"], cwd=ROOT,
                              capture_output=True, text=True, timeout=60)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0:
        return None
    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return None
    # остановленный стек тоже отдаёт JSON — но без адреса API
    if not data.get("API_URL") or not data.get("SERVICE_ROLE_KEY"):
        return None
    return data


STACK = _status()
requires_db = pytest.mark.skipif(
    STACK is None,
    reason="локальный Supabase не поднят (supabase db start && supabase db reset --local)")


@pytest.fixture(scope="session")
def service():
    from supabase import create_client
    return create_client(STACK["API_URL"], STACK["SERVICE_ROLE_KEY"])


@pytest.fixture()
def subscriber(service):
    """Свежий подписчик: auth-юзер + is_subscribed. Возвращает (client, user_id)."""
    from supabase import create_client
    email = f"ix.wave1.{uuid.uuid4().hex[:10]}@test.local"
    password = "wave1-Passw0rd"
    created = service.auth.admin.create_user(
        {"email": email, "password": password, "email_confirm": True})
    uid = created.user.id
    service.table("profiles").update({"is_subscribed": True}).eq("id", uid).execute()
    client = create_client(STACK["API_URL"], STACK["ANON_KEY"])
    client.auth.sign_in_with_password({"email": email, "password": password})
    yield client, uid
    service.auth.admin.delete_user(uid)


@pytest.fixture(scope="session")
def current_ruleset(service):
    sha = "a" * 64
    # сначала снять is_current с чужих строк: частичный уникальный индекс
    # ruleset_versions_current_uidx допускает ровно одну текущую версию
    service.table("ruleset_versions").update({"is_current": False}).neq(
        "sha256", sha).eq("is_current", True).execute()
    service.table("ruleset_versions").upsert(
        {"sha256": sha, "version": "test-a", "packs": {}, "checks_count": 364,
         "is_current": True}).execute()
    return sha


@pytest.fixture(scope="session")
def tobacco_product_id(service) -> str:
    rows = service.table("products").select("id").like("hs_code", "2402%").limit(1).execute().data
    if rows:
        return rows[0]["id"]
    # products: hs_code ~ '^[0-9]{2,10}$', name_ru not null, hierarchy_path jsonb
    ins = service.table("products").insert(
        {"hs_code": "2402209000", "hierarchy_path": ["test"], "name_ru": "test tobacco"}).execute()
    return ins.data[0]["id"]


def _finished_inspection_with_finding(client, uid, service, product_id,
                                      requirement_id=None, key="rev-1"):
    """Заявка -> finalize с одной находкой (severity=critical, status=fail).
    Общий хелпер Задачи 14 (очередь юриста) и Задачи 16 (устаревание
    вердиктов) — живёт здесь, чтобы оба модуля тестов его переиспользовали."""
    ins_id = client.rpc("request_photo_inspection", {
        "p_product_id": product_id, "p_level": "consumer", "p_markets": ["UZ"],
        "p_source_kind": "master_pdf",
        "p_asset_paths": [f"{uid}/{key}/0.pdf"], "p_idempotency_key": key}).execute().data
    service.rpc("finalize_photo_inspection", {
        "p_inspection_id": ins_id, "p_outcome": "done",
        "p_payload": {"overall": "fail", "decided": 1, "checked": 10,
                      "findings": [{"checkpoint_id": "uz.warning.text",
                                    "rule_ref": "tobacco.uz.warning",
                                    "requirement_id": requirement_id,
                                    "group_key": "warnings", "kind": "text_semantic",
                                    "severity": "critical", "status": "fail",
                                    "decided_by": "pdf_text",
                                    "confidence_class": "machine_read",
                                    "message": "нет предупреждения"}],
                      "not_checkable": [], "facts": [], "model_calls": [], "assets": []}}
    ).execute()
    fid = service.table("photo_findings").select("id").eq(
        "inspection_id", ins_id).execute().data[0]["id"]
    return ins_id, fid
