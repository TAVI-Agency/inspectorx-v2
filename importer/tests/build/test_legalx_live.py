"""Тесты живого клиента LegalX (Задача 42, шаг 1): PostgREST RPC на мок-HTTP.

Мок-транспорт — `httpx.MockTransport` (respx в зависимостях проекта нет,
бриф задачи запрещает добавлять новые). Приёмка на реально живом LegalX
(шаг 2, гейт D1: `build eval-golden` с `LEGALX_BACKEND=live`, hit-rate ≥
мокового baseline) сюда не входит — см. докстринг `legalx_live.py`.
"""
from __future__ import annotations

import json
from datetime import date
from decimal import Decimal

import httpx
import pytest

from importer.build.legalx import CourtCase, NormFragment, get_client
from importer.build.legalx_live import LegalXLiveError, LiveLegalX

BASE_URL = "https://legalx-project.supabase.co"
API_KEY = "sb_publishable_test_key"


def _client(handler) -> LiveLegalX:
    transport = httpx.MockTransport(handler)
    return LiveLegalX(base_url=BASE_URL, api_key=API_KEY, transport=transport)


# ── search_norms: happy path + маппинг ──────────────────────────────────

def test_search_norms_maps_json_response_to_dataclasses():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url == f"{BASE_URL}/rest/v1/rpc/search_norms"
        assert request.headers["apikey"] == API_KEY
        assert request.headers["authorization"] == f"Bearer {API_KEY}"
        assert request.headers["content-type"] == "application/json"
        return httpx.Response(
            200,
            json=[
                {
                    "fragment_id": "f1",
                    "act_id": "a1",
                    "act_title": "ТР О безопасности табачной продукции",
                    "article_ref": "ст. 5",
                    "anchor": "p5",
                    "content": "текст фрагмента про акцизную марку",
                    "act_status": "active",
                    "valid_from": "2024-01-01",
                    "valid_to": None,
                    "score": 0.87,
                },
            ],
        )

    client = _client(handler)
    results = client.search_norms("акцизная марка табак", jurisdiction="UZ", limit=5)

    assert results == [
        NormFragment(
            fragment_id="f1",
            act_id="a1",
            act_title="ТР О безопасности табачной продукции",
            article_ref="ст. 5",
            anchor="p5",
            content="текст фрагмента про акцизную марку",
            act_status="active",
            valid_from=date(2024, 1, 1),
            valid_to=None,
            score=0.87,
        )
    ]


def test_search_norms_sends_contract_parameters():
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json=[])

    client = _client(handler)
    client.search_norms("запрос", jurisdiction="UZ", domains=["tobacco"], limit=3)

    assert captured["body"] == {
        "p_query": "запрос",
        "p_jurisdiction": "UZ",
        "p_domains": ["tobacco"],
        "p_limit": 3,
    }


def test_search_norms_null_dates_become_none():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json=[
                {
                    "fragment_id": "f2", "act_id": "a2", "act_title": "Акт",
                    "article_ref": "ст. 1", "anchor": "p1", "content": "текст",
                    "act_status": "pending", "valid_from": None, "valid_to": None,
                    "score": 0.1,
                },
            ],
        )

    client = _client(handler)
    results = client.search_norms("запрос", jurisdiction="UZ")
    assert results[0].valid_from is None
    assert results[0].valid_to is None


def test_search_norms_empty_result_is_not_an_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[])

    client = _client(handler)
    assert client.search_norms("посторонний запрос", jurisdiction="UZ") == []


# ── search_cases: happy path + Decimal ──────────────────────────────────

def test_search_cases_maps_amount_to_decimal_and_none_safe():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url == f"{BASE_URL}/rest/v1/rpc/search_cases"
        return httpx.Response(
            200,
            json=[
                {
                    "case_url": "https://sudx.uz/1", "case_title": "Дело №1",
                    "summary": "штраф за отсутствие марки", "outcome": "удовлетворено",
                    "amount": "1500000.50",
                },
                {
                    "case_url": "https://sudx.uz/2", "case_title": "Дело №2",
                    "summary": "предупреждение", "outcome": "отказано",
                    "amount": None,
                },
            ],
        )

    client = _client(handler)
    results = client.search_cases("ст. 204 КоАО", topic="акциз", limit=2)

    assert results == [
        CourtCase(
            case_url="https://sudx.uz/1", case_title="Дело №1",
            summary="штраф за отсутствие марки", outcome="удовлетворено",
            amount=Decimal("1500000.50"),
        ),
        CourtCase(
            case_url="https://sudx.uz/2", case_title="Дело №2",
            summary="предупреждение", outcome="отказано", amount=None,
        ),
    ]


