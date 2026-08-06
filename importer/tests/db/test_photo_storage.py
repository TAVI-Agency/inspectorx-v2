from __future__ import annotations

import pytest

from .conftest import STACK, requires_db

pytestmark = [pytest.mark.integration, requires_db]

PDF_BYTES = b"%PDF-1.4 test"


def _bucket_field(bucket, name):
    return getattr(bucket, name, None) if not isinstance(bucket, dict) else bucket.get(name)


def test_buckets_exist_with_limits(service):
    rows = {_bucket_field(b, "id"): b for b in service.storage.list_buckets()}
    assert set(rows) >= {"packaging-artwork", "packaging-photos", "evidence-crops"}
    assert _bucket_field(rows["packaging-artwork"], "file_size_limit") == 52428800
    assert _bucket_field(rows["packaging-photos"], "file_size_limit") == 10485760
    assert "image/heic" in _bucket_field(rows["packaging-photos"], "allowed_mime_types")


def test_own_prefix_write_and_read(subscriber):
    client, uid = subscriber
    path = f"{uid}/test-inspection/0.pdf"
    client.storage.from_("packaging-artwork").upload(
        path, PDF_BYTES, {"content-type": "application/pdf"})
    got = client.storage.from_("packaging-artwork").download(path)
    assert got == PDF_BYTES


def test_foreign_prefix_is_sealed(subscriber, service):
    """Главная проверка риска 8: чужой префикс не читается и не пишется."""
    client, uid = subscriber
    own_path = f"{uid}/seal/0.pdf"
    client.storage.from_("packaging-artwork").upload(
        own_path, PDF_BYTES, {"content-type": "application/pdf"})
    from supabase import create_client
    stranger = create_client(STACK["API_URL"], STACK["ANON_KEY"])
    with pytest.raises(Exception):
        stranger.storage.from_("packaging-artwork").download(own_path)
    with pytest.raises(Exception):
        stranger.storage.from_("packaging-artwork").upload(
            f"{uid}/seal/1.pdf", PDF_BYTES, {"content-type": "application/pdf"})
