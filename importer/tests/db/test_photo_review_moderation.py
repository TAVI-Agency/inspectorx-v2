"""Модерация заключений юриста по находкам фотоконтроля (вариант «б»:
публикует модератор через экран, автопубликации нет).

Миграция — supabase/migrations/20260810160000_photo_review_moderation.sql.
Паттерн фикстур/скипа тот же, что у test_photo_reviews.py (маркер integration,
живой ЛОКАЛЬНЫЙ Supabase); `verified_lawyer` переиспользуем оттуда.
"""
from __future__ import annotations

import re
import subprocess
import uuid

import pytest

from .conftest import ROOT, STACK, _finished_inspection_with_finding, requires_db
from .test_photo_reviews import verified_lawyer  # noqa: F401  (фикстура)

pytestmark = [pytest.mark.integration, requires_db]

QUEUE_VIEWS = ("public.photo_finding_queue", "public.photo_review_moderation_queue")


def _db_container() -> str:
    """Имя контейнера БД локального стека: `supabase_db_<project_id>`."""
    m = re.search(r'^project_id\s*=\s*"([^"]+)"',
                  (ROOT / "supabase" / "config.toml").read_text(), re.M)
    assert m, "project_id не найден в supabase/config.toml"
    return f"supabase_db_{m.group(1)}"


def _psql(query: str) -> str:
    """Сырой SQL на локальной базе. PostgREST системные каталоги не отдаёт, а
    psycopg в .venv-importer нет — ходим psql'ом внутри контейнера БД."""
    proc = subprocess.run(
        ["docker", "exec", _db_container(), "psql", "-U", "postgres", "-d", "postgres",
         "-tAc", query],
        capture_output=True, text=True, timeout=60)
    assert proc.returncode == 0, proc.stderr
    return proc.stdout.strip()


def _has_select(role: str, relation: str) -> bool:
    return _psql(f"select has_table_privilege('{role}', '{relation}', 'select')") == "t"


@pytest.fixture()
def moderator(service):
    """Пользователь с `profiles.is_moderator = true` — флаг ставится только
    service_role-ом (клиентский грант update его не покрывает)."""
    from supabase import create_client
    email = f"ix.wave1.moder.{uuid.uuid4().hex[:10]}@test.local"
    password = "wave1-Passw0rd"
    created = service.auth.admin.create_user(
        {"email": email, "password": password, "email_confirm": True})
    uid = created.user.id
    service.table("profiles").update({"is_moderator": True}).eq("id", uid).execute()
    client = create_client(STACK["API_URL"], STACK["ANON_KEY"])
    client.auth.sign_in_with_password({"email": email, "password": password})
    yield client, uid
    service.auth.admin.delete_user(uid)


def _pending_review(service, fid: str, lawyer_uid: str) -> str:
    """Заключение юриста на находке — ровно то, что кладёт витрина
    (insert без status: default 'pending')."""
    row = service.table("photo_finding_reviews").insert({
        "finding_id": fid, "lawyer_id": lawyer_uid, "verdict": "confirm",
        "comment_text": "заключение на модерацию, длиннее двадцати символов"},
    ).execute().data[0]
    return row["id"]


# ── Негатив: обычный пользователь ───────────────────────────────────────────

def test_non_moderator_cannot_call_rpc(
        subscriber, service, verified_lawyer, current_ruleset, tobacco_product_id):
    client, uid = subscriber
    _, lawyer_uid = verified_lawyer
    _, fid = _finished_inspection_with_finding(client, uid, service, tobacco_product_id)
    review_id = _pending_review(service, fid, lawyer_uid)

    with pytest.raises(Exception, match="not_a_moderator"):
        client.rpc("moderate_photo_finding_review",
                   {"p_review_id": review_id, "p_decision": "published"}).execute()

    # статус не изменился
    row = service.table("photo_finding_reviews").select("status").eq(
        "id", review_id).execute().data[0]
    assert row["status"] == "pending"


def test_lawyer_cannot_publish_own_review(
        subscriber, service, verified_lawyer, current_ruleset, tobacco_product_id):
    """Ключевой инвариант варианта «б»: автор заключения себя не публикует."""
    client, uid = subscriber
    lawyer_client, lawyer_uid = verified_lawyer
    _, fid = _finished_inspection_with_finding(client, uid, service, tobacco_product_id)
    review_id = _pending_review(service, fid, lawyer_uid)

    with pytest.raises(Exception, match="not_a_moderator"):
        lawyer_client.rpc("moderate_photo_finding_review",
                          {"p_review_id": review_id, "p_decision": "published"}).execute()


