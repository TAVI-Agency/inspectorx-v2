"""Скачивание и кэш документов для research-режима Cartographer (ADR-0003:
«Cartographer — разовый deep research»; ADR-0002: агентный ресёрч — Railway).

Кэш — `pipeline.documents` (миграция 20260911100000): один и тот же URL
второй раз не качается (вежливость к lex.uz/gov.uz и воспроизводимость:
карта строится по зафиксированному снимку источника, sha256 — в отчёте).
Вежливость: пауза между запросами к одному хосту (`host_delays`, lex.uz —
20 с по его robots.txt `Crawl-delay: 20`; остальные — `default_delay`).
Текст: HTML — BeautifulSoup без script/style/nav/header/footer; PDF — pypdf
(текстовый слой; сканы дают пустую строку — это честный «нет текста», не
ошибка); прочее (бинарь, архивы) — пустая строка: в `pipeline.documents`
такому телу делать нечего, а в промпт оно всё равно не пойдёт.

Любой сбой разбора тела — `DocFetchError`, а не исключение pypdf/кодека:
`ResearchToolkit.gather` ловит только её, и битый PDF не должен ронять
`build map --research` целиком.

SSRF: URL скачивается, только если схема — http/https И все адреса хоста
публичные (`_assert_public_url`). Редиректы обходятся ВРУЧНУЮ
(`follow_redirects=False`, до `MAX_REDIRECTS` hop'ов) — иначе публичный
вход стал бы мостом во внутреннюю сеть через `Location:`. Тело читается
стримом с обрывом на `max_bytes`, а не буферизуется целиком."""
from __future__ import annotations

import hashlib
import io
import ipaddress
import socket
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from time import monotonic, sleep as time_sleep
from typing import Callable, Protocol
from urllib.parse import urljoin, urlsplit

import httpx
from bs4 import BeautifulSoup
from pypdf import PdfReader

USER_AGENT = "InspectorX-Research/1.0 (+https://inspectorx.uz)"

# lex.uz robots.txt: Crawl-delay: 20 — остальные хосты идут через default_delay.
DEFAULT_HOST_DELAYS: dict[str, float] = {"lex.uz": 20.0}

ALLOWED_SCHEMES = ("http", "https")
MAX_REDIRECTS = 5
_REDIRECT_CODES = (301, 302, 303, 307, 308)

# Резолвер хоста в список IP: инжектируется в `DocumentFetcher` — тестам
# нельзя ходить в реальный DNS.
Resolver = Callable[[str], list[str]]


@dataclass(frozen=True)
class FetchedDoc:
    """Результат скачивания: URL после редиректов, тип контента, извлечённый
    текст и sha256 сырого тела (снимок источника для отчёта картирования)."""

    url: str
    final_url: str
    content_type: str
    sha256: str
    text: str
    fetched_at: datetime
    from_cache: bool = False


class DocCache(Protocol):
    """Контракт кэша документов: по URL — либо ничего, либо готовый FetchedDoc."""

    def get(self, url: str) -> FetchedDoc | None:
        ...

    def put(self, doc: FetchedDoc) -> None:
        ...


class DocFetchError(Exception):
    """HTTP-ошибка, превышение max_bytes, сетевой сбой, запрещённый адрес
    (SSRF-проверка) или сбой разбора тела при скачивании."""


def default_resolver(host: str) -> list[str]:
    """Все адреса хоста через `socket.getaddrinfo` (и A, и AAAA)."""
    return [info[4][0] for info in socket.getaddrinfo(host, None)]


def _assert_public_url(url: str, resolver: Resolver) -> None:
    """Пускаем дальше только http/https на ПУБЛИЧНЫЙ адрес.

    URL приходит из выдачи веб-поиска, то есть в конечном счёте от LLM —
    без этой проверки `build map --research` скачивал бы `file://`,
    `http://169.254.169.254/` (метаданные облака) или внутренние сервисы
    Railway по одному лишь названию модели."""
    parts = urlsplit(url)
    if parts.scheme not in ALLOWED_SCHEMES:
        raise DocFetchError(f"{url}: схема {parts.scheme!r} не поддерживается (только http/https)")
    host = parts.hostname
    if not host:
        raise DocFetchError(f"{url}: в URL нет хоста")
    try:
        addresses = resolver(host)
    except OSError as exc:
        raise DocFetchError(f"{url}: хост не резолвится: {exc}") from exc
    if not addresses:
        raise DocFetchError(f"{url}: хост не резолвится")
    for address in addresses:
        try:
            ip = ipaddress.ip_address(address)
        except ValueError as exc:
            raise DocFetchError(f"{url}: неразбираемый адрес {address!r}") from exc
        if (ip.is_private or ip.is_loopback or ip.is_link_local
                or ip.is_reserved or ip.is_multicast or ip.is_unspecified):
            raise DocFetchError(f"{url}: непубличный адрес {address}")


class InMemoryDocCache:
    """Кэш в памяти процесса — для тестов и разовых прогонов без Supabase."""

    def __init__(self) -> None:
        self._docs: dict[str, FetchedDoc] = {}

    def get(self, url: str) -> FetchedDoc | None:
        return self._docs.get(url)

    def put(self, doc: FetchedDoc) -> None:
        self._docs[doc.url] = doc


