"""ResearchToolkit (Задача 4, «ночь 11.09.2026»): «глаза и руки»
Cartographer'а в режиме `--research` — склеивает `WebSearcher.search`
(Задача 2) и `DocumentFetcher.fetch` (Задача 3) в один шаг «план запросов ->
реальные источники» (сам план запросов и промпт с ними — забота
`Cartographer`, этот модуль ничего не знает про LLM).

Deep research — best effort: сбой одного запроса поиска (`WebSearchError`)
или скачивания одной страницы (`DocFetchError`) не должен ронять всю
разведку по группе — он просто пропускается и копится в `skipped`, которое
идёт в отчёт владельцу (CLI печатает его при `build map --research`)."""
from __future__ import annotations

from dataclasses import dataclass

from importer.build.docfetch import DocFetchError, DocumentFetcher
from importer.build.websearch import SearchResult, WebSearcher, WebSearchError


@dataclass(frozen=True)
class ResearchSource:
    """Один собранный источник: находка поиска + текст, реально скачанный
    и усечённый до `excerpt_chars` (полный текст незачем гнать в промпт)."""

    url: str
    title: str
    excerpt: str
    sha256: str


class ResearchToolkit:
    """Поиск -> скачивание -> выдержки, с дедупом по URL и лимитами на
    число запросов/документов (разведка по группе — разовая и небесплатная,
    лимиты защищают от неограниченного разрастания плана запросов LLM)."""

    def __init__(
        self,
        searcher: WebSearcher,
        fetcher: DocumentFetcher,
        *,
        max_queries: int = 6,
        max_docs: int = 8,
        excerpt_chars: int = 3000,
    ) -> None:
        self._searcher = searcher
        self._fetcher = fetcher
        self.max_queries = max_queries
        self._max_docs = max_docs
        self._excerpt_chars = excerpt_chars
        self.skipped: list[tuple[str, str]] = []

    def gather(self, queries: list[str]) -> list[ResearchSource]:
        """Прогоняет запросы (до `max_queries`) через поиск, дедуплицирует
        находки по URL, скачивает до `max_docs` штук. `skipped` каждый раз
        начинается заново — это отчёт по ПОСЛЕДНЕЙ разведке, не накопитель."""
        self.skipped = []
        seen: dict[str, SearchResult] = {}
        for q in queries[: self.max_queries]:
            try:
                for r in self._searcher.search(q):
                    seen.setdefault(r["url"], r)
            except WebSearchError as exc:
                self.skipped.append((q, str(exc)))

        sources: list[ResearchSource] = []
        for url, r in seen.items():
            if len(sources) >= self._max_docs:
                break
            try:
                doc = self._fetcher.fetch(url)
            except DocFetchError as exc:
                self.skipped.append((url, str(exc)))
                continue
            sources.append(ResearchSource(
                url=url, title=r["title"],
                excerpt=doc.text[: self._excerpt_chars], sha256=doc.sha256,
            ))
        return sources
