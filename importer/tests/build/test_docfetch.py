"""docfetch: HTML/PDF -> текст, sha256, кэш (память/Supabase), вежливость по
хостам, ошибки, SSRF-защита (схема + резолв адресов, в т.ч. на каждом hop'е
редиректа).

`resolver=_public` во всех фетчерах — тестовый дублёр `socket.getaddrinfo`:
без него проверка публичности адреса ходила бы в реальный DNS."""
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


def _public(host: str) -> list[str]:
    """Резолвер-дублёр: любой хост — публичный адрес (реального DNS в тестах нет)."""
    return ["93.184.216.34"]


def test_extract_text_html_drops_nav_script_style():
    text = extract_text_html(HTML)
    assert "Постановление" in text and "Пункт 1." in text
    assert "alert" not in text and "меню" not in text and "x{}" not in text


def test_extract_text_pdf_blank_page_is_empty_string():
    assert extract_text_pdf(_pdf_bytes()) == ""


def test_fetch_html_and_cache_hit():
    routes = {"https://lex.uz/docs/1": httpx.Response(200, text=HTML, headers={"content-type": "text/html; charset=utf-8"})}
    sleeps = []
    f = DocumentFetcher(cache=InMemoryDocCache(), client=_client(routes), sleep=sleeps.append,
                        clock=lambda: 0.0, resolver=_public)
    d1 = f.fetch("https://lex.uz/docs/1")
    assert d1.content_type == "text/html" and "Постановление" in d1.text and len(d1.sha256) == 64
    assert d1.from_cache is False
    d2 = f.fetch("https://lex.uz/docs/1")
    assert d2.from_cache is True and d2.sha256 == d1.sha256


def test_fetch_pdf_by_content_type():
    routes = {"https://gov.uz/a.pdf": httpx.Response(200, content=_pdf_bytes(), headers={"content-type": "application/pdf"})}
    d = DocumentFetcher(client=_client(routes), sleep=lambda s: None,
                        resolver=_public).fetch("https://gov.uz/a.pdf")
    assert d.content_type == "application/pdf" and d.text == ""


def test_politeness_delay_per_host():
    routes = {u: httpx.Response(200, text=HTML, headers={"content-type": "text/html"})
              for u in ("https://lex.uz/1", "https://lex.uz/2", "https://gov.uz/1")}
    sleeps, now = [], [100.0]
    f = DocumentFetcher(client=_client(routes), host_delays={"lex.uz": 20.0}, default_delay=1.0,
                        sleep=sleeps.append, clock=lambda: now[0], resolver=_public)
    f.fetch("https://lex.uz/1")          # первый запрос к хосту — без ожидания
    f.fetch("https://lex.uz/2")          # тот же хост сразу -> ждать 20
    f.fetch("https://gov.uz/1")          # другой хост — без ожидания
    assert sleeps == [20.0]


def test_http_error_and_too_large_raise():
    routes = {"https://x/404": httpx.Response(404), "https://x/big": httpx.Response(200, content=b"a" * 11, headers={"content-type": "text/plain"})}
    f = DocumentFetcher(client=_client(routes), max_bytes=10, sleep=lambda s: None, resolver=_public)
    with pytest.raises(DocFetchError, match="404"):
        f.fetch("https://x/404")
    with pytest.raises(DocFetchError, match="max_bytes"):
        f.fetch("https://x/big")


# ── разбор тела: сбой парсера — это DocFetchError, а не исключение pypdf ──

def test_broken_pdf_is_docfetch_error():
    """Битый PDF обязан прийти как `DocFetchError`: `ResearchToolkit.gather`
    ловит только её, иначе `build map --research` падает целиком (и падает
    повторно — битый документ в кэш не кладётся)."""
    routes = {"https://gov.uz/broken.pdf": httpx.Response(
        200, content=b"%PDF-broken", headers={"content-type": "application/pdf"})}
    f = DocumentFetcher(client=_client(routes), sleep=lambda s: None, resolver=_public)
    with pytest.raises(DocFetchError, match="не разобран"):
        f.fetch("https://gov.uz/broken.pdf")


def test_binary_content_type_gives_empty_text():
    """Не-HTML/не-PDF тело в `text` не пишем: бинарь в `pipeline.documents`
    бесполезен для промпта и только раздувает строку."""
    routes = {"https://gov.uz/a.zip": httpx.Response(
        200, content=b"PK\x03\x04\x00\x01", headers={"content-type": "application/zip"})}
    d = DocumentFetcher(client=_client(routes), sleep=lambda s: None,
                        resolver=_public).fetch("https://gov.uz/a.zip")
    assert d.text == "" and d.content_type == "application/zip" and len(d.sha256) == 64


# ── SSRF: схема, приватные адреса, перепроверка каждого hop'а редиректа ──

def test_non_http_scheme_rejected():
    f = DocumentFetcher(client=_client({}), sleep=lambda s: None, resolver=_public)
    with pytest.raises(DocFetchError, match="схема"):
        f.fetch("ftp://lex.uz/docs/1")


def test_private_address_rejected():
    f = DocumentFetcher(client=_client({}), sleep=lambda s: None, resolver=lambda h: ["127.0.0.1"])
    with pytest.raises(DocFetchError, match="непубличный"):
        f.fetch("https://localhost.example/secret")


def test_redirect_hop_to_private_address_rejected():
    """Редиректы обходятся вручную: публичный вход не должен быть мостом во
    внутреннюю сеть."""
    routes = {"https://ok.example/r": httpx.Response(
        302, headers={"location": "https://internal.example/secret"})}

    def resolver(host: str) -> list[str]:
        return ["10.0.0.1"] if host == "internal.example" else ["93.184.216.34"]

    f = DocumentFetcher(client=_client(routes), sleep=lambda s: None, resolver=resolver)
    with pytest.raises(DocFetchError, match="непубличный"):
        f.fetch("https://ok.example/r")


def test_redirect_to_public_host_is_followed_and_final_url_is_target():
    routes = {
        "https://ok.example/r": httpx.Response(302, headers={"location": "https://lex.uz/docs/1"}),
        "https://lex.uz/docs/1": httpx.Response(
            200, text=HTML, headers={"content-type": "text/html; charset=utf-8"}),
    }
    f = DocumentFetcher(client=_client(routes), sleep=lambda s: None, resolver=_public)
    d = f.fetch("https://ok.example/r")
    assert d.final_url == "https://lex.uz/docs/1"
    assert d.url == "https://ok.example/r" and "Постановление" in d.text


def test_redirect_loop_stops_at_limit():
    routes = {"https://ok.example/r": httpx.Response(302, headers={"location": "https://ok.example/r"})}
    f = DocumentFetcher(client=_client(routes), sleep=lambda s: None, resolver=_public)
    with pytest.raises(DocFetchError, match="редирект"):
        f.fetch("https://ok.example/r")


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
