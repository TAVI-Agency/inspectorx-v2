"""Мок-клиент LegalX/SudX (ADR-0005): контракт + фикстуры на реальном контенте сигарет.

Сценарии из брифа Задачи 3:
- поиск норм по УЗ находит хотя бы один фрагмент по «акцизная марка табак»;
- поиск по КЗ пуст (norms_kz.json — пустой массив, живого КЗ-контента ещё нет);
- поиск судебной практики по статье КоАО возвращает не больше limit кейсов;
- get_client() переключается по env LEGALX_BACKEND: mock (в т.ч. по умолчанию),
  live -> LiveLegalX или ValueError без ключей (полное покрытие ветки live —
  test_legalx_live.py, Задача 42), прочее -> ValueError.
"""
from datetime import date
from decimal import Decimal

import pytest

from importer.build.legalx import CourtCase, LegalXClient, NormFragment, get_client
from importer.build.legalx_mock import MockLegalX


# ── search_norms ──────────────────────────────────────────────────────────

def test_search_norms_uz_finds_fragment_for_cigarette_query():
    client = MockLegalX()
    results = client.search_norms("акцизная марка табак", jurisdiction="UZ")
    assert len(results) >= 1
    assert all(isinstance(r, NormFragment) for r in results)
    # Контракт ADR-0005: все поля должны быть заполнены реальными реквизитами.
    top = results[0]
    assert top.fragment_id and top.act_id and top.act_title
    assert top.article_ref and top.anchor and top.content
    assert top.act_status
    assert isinstance(top.score, float)


def test_search_norms_kz_is_empty_until_kz_fixtures_land():
    client = MockLegalX()
    results = client.search_norms("акцизная марка табак", jurisdiction="KZ")
    assert results == []


def test_search_norms_unranked_query_returns_empty():
    """Запрос без пересечения слов с фикстурами — пустой результат, не ошибка."""
    client = MockLegalX()
    results = client.search_norms("совершенно посторонний запрос про огурцы", jurisdiction="UZ")
    assert results == []


def test_search_norms_respects_limit():
    client = MockLegalX()
    results = client.search_norms("табачной продукции упаковку", jurisdiction="UZ", limit=2)
    assert len(results) <= 2


def test_search_norms_ranks_by_word_overlap_desc():
    """Скор не возрастает по списку — топ-результат релевантнее хвоста."""
    client = MockLegalX()
    results = client.search_norms("маркировка табачной продукции упаковку", jurisdiction="UZ", limit=10)
    assert len(results) >= 2
    scores = [r.score for r in results]
    assert scores == sorted(scores, reverse=True)


def test_search_norms_valid_dates_are_date_or_none():
    client = MockLegalX()
    for r in client.search_norms("табачной продукции", jurisdiction="UZ", limit=10):
        assert r.valid_from is None or isinstance(r.valid_from, date)
        assert r.valid_to is None or isinstance(r.valid_to, date)


# ── search_cases ──────────────────────────────────────────────────────────

def test_search_cases_returns_at_most_five_by_default():
    client = MockLegalX()
    results = client.search_cases("ст. 204 КоАО")
    assert 1 <= len(results) <= 5
    assert all(isinstance(c, CourtCase) for c in results)
    top = results[0]
    assert top.case_url and top.case_title and top.summary and top.outcome
    assert top.amount is None or isinstance(top.amount, Decimal)


def test_search_cases_respects_limit():
    client = MockLegalX()
    results = client.search_cases("ст. 204 КоАО", limit=1)
    assert len(results) <= 1


def test_search_cases_unknown_article_is_empty():
    client = MockLegalX()
    assert client.search_cases("ст. 999 несуществующая КоАО") == []


# ── get_client() / переключение бэкенда ─────────────────────────────────

def test_get_client_mock_backend(monkeypatch):
    monkeypatch.setenv("LEGALX_BACKEND", "mock")
    client = get_client()
    assert isinstance(client, MockLegalX)


def test_get_client_default_is_mock_when_env_unset(monkeypatch):
    monkeypatch.delenv("LEGALX_BACKEND", raising=False)
    client = get_client()
    assert isinstance(client, MockLegalX)


def test_get_client_live_without_env_raises_value_error(monkeypatch):
    """Полное покрытие ветки `live` (успех + перечисление недостающих
    переменных) — `importer/tests/build/test_legalx_live.py` (Задача 42)."""
    monkeypatch.setenv("LEGALX_BACKEND", "live")
    monkeypatch.delenv("LEGALX_SUPABASE_URL", raising=False)
    monkeypatch.delenv("LEGALX_SUPABASE_KEY", raising=False)
    with pytest.raises(ValueError, match="LEGALX_SUPABASE_URL"):
        get_client()


def test_get_client_unknown_backend_raises_value_error(monkeypatch):
    monkeypatch.setenv("LEGALX_BACKEND", "totally-unknown")
    with pytest.raises(ValueError):
        get_client()


def test_mock_satisfies_legalx_client_protocol():
    client: LegalXClient = MockLegalX()
    assert hasattr(client, "search_norms") and hasattr(client, "search_cases")
