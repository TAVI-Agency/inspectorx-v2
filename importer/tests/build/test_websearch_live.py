"""Живой веб-поиск шага 'samples': server-side инструмент web_search Claude API.

Мусорный ответ модели (не JSON-массив) — пустой результат, не исключение
(контракт WebSearcher: пусто = «не нашёл»). pause_turn у server-side
инструмента резюмируется до MAX_RESUMES раз."""
from types import SimpleNamespace

from importer.build.websearch import _LiveWebSearcher


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
