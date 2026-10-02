"""Живой веб-поиск шага 'samples': server-side инструмент web_search Claude API.

Мусорный ответ модели (не JSON-массив) — пустой результат, не исключение
(контракт WebSearcher: пусто = «не нашёл»). pause_turn у server-side
инструмента резюмируется до MAX_RESUMES раз."""
from types import SimpleNamespace

import pytest

from importer.build.websearch import WebSearchError, _LiveWebSearcher, get_web_searcher


def _resp(text, stop_reason="end_turn"):
    return SimpleNamespace(
        content=[SimpleNamespace(type="text", text=text)], stop_reason=stop_reason)


class _FakeClient:
    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []
        self.messages = SimpleNamespace(create=self._create)

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        return self._responses.pop(0)


def test_parses_json_array_of_results():
    fake = _FakeClient([_resp('[{"title": "Шаблон", "url": "https://lex.uz/x", "snippet": "..." }]')])
    results = _LiveWebSearcher(client=fake).search("шаблон декларации")
    assert results == [{"title": "Шаблон", "url": "https://lex.uz/x", "snippet": "..."}]
    assert any(t.get("type") == "web_search_20260209" for t in fake.calls[0]["tools"])


def test_garbage_answer_means_empty_not_crash():
    fake = _FakeClient([_resp("ничего не нашлось, вот прости")])
    assert _LiveWebSearcher(client=fake).search("абракадабра") == []


def test_pause_turn_resumed_once():
    fake = _FakeClient([_resp("", stop_reason="pause_turn"), _resp('[]')])
    assert _LiveWebSearcher(client=fake).search("query") == []
    assert len(fake.calls) == 2


class _BoomClient:
    """Клиент, падающий на вызове API (сетевой сбой / статус-ошибка SDK)."""

    def __init__(self, exc: Exception) -> None:
        self.messages = SimpleNamespace(create=self._create)
        self._exc = exc

    def _create(self, **kwargs):
        raise self._exc


def test_client_failure_becomes_web_search_error():
    """Ошибка клиента Anthropic обязана прийти как `WebSearchError`: только
    её (точнее, её родителя `AgentLLMError`) ловит `ResearchToolkit.gather`,
    иначе один неудачный запрос роняет всю разведку."""
    searcher = _LiveWebSearcher(client=_BoomClient(RuntimeError("соединение оборвалось")))
    with pytest.raises(WebSearchError, match="соединение оборвалось"):
        searcher.search("шаблон декларации")


def test_allowlist_filters_live_results():
    """Allowlist доменов обязан работать и на дефолтном бэкенде: без него
    `docfetch` скачает любой URL, названный моделью."""
    fake = _FakeClient([_resp(
        '[{"title": "норма", "url": "https://lex.uz/1", "snippet": ""},'
        ' {"title": "мусор", "url": "https://spam.example/2", "snippet": ""}]')])
    results = _LiveWebSearcher(client=fake, allowed_domains=("lex.uz",)).search("запрос")
    assert [r["url"] for r in results] == ["https://lex.uz/1"]


def test_factory_passes_allowlist_to_live_backend(monkeypatch):
    monkeypatch.setenv("WEBSEARCH_BACKEND", "live")
    monkeypatch.setenv("WEBSEARCH_ALLOWED_DOMAINS", "lex.uz, gov.uz")
    searcher = get_web_searcher()
    assert isinstance(searcher, _LiveWebSearcher)
    assert searcher.allowed_domains == ("lex.uz", "gov.uz")