class SupabaseDocCache:
    """Кэш в `pipeline.documents` — воспроизводимость между прогонами
    Cartographer (тот же URL второй раз не качается ни в этом процессе,
    ни в следующем)."""

    def __init__(self, client) -> None:
        self._client = client

    def _table(self):
        return self._client.schema("pipeline").table("documents")

    def get(self, url: str) -> FetchedDoc | None:
        rows = self._table().select("*").eq("url", url).limit(1).execute().data
        if not rows:
            return None
        row = rows[0]
        return FetchedDoc(
            url=row["url"],
            final_url=row["final_url"],
            content_type=row["content_type"],
            sha256=row["sha256"],
            text=row["text"],
            fetched_at=datetime.fromisoformat(row["fetched_at"]),
        )

    def put(self, doc: FetchedDoc) -> None:
        self._table().upsert({
            "url": doc.url,
            "final_url": doc.final_url,
            "content_type": doc.content_type,
            "sha256": doc.sha256,
            "text": doc.text,
            "fetched_at": doc.fetched_at.isoformat(),
        }).execute()


def extract_text_html(html: str) -> str:
    """Текст страницы без навигации/скриптов/стилей: только то, что реально
    читает человек (заголовок, содержательные блоки)."""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "nav", "header", "footer", "aside"]):
        tag.decompose()
    lines = [ln.strip() for ln in soup.get_text("\n").splitlines()]
    return "\n".join(ln for ln in lines if ln)


def extract_text_pdf(data: bytes) -> str:
    """Текстовый слой PDF. Скан без OCR-слоя даёт пустую строку — это
    честный «текста нет», а не ошибка извлечения."""
    reader = PdfReader(io.BytesIO(data))
    return "\n".join((page.extract_text() or "").strip() for page in reader.pages).strip()


class DocumentFetcher:
    """Скачивает URL с вежливостью по хостам и кэшированием.

    `sleep`/`clock`/`resolver` инжектируются (по умолчанию — реальные
    `time.sleep`/`time.monotonic`/`socket.getaddrinfo`), в тестах — списки и
    лямбды: без ожидания и без похода в DNS."""

    def __init__(
        self,
        *,
        cache: DocCache | None = None,
        client: httpx.Client | None = None,
        host_delays: dict[str, float] | None = None,
        default_delay: float = 1.0,
        max_bytes: int = 5_000_000,
        timeout: float = 30.0,
        sleep: Callable[[float], None] = time_sleep,
        clock: Callable[[], float] = monotonic,
        resolver: Resolver = default_resolver,
    ) -> None:
        self._cache = cache
        self._client = client or httpx.Client(timeout=timeout)
        self._host_delays = dict(host_delays) if host_delays is not None else dict(DEFAULT_HOST_DELAYS)
        self._default_delay = default_delay
        self._max_bytes = max_bytes
        self._sleep = sleep
        self._clock = clock
        self._resolver = resolver
        self._last_hit: dict[str, float] = {}

    def _wait_for_host(self, host: str) -> None:
        delay = self._host_delays.get(host, self._default_delay)
        last = self._last_hit.get(host)
        now = self._clock()
        if last is not None:
            elapsed = now - last
            if elapsed < delay:
                self._sleep(delay - elapsed)
        self._last_hit[host] = self._clock()

    def _download(self, url: str) -> tuple[str, str, str, bytes]:
        """Ручной обход редиректов: (final_url, content_type, charset, тело).

        Каждый hop заново проходит `_assert_public_url` — редирект с
        публичного хоста на `10.0.0.1` должен упираться в ту же проверку,
        что и исходный URL. Тело читается стримом и обрывается на
        `max_bytes`, не буферизуясь целиком."""
        target = url
        for _ in range(MAX_REDIRECTS + 1):
            _assert_public_url(target, self._resolver)
            self._wait_for_host(urlsplit(target).hostname or "")
            try:
                with self._client.stream(
                    "GET", target, follow_redirects=False,
                    headers={"User-Agent": USER_AGENT},
                ) as resp:
                    if resp.status_code in _REDIRECT_CODES and "location" in resp.headers:
                        target = urljoin(target, resp.headers["location"])
                        continue
                    if resp.status_code >= 400:
                        raise DocFetchError(f"{url}: HTTP {resp.status_code}")
                    content = bytearray()
                    for chunk in resp.iter_bytes():
                        content.extend(chunk)
                        if len(content) > self._max_bytes:
                            raise DocFetchError(f"{url}: превышен max_bytes={self._max_bytes}")
                    content_type = resp.headers.get("content-type", "").split(";")[0].strip().lower()
                    return str(resp.url), content_type, resp.charset_encoding or "utf-8", bytes(content)
            except httpx.HTTPError as exc:
                raise DocFetchError(f"{url}: сетевая ошибка: {exc}") from exc
        raise DocFetchError(f"{url}: слишком много редиректов (> {MAX_REDIRECTS})")

    def fetch(self, url: str) -> FetchedDoc:
        if self._cache is not None:
            cached = self._cache.get(url)
            if cached is not None:
                return replace(cached, from_cache=True)

        final_url, content_type, charset, content = self._download(url)

        is_pdf = content_type == "application/pdf" or final_url.lower().endswith(".pdf")
        try:
            if is_pdf:
                text = extract_text_pdf(content)
                content_type = content_type or "application/pdf"
            elif content_type in ("text/html", "application/xhtml+xml"):
                text = extract_text_html(content.decode(charset, errors="replace"))
            else:
                # Не HTML и не PDF — тело в `text` не кладём: бинарь в
                # `pipeline.documents` бесполезен и только раздувает строку.
                text = ""
        except Exception as exc:  # pypdf/BeautifulSoup/кодек — наружу только DocFetchError
            raise DocFetchError(f"{url}: не разобран {content_type or '?'}: {exc}") from exc

        doc = FetchedDoc(
            url=url,
            final_url=final_url,
            content_type=content_type,
            sha256=hashlib.sha256(content).hexdigest(),
            text=text,
            fetched_at=datetime.now(timezone.utc),
        )
        if self._cache is not None:
            self._cache.put(doc)
        return doc
