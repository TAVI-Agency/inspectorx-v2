"""Задача 14: очередь юриста по находкам фотоконтроля, заключения, подпись.
Тот же паттерн скипа/фикстур, что у test_photo_runtime.py / test_photo_lifecycle.py
(маркер integration, живой ЛОКАЛЬНЫЙ Supabase). Хелпер _finished_inspection_with_finding
живёт в conftest.py — переиспользован Задачей 16.

Ниже также тесты на решение владельца поверх исходного брифа: verified-юрист
получил select-доступ к ЧУЖОМУ отчёту (photo_inspections/photo_findings/…) —
без него кнопка «Подписать вердикт» на /checks/packaging/:id была недостижима
(RLS "own read" из 20260810100000_photo_runtime.sql отдавала лоеру пустой bundle)."""
from __future__ import annotations

import uuid

import pytest

from .conftest import STACK, _finished_inspection_with_finding, requires_db

pytestmark = [pytest.mark.integration, requires_db]


@pytest.fixture()
def verified_lawyer(service):
    """Второй пользователь — верифицированный юрист, НЕ владелец никакой проверки.
    Возвращает (client, user_id), как и `subscriber`."""
    from supabase import create_client
    email = f"ix.wave1.lawyer.{uuid.uuid4().hex[:10]}@test.local"
    password = "wave1-Passw0rd"
    created = service.auth.admin.create_user(
        {"email": email, "password": password, "email_confirm": True})
    uid = created.user.id
    service.table("lawyer_profiles").insert(
        {"user_id": uid, "display_name": "Тестовый юрист", "credentials": "тест",
         "status": "verified"}).execute()
    client = create_client(STACK["API_URL"], STACK["ANON_KEY"])
    client.auth.sign_in_with_password({"email": email, "password": password})
    yield client, uid
    service.auth.admin.delete_user(uid)


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


def test_verified_lawyer_reads_foreign_inspection_and_findings(
        subscriber, service, verified_lawyer, current_ruleset, tobacco_product_id):
    """Без этого юрист не может открыть /checks/packaging/:id чужой проверки,
    чтобы увидеть кнопку «Подписать вердикт» (решение владельца поверх брифа)."""
    client, uid = subscriber
    lawyer_client, _ = verified_lawyer
    ins_id, fid = _finished_inspection_with_finding(client, uid, service, tobacco_product_id)

    ins_rows = lawyer_client.table("photo_inspections").select("id").eq("id", ins_id).execute().data
    assert any(r["id"] == ins_id for r in ins_rows)

    f_rows = lawyer_client.table("photo_findings").select("id").eq("id", fid).execute().data
    assert any(r["id"] == fid for r in f_rows)

    # события/ассеты той же проверки — тоже должны читаться (полный bundle отчёта)
    ev_rows = lawyer_client.table("photo_inspection_events").select("inspection_id") \
        .eq("inspection_id", ins_id).execute().data
    assert len(ev_rows) > 0
    asset_rows = lawyer_client.table("photo_assets").select("inspection_id") \
        .eq("inspection_id", ins_id).execute().data
    assert len(asset_rows) > 0


def test_non_lawyer_still_blocked_from_foreign_inspection(
        subscriber, service, current_ruleset, tobacco_product_id):
    """Негативный контроль: обычный (не-юрист) подписчик по-прежнему не видит чужую проверку."""
    client, uid = subscriber
    ins_id, _ = _finished_inspection_with_finding(client, uid, service, tobacco_product_id)

    from supabase import create_client
    other_email = f"ix.wave1.other.{uuid.uuid4().hex[:10]}@test.local"
    other_password = "wave1-Passw0rd"
    created = service.auth.admin.create_user(
        {"email": other_email, "password": other_password, "email_confirm": True})
    other_uid = created.user.id
    try:
        other_client = create_client(STACK["API_URL"], STACK["ANON_KEY"])
        other_client.auth.sign_in_with_password(
            {"email": other_email, "password": other_password})
        rows = other_client.table("photo_inspections").select("id").eq("id", ins_id).execute().data
        assert not any(r["id"] == ins_id for r in rows)
    finally:
        service.auth.admin.delete_user(other_uid)


def test_lawyer_cannot_write_foreign_inspection(
        subscriber, service, verified_lawyer, current_ruleset, tobacco_product_id):
    """Новая select-политика не открывает insert/update — грант на них у
    authenticated отозван ещё в 20260810100000_photo_runtime.sql, эта проверка
    защищает именно от регрессии (что новая политика их случайно не вернула)."""
    client, uid = subscriber
    lawyer_client, _ = verified_lawyer
    ins_id, _ = _finished_inspection_with_finding(client, uid, service, tobacco_product_id)
    with pytest.raises(Exception):
        lawyer_client.table("photo_inspections").update(
            {"last_error": "hacked"}).eq("id", ins_id).execute()


# ── Ревью после второго прохода: Critical (анонимное чтение вью) + Important
# (дубли строк при повторной эскалации) + MINOR (published-заключения других
# юристов) ─────────────────────────────────────────────────────────────────