def test_search_cases_sends_contract_parameters():
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json=[])

    client = _client(handler)
    client.search_cases("ст. 204 КоАО", limit=1)

    assert captured["body"] == {"p_article": "ст. 204 КоАО", "p_topic": None, "p_limit": 1}


# ── ретраи и ошибки ──────────────────────────────────────────────────────

def test_500_then_200_retries_once_and_succeeds():
    attempts = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["n"] += 1
        if attempts["n"] == 1:
            return httpx.Response(500, text="internal error")
        return httpx.Response(200, json=[])

    client = _client(handler)
    results = client.search_norms("запрос", jurisdiction="UZ")
    assert results == []
    assert attempts["n"] == 2


def test_500_twice_raises_legalx_live_error():
    attempts = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["n"] += 1
        return httpx.Response(500, text="internal error")

    client = _client(handler)
    with pytest.raises(LegalXLiveError) as exc_info:
        client.search_norms("запрос", jurisdiction="UZ")

    assert attempts["n"] == 2
    assert exc_info.value.status_code == 500
    assert "internal error" in str(exc_info.value)


def test_401_raises_without_retry():
    attempts = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["n"] += 1
        return httpx.Response(401, text="Invalid API key")

    client = _client(handler)
    with pytest.raises(LegalXLiveError) as exc_info:
        client.search_norms("запрос", jurisdiction="UZ")

    assert attempts["n"] == 1  # 4xx — без ретрая
    assert exc_info.value.status_code == 401
    assert "Invalid API key" in str(exc_info.value)


def test_timeout_retries_once_and_succeeds():
    attempts = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["n"] += 1
        if attempts["n"] == 1:
            raise httpx.ConnectTimeout("timed out", request=request)
        return httpx.Response(200, json=[])

    client = _client(handler)
    results = client.search_norms("запрос", jurisdiction="UZ")
    assert results == []
    assert attempts["n"] == 2


def test_timeout_twice_raises_legalx_live_error():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("timed out", request=request)

    client = _client(handler)
    with pytest.raises(LegalXLiveError):
        client.search_norms("запрос", jurisdiction="UZ")


def test_timeout_is_configurable():
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json=[]))
    client = LiveLegalX(base_url=BASE_URL, api_key=API_KEY, timeout=5.0, transport=transport)
    assert client._client.timeout.read == 5.0


# ── get_client(): переключение на live через env ────────────────────────

def test_get_client_live_with_env_returns_live_client(monkeypatch):
    monkeypatch.setenv("LEGALX_BACKEND", "live")
    monkeypatch.setenv("LEGALX_SUPABASE_URL", BASE_URL)
    monkeypatch.setenv("LEGALX_SUPABASE_KEY", API_KEY)

    client = get_client()
    assert isinstance(client, LiveLegalX)


def test_get_client_live_without_env_raises_value_error_listing_missing_vars(monkeypatch):
    monkeypatch.setenv("LEGALX_BACKEND", "live")
    monkeypatch.delenv("LEGALX_SUPABASE_URL", raising=False)
    monkeypatch.delenv("LEGALX_SUPABASE_KEY", raising=False)

    with pytest.raises(ValueError) as exc_info:
        get_client()

    assert "LEGALX_SUPABASE_URL" in str(exc_info.value)
    assert "LEGALX_SUPABASE_KEY" in str(exc_info.value)


def test_get_client_live_missing_only_key_lists_only_key(monkeypatch):
    monkeypatch.setenv("LEGALX_BACKEND", "live")
    monkeypatch.setenv("LEGALX_SUPABASE_URL", BASE_URL)
    monkeypatch.delenv("LEGALX_SUPABASE_KEY", raising=False)

    with pytest.raises(ValueError) as exc_info:
        get_client()

    assert "LEGALX_SUPABASE_KEY" in str(exc_info.value)
    assert "LEGALX_SUPABASE_URL" not in str(exc_info.value)