def test_non_moderator_does_not_see_foreign_pending(
        subscriber, service, verified_lawyer, current_ruleset, tobacco_product_id):
    """Владелец проверки не видит pending-заключение ни в таблице
    ("owner reads published" — только published), ни в очереди модерации."""
    client, uid = subscriber
    _, lawyer_uid = verified_lawyer
    _, fid = _finished_inspection_with_finding(client, uid, service, tobacco_product_id)
    review_id = _pending_review(service, fid, lawyer_uid)

    rows = client.table("photo_finding_reviews").select("id").eq(
        "id", review_id).execute().data
    assert not any(r["id"] == review_id for r in rows)

    queue = client.table("photo_review_moderation_queue").select("review_id").execute().data
    assert not any(r["review_id"] == review_id for r in queue)


@pytest.mark.parametrize("relation", QUEUE_VIEWS)
def test_queue_views_have_no_anon_privilege(relation):
    """Important-фикс ревью: `grant select … to authenticated` НИЧЕГО не сужает —
    default privileges Supabase уже дали select всем ролям, и от анонимного
    чтения очередей держал только WHERE-предикат внутри вью. Проверяем сам
    ГРАНТ (`has_table_privilege`), а не поведение PostgREST: только так тест
    ловит регрессию привилегии, а не гадает по коду ошибки HTTP-слоя."""
    assert _has_select("anon", relation) is False
    assert _has_select("authenticated", relation) is True


@pytest.mark.parametrize("relation", QUEUE_VIEWS)
def test_queue_views_are_security_barrier(relation):
    """Minor того же ревью: предикат безопасности вью должен вычисляться до
    пользовательских фильтров запроса."""
    assert _psql(
        f"select 'security_barrier=true' = any(c.reloptions) from pg_class c "
        f"where c.oid = '{relation}'::regclass") == "t"


def test_moderation_queue_blocks_anonymous_access(
        subscriber, service, verified_lawyer, current_ruleset, tobacco_product_id):
    """Тот же Critical, что чинили у photo_finding_queue: у anon-ключа
    auth.uid() тоже null, поэтому предикат вью — `auth.role()`. После ревока
    привилегии у anon исход ровно один — отказ на уровне прав, поэтому тест
    строгий: «пустой ответ» больше не засчитывается."""
    client, uid = subscriber
    _, lawyer_uid = verified_lawyer
    _, fid = _finished_inspection_with_finding(client, uid, service, tobacco_product_id)
    _pending_review(service, fid, lawyer_uid)

    from postgrest.exceptions import APIError
    from supabase import create_client
    anon_client = create_client(STACK["API_URL"], STACK["ANON_KEY"])
    with pytest.raises(APIError):
        anon_client.table("photo_review_moderation_queue").select("*").execute()


# ── Позитив: модератор ──────────────────────────────────────────────────────

def test_moderator_sees_pending_and_publishes(
        subscriber, service, verified_lawyer, moderator,
        current_ruleset, tobacco_product_id):
    """Главный сквозной путь: модератор видит pending в очереди, публикует —
    и заключение появляется у владельца проверки (RLS "owner reads published"
    уже работала, не хватало именно перехода)."""
    client, uid = subscriber
    _, lawyer_uid = verified_lawyer
    mod_client, mod_uid = moderator
    _, fid = _finished_inspection_with_finding(client, uid, service, tobacco_product_id)
    review_id = _pending_review(service, fid, lawyer_uid)

    queue = mod_client.table("photo_review_moderation_queue").select("*").execute().data
    row = next((r for r in queue if r["review_id"] == review_id), None)
    assert row is not None
    # экран показывает контекст находки и автора — он приходит из самой вью
    assert row["lawyer_name"]
    assert row["comment_text"]
    assert row["finding_id"] == fid

    # прямое чтение таблицы модератору тоже открыто (политика "moderator reads pending")
    direct = mod_client.table("photo_finding_reviews").select("id").eq(
        "id", review_id).execute().data
    assert any(r["id"] == review_id for r in direct)

    mod_client.rpc("moderate_photo_finding_review",
                   {"p_review_id": review_id, "p_decision": "published"}).execute()

    stored = service.table("photo_finding_reviews").select(
        "status, published_at, moderated_by, moderated_at").eq("id", review_id).execute().data[0]
    assert stored["status"] == "published"
    assert stored["published_at"] is not None
    assert stored["moderated_at"] is not None
    assert stored["moderated_by"] == mod_uid

    # владелец проверки теперь видит заключение
    owner_rows = client.table("photo_finding_reviews").select("id, comment_text").eq(
        "finding_id", fid).execute().data
    assert any(r["id"] == review_id for r in owner_rows)

    # и очередь модерации опустела по этой строке
    queue_after = mod_client.table("photo_review_moderation_queue").select(
        "review_id").execute().data
    assert not any(r["review_id"] == review_id for r in queue_after)