def test_queue_blocks_anonymous_access(subscriber, service, current_ruleset, tobacco_product_id):
    """Critical-фикс: было `(select auth.uid()) is null` как эскейп для
    service_role — у anon-ключа auth.uid() тоже null, вместе с `grant select
    … to anon` вью читалась анонимно (подтверждено живым прогоном до фикса).
    Теперь grant сужен до authenticated, предикат — `auth.role() =
    'service_role'`: anon либо получает permission-denied, либо (если PostgREST
    смолчит) обязан не видеть чужую находку."""
    client, uid = subscriber
    ins_id, fid = _finished_inspection_with_finding(client, uid, service, tobacco_product_id)
    client.rpc("record_finding_action",
               {"p_finding_id": fid, "p_action": "escalated"}).execute()

    from postgrest.exceptions import APIError
    from supabase import create_client
    anon_client = create_client(STACK["API_URL"], STACK["ANON_KEY"])
    try:
        rows = anon_client.table("photo_finding_queue").select("*").execute().data
    except APIError:
        return  # permission denied (нет select-гранта) — корректный, даже более строгий исход
    # если запрос прошёл (напр. пустой select без ошибки) — строка чужой находки
    # не должна утечь; ловим только ожидаемый APIError, а не bare Exception,
    # чтобы AssertionError ниже не проглатывался молча
    assert not any(r["finding_id"] == fid for r in rows)


def test_queue_hides_from_non_lawyer_authenticated(
        subscriber, service, current_ruleset, tobacco_product_id):
    """Негативный контроль на саму вью: обычный подписчик (authenticated,
    но не verified-юрист) не видит очередь, даже свою собственную эскалацию."""
    client, uid = subscriber
    ins_id, fid = _finished_inspection_with_finding(client, uid, service, tobacco_product_id)
    client.rpc("record_finding_action",
               {"p_finding_id": fid, "p_action": "escalated"}).execute()
    rows = client.table("photo_finding_queue").select("*").execute().data
    assert not any(r["finding_id"] == fid for r in rows)


def test_queue_visible_to_verified_lawyer(
        subscriber, service, verified_lawyer, current_ruleset, tobacco_product_id):
    """Позитивный контроль на саму вью (не через service_role, как в первом
    тесте файла, а через реальный клиент verified-юриста)."""
    client, uid = subscriber
    lawyer_client, _ = verified_lawyer
    ins_id, fid = _finished_inspection_with_finding(client, uid, service, tobacco_product_id)
    client.rpc("record_finding_action",
               {"p_finding_id": fid, "p_action": "escalated"}).execute()
    rows = lawyer_client.table("photo_finding_queue").select("*").execute().data
    assert any(r["finding_id"] == fid for r in rows)


def test_repeated_escalation_does_not_duplicate_queue_row(
        subscriber, service, verified_lawyer, current_ruleset, tobacco_product_id):
    """Important-фикс: `record_finding_action('escalated')` не защищён
    уникальным индексом — повторный вызов раньше плодил вторую строку вью
    (join по `photo_finding_actions`). `distinct on (f.id)` в вью схлопывает
    это обратно в одну строку."""
    client, uid = subscriber
    lawyer_client, _ = verified_lawyer
    ins_id, fid = _finished_inspection_with_finding(client, uid, service, tobacco_product_id)
    client.rpc("record_finding_action",
               {"p_finding_id": fid, "p_action": "escalated"}).execute()
    client.rpc("record_finding_action",
               {"p_finding_id": fid, "p_action": "escalated"}).execute()
    rows = lawyer_client.table("photo_finding_queue").select("*") \
        .eq("finding_id", fid).execute().data
    assert len(rows) == 1


def test_lawyer_reads_other_lawyers_published_review(
        subscriber, service, verified_lawyer, current_ruleset, tobacco_product_id):
    """MINOR-фикс: без политики "lawyer reads published" блок «Заключения
    юристов» в чужом отчёте был бы пуст для юриста, который сам заключение
    не писал — только автор ("lawyer reads own") и владелец проверки
    ("owner reads published") могли его увидеть."""
    client, uid = subscriber
    _, author_uid = verified_lawyer
    _, fid = _finished_inspection_with_finding(client, uid, service, tobacco_product_id)

    review = service.table("photo_finding_reviews").insert({
        "finding_id": fid, "lawyer_id": author_uid, "verdict": "confirm",
        "comment_text": "тестовое опубликованное заключение по находке"}).execute().data[0]
    service.table("photo_finding_reviews").update(
        {"status": "published"}).eq("id", review["id"]).execute()

    from supabase import create_client
    other_lawyer_email = f"ix.wave1.lawyer2.{uuid.uuid4().hex[:10]}@test.local"
    other_lawyer_password = "wave1-Passw0rd"
    created = service.auth.admin.create_user(
        {"email": other_lawyer_email, "password": other_lawyer_password, "email_confirm": True})
    other_uid = created.user.id
    try:
        service.table("lawyer_profiles").insert(
            {"user_id": other_uid, "display_name": "Второй тестовый юрист",
             "credentials": "тест", "status": "verified"}).execute()
        other_client = create_client(STACK["API_URL"], STACK["ANON_KEY"])
        other_client.auth.sign_in_with_password(
            {"email": other_lawyer_email, "password": other_lawyer_password})
        rows = other_client.table("photo_finding_reviews").select("id") \
            .eq("finding_id", fid).eq("status", "published").execute().data
        assert any(r["id"] == review["id"] for r in rows)
    finally:
        service.auth.admin.delete_user(other_uid)
