"""docfetch: HTML/PDF -> текст, sha256, кэш (память/Supabase), вежливость по хостам, ошибки."""
import io
from datetime import datetime, timezone

import httpx
import pytest
from pypdf import PdfWriter

from importer.build.docfetch import (
    DocFetchError, DocumentFetcher, FetchedDoc, InMemoryDocCache, SupabaseDocCache,
    extract_text_html, extract_text_pdf,
)

HTML = "<html><head><title>t</title><style>x{}</style></head><body><nav>меню</nav><h1>Постановление</h1><p>Пункт 1.</p><script>alert(1)</script></body></html>"


def _pdf_bytes() -> bytes:
    w = PdfWriter(); w.add_blank_page(width=200, height=200)
    buf = io.BytesIO(); w.write(buf); return buf.getvalue()


def _client(routes: dict[str, httpx.Response]):
    def handler(request):
        return routes.get(str(request.url), httpx.Response(404))
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_extract_text_html_drops_nav_script_style():
    text = extract_text_html(HTML)
    assert "Постановление" in text and "Пункт 1." in text
    assert "alert" not in text and "меню" not in text and "x{}" not in text


def test_extract_text_pdf_blank_page_is_empty_string():
    assert extract_text_pdf(_pdf_bytes()) == ""


def test_fetch_html_and_cache_hit():
    routes = {"https://lex.uz/docs/1": httpx.Response(200, text=HTML, headers={"content-type": "text/html; charset=utf-8"})}
    sleeps = []
    f = DocumentFetcher(cache=InMemoryDocCache(), client=_client(routes), sleep=sleeps.append, clock=lambda: 0.0)
    d1 = f.fetch("https://lex.uz/docs/1")
    assert d1.content_type == "text/html" and "Постановление" in d1.text and len(d1.sha256) == 64
    assert d1.from_cache is False
    d2 = f.fetch("https://lex.uz/docs/1")
    assert d2.from_cache is True and d2.sha256 == d1.sha256


def test_fetch_pdf_by_content_type():
    routes = {"https://gov.uz/a.pdf": httpx.Response(200, content=_pdf_bytes(), headers={"content-type": "application/pdf"})}
    d = DocumentFetcher(client=_client(routes), sleep=lambda s: None).fetch("https://gov.uz/a.pdf")
    assert d.content_type == "application/pdf" and d.text == ""


def test_politeness_delay_per_host():
    routes = {u: httpx.Response(200, text=HTML, headers={"content-type": "text/html"})
              for u in ("https://lex.uz/1", "https://lex.uz/2", "https://gov.uz/1")}
    sleeps, now = [], [100.0]
    f = DocumentFetcher(client=_client(routes), host_delays={"lex.uz": 20.0}, default_delay=1.0,
                        sleep=sleeps.append, clock=lambda: now[0])
    f.fetch("https://lex.uz/1")          # первый запрос к хосту — без ожидания
    f.fetch("https://lex.uz/2")          # тот же хост сразу -> ждать 20
    f.fetch("https://gov.uz/1")          # другой хост — без ожидания
    assert sleeps == [20.0]


def test_http_error_and_too_large_raise():
    routes = {"https://x/404": httpx.Response(404), "https://x/big": httpx.Response(200, content=b"a" * 11, headers={"content-type": "text/plain"})}
    f = DocumentFetcher(client=_client(routes), max_bytes=10, sleep=lambda s: None)
    with pytest.raises(DocFetchError, match="404"):
        f.fetch("https://x/404")
    with pytest.raises(DocFetchError, match="max_bytes"):
        f.fetch("https://x/big")


class _FakeTable:
    def __init__(self, rows): self.rows = rows; self.last = None
    def select(self, *_): self._mode = "select"; return self
    def eq(self, col, val): self._eq = (col, val); return self
    def limit(self, n): return self
    def execute(self):
        from types import SimpleNamespace
        if self._mode == "upsert":
            return SimpleNamespace(data=[self.last])
        col, val = self._eq
        return SimpleNamespace(data=[r for r in self.rows if r[col] == val])
    def upsert(self, row): self._mode = "upsert"; self.last = row; self.rows.append(row); return self


class _FakeClient:
    def __init__(self, rows): self.table_ = _FakeTable(rows); self.schema_name = None
    def schema(self, name): self.schema_name = name; return self
    def table(self, name): assert name == "documents"; return self.table_


def test_supabase_cache_roundtrip():
    client = _FakeClient([])
    cache = SupabaseDocCache(client)
    assert cache.get("https://lex.uz/1") is None
    doc = FetchedDoc(url="https://lex.uz/1", final_url="https://lex.uz/1", content_type="text/html",
                     sha256="ab" * 32, text="тело", fetched_at=datetime(2026, 9, 11, tzinfo=timezone.utc))
    cache.put(doc)
    assert client.schema_name == "pipeline"
    got = cache.get("https://lex.uz/1")
    assert got is not None and got.text == "тело" and got.sha256 == "ab" * 32
