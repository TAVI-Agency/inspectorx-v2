from __future__ import annotations

import uuid

import pytest

from .conftest import STACK, requires_db

pytestmark = [pytest.mark.integration, requires_db]

PDF_BYTES = b"%PDF-1.4 test"


def _bucket_field(bucket, name):
    return getattr(bucket, name, None) if not isinstance(bucket, dict) else bucket.get(name)


@pytest.fixture()
def stranger(service):
    """Второй авторизованный подписчик (не anon) — по образцу subscriber из conftest.

    Нужен, чтобы риск 8 («чужой префикс запечатан») проверялся против политики
    `to authenticated`: анонимный клиент у неё нет доступа вообще, поэтому тест
    на анонимном клиенте зелёный даже при дырявой политике вида
    `to authenticated using (true)`.
    """
    from supabase import create_client
    email = f"ix.wave1.stranger.{uuid.uuid4().hex[:10]}@test.local"
    password = "wave1-Passw0rd"
    created = service.auth.admin.create_user(
        {"email": email, "password": password, "email_confirm": True})
    uid = created.user.id
    service.table("profiles").update({"is_subscribed": True}).eq("id", uid).execute()
    client = create_client(STACK["API_URL"], STACK["ANON_KEY"])
    client.auth.sign_in_with_password({"email": email, "password": password})
    yield client, uid
    service.auth.admin.delete_user(uid)


def test_buckets_exist_with_limits(service):
    rows = {_bucket_field(b, "id"): b for b in service.storage.list_buckets()}
    assert set(rows) >= {"packaging-artwork", "packaging-photos", "evidence-crops"}
    assert _bucket_field(rows["packaging-artwork"], "file_size_limit") == 52428800
    assert _bucket_field(rows["packaging-artwork"], "allowed_mime_types") == ["application/pdf"]
    assert _bucket_field(rows["packaging-photos"], "file_size_limit") == 10485760
    assert "image/heic" in _bucket_field(rows["packaging-photos"], "allowed_mime_types")
    assert _bucket_field(rows["evidence-crops"], "file_size_limit") == 2097152
    assert _bucket_field(rows["evidence-crops"], "allowed_mime_types") == [
        "image/jpeg", "image/png"]


def test_own_prefix_write_and_read(subscriber):
    client, uid = subscriber
    path = f"{uid}/test-inspection/0.pdf"
    client.storage.from_("packaging-artwork").upload(
        path, PDF_BYTES, {"content-type": "application/pdf"})
    got = client.storage.from_("packaging-artwork").download(path)
    assert got == PDF_BYTES


def test_foreign_prefix_is_sealed(subscriber, stranger):
    """Главная проверка риска 8: чужой префикс не читается и не пишется — ни анонимным
    клиентом, ни ВТОРЫМ РЕАЛЬНЫМ авторизованным пользователем (политики выданы
    `to authenticated`, поэтому только проверка вторым uid доказывает, что политика
    действительно фильтрует по (storage.foldername(name))[1] = auth.uid(), а не
    пропускает всех authenticated)."""
    client, uid = subscriber
    stranger_client, stranger_uid = stranger
    own_path = f"{uid}/seal/0.pdf"
    client.storage.from_("packaging-artwork").upload(
        own_path, PDF_BYTES, {"content-type": "application/pdf"})

    # анонимный клиент — тоже отвергается (базовый случай)
    from supabase import create_client
    anon = create_client(STACK["API_URL"], STACK["ANON_KEY"])
    with pytest.raises(Exception):
        anon.storage.from_("packaging-artwork").download(own_path)
    with pytest.raises(Exception):
        anon.storage.from_("packaging-artwork").upload(
            f"{uid}/seal/1.pdf", PDF_BYTES, {"content-type": "application/pdf"})

    # второй авторизованный пользователь — главная проверка риска 8
    with pytest.raises(Exception):
        stranger_client.storage.from_("packaging-artwork").download(own_path)
    with pytest.raises(Exception):
        stranger_client.storage.from_("packaging-artwork").upload(
            f"{uid}/seal/2.pdf", PDF_BYTES, {"content-type": "application/pdf"})

    # позитивный контроль: свой префикс у второго пользователя работает —
    # без этого тест был бы вакуумно-зелёным (например, при полностью закрытых политиках)
    stranger_path = f"{stranger_uid}/seal/0.pdf"
    stranger_client.storage.from_("packaging-artwork").upload(
        stranger_path, PDF_BYTES, {"content-type": "application/pdf"})
    got = stranger_client.storage.from_("packaging-artwork").download(stranger_path)
    assert got == PDF_BYTES
