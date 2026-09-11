"""Бэкенды веб-поиска Serper/Tavily: тело запроса, маппинг ответа, allowlist,
ошибки HTTP -> WebSearchError, пусто = «не нашёл»."""
import json

import httpx
import pytest

from importer.build.websearch import (
    SerperWebSearcher, TavilyWebSearcher, WebSearchError, filter_allowed, get_web_searcher,
)


def _transport(calls, status=200, body=None):
    def handler(request):
        calls.append(request)
        return httpx.Response(status, json=body if body is not None else {})
    return httpx.MockTransport(handler)


def test_serper_maps_organic_and_sends_locale():
    calls = []
    body = {"organic": [
        {"title": "ПКМ-737", "link": "https://lex.uz/docs/5118476", "snippet": "маркировка"},
        {"title": "спам", "link": "https://example.com/x", "snippet": "…"},
    ]}
    s = SerperWebSearcher("key", allowed_domains=("lex.uz", "gov.uz"),
                          client=httpx.Client(transport=_transport(calls, body=body)))
    out = s.search("маркировка молока")
    assert out == [{"title": "ПКМ-737", "url": "https://lex.uz/docs/5118476", "snippet": "маркировка"}]
    req = calls[0]
    assert str(req.url) == "https://google.serper.dev/search"
    assert req.headers["x-api-key"] == "key"
    assert json.loads(req.content) == {"q": "маркировка молока", "gl": "uz", "hl": "ru", "num": 10}


def test_serper_http_error_raises():
    s = SerperWebSearcher("key", client=httpx.Client(transport=_transport([], status=403)))
    with pytest.raises(WebSearchError, match="serper.*403"):
        s.search("q")


def test_tavily_maps_results_and_include_domains():
    calls = []
    body = {"results": [{"title": "T", "url": "https://consumer.gov.uz/a", "content": "текст"}]}
    t = TavilyWebSearcher("tk", allowed_domains=("gov.uz",),
                          client=httpx.Client(transport=_transport(calls, body=body)))
    assert t.search("q") == [{"title": "T", "url": "https://consumer.gov.uz/a", "snippet": "текст"}]
    sent = json.loads(calls[0].content)
    assert sent["query"] == "q" and sent["include_domains"] == ["gov.uz"]
    assert sent["country"] == "uzbekistan"
    assert calls[0].headers["authorization"] == "Bearer tk"


def test_filter_allowed_matches_host_suffix_only():
    results = [
        {"title": "", "url": "https://lex.uz/docs/1", "snippet": ""},
        {"title": "", "url": "https://sub.lex.uz/x", "snippet": ""},
        {"title": "", "url": "https://notlex.uz/x", "snippet": ""},
    ]
    assert [r["url"] for r in filter_allowed(results, ("lex.uz",))] == [
        "https://lex.uz/docs/1", "https://sub.lex.uz/x"]
    assert filter_allowed(results, ()) == results


def test_factory_serper_requires_key(monkeypatch):
    monkeypatch.setenv("WEBSEARCH_BACKEND", "serper")
    monkeypatch.delenv("SERPER_API_KEY", raising=False)
    with pytest.raises(ValueError, match="SERPER_API_KEY"):
        get_web_searcher()


def test_factory_serper_reads_env(monkeypatch):
    monkeypatch.setenv("WEBSEARCH_BACKEND", "serper")
    monkeypatch.setenv("SERPER_API_KEY", "k")
    monkeypatch.setenv("WEBSEARCH_ALLOWED_DOMAINS", "lex.uz, gov.uz")
    monkeypatch.setenv("WEBSEARCH_HL", "uz")
    s = get_web_searcher()
    assert isinstance(s, SerperWebSearcher)
    assert s.allowed_domains == ("lex.uz", "gov.uz") and s.hl == "uz"