def test_rejected_review_stays_hidden_from_owner(
        subscriber, service, verified_lawyer, moderator,
        current_ruleset, tobacco_product_id):
    client, uid = subscriber
    _, lawyer_uid = verified_lawyer
    mod_client, _ = moderator
    _, fid = _finished_inspection_with_finding(client, uid, service, tobacco_product_id)
    review_id = _pending_review(service, fid, lawyer_uid)

    mod_client.rpc("moderate_photo_finding_review",
                   {"p_review_id": review_id, "p_decision": "rejected"}).execute()

    stored = service.table("photo_finding_reviews").select(
        "status, published_at").eq("id", review_id).execute().data[0]
    assert stored["status"] == "rejected"
    assert stored["published_at"] is None      # отклонённое не «публикуется» задним числом

    owner_rows = client.table("photo_finding_reviews").select("id").eq(
        "finding_id", fid).execute().data
    assert not any(r["id"] == review_id for r in owner_rows)


def test_second_moderation_fails(
        subscriber, service, verified_lawyer, moderator,
        current_ruleset, tobacco_product_id):
    """Переход разрешён только из 'pending': повтор (в т.ч. вторая вкладка)
    не перезаписывает уже принятое решение."""
    client, uid = subscriber
    _, lawyer_uid = verified_lawyer
    mod_client, _ = moderator
    _, fid = _finished_inspection_with_finding(client, uid, service, tobacco_product_id)
    review_id = _pending_review(service, fid, lawyer_uid)

    mod_client.rpc("moderate_photo_finding_review",
                   {"p_review_id": review_id, "p_decision": "published"}).execute()
    with pytest.raises(Exception, match="review_not_pending"):
        mod_client.rpc("moderate_photo_finding_review",
                       {"p_review_id": review_id, "p_decision": "rejected"}).execute()

    stored = service.table("photo_finding_reviews").select("status").eq(
        "id", review_id).execute().data[0]
    assert stored["status"] == "published"


def test_unknown_decision_rejected(
        subscriber, service, verified_lawyer, moderator,
        current_ruleset, tobacco_product_id):
    client, uid = subscriber
    _, lawyer_uid = verified_lawyer
    mod_client, _ = moderator
    _, fid = _finished_inspection_with_finding(client, uid, service, tobacco_product_id)
    review_id = _pending_review(service, fid, lawyer_uid)

    with pytest.raises(Exception, match="bad_decision"):
        mod_client.rpc("moderate_photo_finding_review",
                       {"p_review_id": review_id, "p_decision": "approved"}).execute()


def test_moderator_cannot_update_review_directly(
        subscriber, service, verified_lawyer, moderator,
        current_ruleset, tobacco_product_id):
    """RPC — единственный путь: select-политика модератора не открывает update
    (грант на него у authenticated отозван в 20260810100000_photo_runtime.sql)."""
    client, uid = subscriber
    _, lawyer_uid = verified_lawyer
    mod_client, _ = moderator
    _, fid = _finished_inspection_with_finding(client, uid, service, tobacco_product_id)
    review_id = _pending_review(service, fid, lawyer_uid)

    try:
        mod_client.table("photo_finding_reviews").update(
            {"status": "published"}).eq("id", review_id).execute()
    except Exception:
        pass  # permission denied — ожидаемый исход
    stored = service.table("photo_finding_reviews").select("status").eq(
        "id", review_id).execute().data[0]
    assert stored["status"] == "pending"


def test_moderator_flag_not_self_settable(subscriber, service):
    """Флаг ставит только владелец SQL-ом: колоночный грант update на profiles
    покрывает лишь full_name/phone/company (20260711120001_rls.sql)."""
    client, uid = subscriber
    try:
        client.table("profiles").update({"is_moderator": True}).eq("id", uid).execute()
    except Exception:
        pass
    stored = service.table("profiles").select("is_moderator").eq("id", uid).execute().data[0]
    assert stored["is_moderator"] is False
