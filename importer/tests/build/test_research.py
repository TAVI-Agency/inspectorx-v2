"""ResearchToolkit (Задача 4, «ночь 11.09.2026»): «глаза и руки» Cartographer
в режиме `--research` — склеивает `WebSearcher.search` и `DocumentFetcher.fetch`
в план запросов -> дедуп по URL -> короткие выдержки.

Сценарии:
- дедуп по URL между разными запросами, пропуск ошибок поиска/скачивания
  (best effort — они идут в `skipped`, не роняют разведку), усечение
  выдержки до `excerpt_chars`;
- лимиты `max_queries`/`max_docs` реально режут план запросов и число
  скачанных документов.

`_Searcher`/`_Fetcher` — фейки по образцу примеров из брифа задачи."""
from __future__ import annotations

from datetime import datetime, timezone

from importer.build.docfetch import DocFetchError, FetchedDoc
from importer.build.research import ResearchSource, ResearchToolkit
from importer.build.websearch import WebSearchError


class _Searcher:
    def __init__(self, table):
        self.table = table
        self.queries = []

    def search(self, q):
        self.queries.append(q)
        if isinstance(self.table.get(q), Exception):
            raise self.table[q]
        return self.table.get(q, [])


class _Fetcher:
    def __init__(self, docs):
        self.docs = docs
        self.urls = []

    def fetch(self, url):
        self.urls.append(url)
        if isinstance(self.docs.get(url), Exception):
            raise self.docs[url]
        return self.docs[url]


def _doc(url, text):
    return FetchedDoc(url=url, final_url=url, content_type="text/html", sha256="0" * 64,
                       text=text, fetched_at=datetime(2026, 9, 11, tzinfo=timezone.utc))


def test_gather_dedupes_urls_skips_failures_and_truncates():
    searcher = _Searcher({
        "q1": [{"title": "A", "url": "https://lex.uz/1", "snippet": ""},
               {"title": "B", "url": "https://gov.uz/2", "snippet": ""}],
        "q2": [{"title": "A2", "url": "https://lex.uz/1", "snippet": ""}],
        "q3": WebSearchError("serper API 500"),
    })
    fetcher = _Fetcher({"https://lex.uz/1": _doc("https://lex.uz/1", "x" * 5000),
                        "https://gov.uz/2": DocFetchError("HTTP 404")})
    kit = ResearchToolkit(searcher, fetcher, excerpt_chars=100)
    sources = kit.gather(["q1", "q2", "q3"])
    assert [s.url for s in sources] == ["https://lex.uz/1"]
    assert isinstance(sources[0], ResearchSource)
    assert len(sources[0].excerpt) == 100 and sources[0].title == "A"
    assert sources[0].sha256 == "0" * 64
    assert fetcher.urls == ["https://lex.uz/1", "https://gov.uz/2"]
    assert ("https://gov.uz/2", "HTTP 404") in kit.skipped
    assert ("q3", "serper API 500") in kit.skipped


def test_gather_respects_max_queries_and_max_docs():
    searcher = _Searcher({f"q{i}": [{"title": "", "url": f"https://lex.uz/{i}", "snippet": ""}] for i in range(10)})
    fetcher = _Fetcher({f"https://lex.uz/{i}": _doc(f"https://lex.uz/{i}", "t") for i in range(10)})
    kit = ResearchToolkit(searcher, fetcher, max_queries=3, max_docs=2)
    assert len(kit.gather([f"q{i}" for i in range(10)])) == 2
    assert searcher.queries == ["q0", "q1", "q2"]
    assert kit.max_queries == 3


def test_gather_resets_skipped_between_calls():
    """Второй `gather` не должен тащить `skipped` из первого прогона —
    отчёт владельцу должен отражать только последнюю разведку."""
    searcher = _Searcher({"q1": WebSearchError("боль"), "q2": []})
    fetcher = _Fetcher({})
    kit = ResearchToolkit(searcher, fetcher)
    kit.gather(["q1"])
    assert kit.skipped == [("q1", "боль")]

    kit.gather(["q2"])
    assert kit.skipped == []
