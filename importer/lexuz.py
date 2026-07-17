"""Доступ к lex.uz: fetch с дисковым кэшем (не долбим сайт), эвристики страницы."""
import re
import time
from pathlib import Path
from typing import Callable

import httpx
from bs4 import BeautifulSoup


class LexuzUnreachable(Exception):
    pass


# Заголовки языковых ссылок шапки lex.uz → наш код языка.
# Язык версии определяется ТОЛЬКО по title: знак doc_id семантики не несёт
# (см. research-loop/DECISIONS.md, запись 2026-07-16).
_LANG_TITLES = {
    "Ўзбекча": "uz_cyr",
    "O'zbekcha": "uz_lat", "O’zbekcha": "uz_lat", "O‘zbekcha": "uz_lat",
    "Oʻzbekcha": "uz_lat",  # U+02BB — официальная узбекская окина
    "Русча": "ru", "Русский": "ru",
    "English": "en", "Инглизча": "en",
}


def _http_fetch(url: str) -> str:
    last = None
    for delay in (2, 4, 8):
        try:
            resp = httpx.get(url, follow_redirects=True, timeout=30,
                             headers={"User-Agent": "Mozilla/5.0 (importer inspector-x)"})
            if resp.status_code == 404:
                raise LexuzUnreachable(f"404: {url}")
            resp.raise_for_status()
            return resp.text
        except LexuzUnreachable:
            raise
        except httpx.HTTPError as e:
            last = e
            time.sleep(delay)
    raise LexuzUnreachable(f"lex.uz недоступен: {url}: {last}")


class LexuzClient:
    def __init__(self, cache_dir: Path, fetcher: Callable[[str], str] | None = None):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._fetcher = fetcher or _http_fetch

    def fetch(self, doc_id: str) -> str:
        cached = self.cache_dir / f"{doc_id}.html"
        if cached.exists():
            return cached.read_text(encoding="utf-8")
        html = self._fetcher(f"https://lex.uz/ru/docs/{doc_id}")  # doc_id уже со знаком
        cached.write_text(html, encoding="utf-8")
        return html

    @staticmethod
    def page_text(html: str) -> str:
        text = BeautifulSoup(html, "html.parser").get_text(" ")
        return re.sub(r"\s+", " ", text).strip()

    @staticmethod
    def is_repealed(html: str) -> bool:
        head = LexuzClient.page_text(html)[:5000].lower()
        return any(m in head for m in
                   ("утратил силу", "утратила силу", "kuchini yo'qotgan", "кучини йўқотган"))

    @staticmethod
    def is_russian(html: str) -> bool:
        text = f" {LexuzClient.page_text(html).lower()} "
        hits = sum(text.count(w) for w in (" и ", " или ", " в ", " на "))
        return hits >= 20

    @staticmethod
    def language_versions(html: str) -> dict[str, str]:
        """Ссылки шапки акта на языковые версии: у каждой версии свой doc_id."""
        versions: dict[str, str] = {}
        pat = r"openUrl\('/[a-z]{2}/docs/(-?\d+)'\)\"\s*title=\"([^\"]+)\""
        for m in re.finditer(pat, html):
            lang = _LANG_TITLES.get(m.group(2))
            if lang and lang not in versions:
                versions[lang] = m.group(1)
        return versions

    @staticmethod
    def quote_script(text: str) -> str:
        """Графика узбекской цитаты: 'cyr' | 'lat' — для выбора версии акта."""
        low = text.lower()
        cyr = len(re.findall(r"[а-яёўқғҳ]", low))
        lat = len(re.findall(r"[a-z]", low))
        return "lat" if lat > cyr else "cyr"

    @staticmethod
    def find_paragraph(html: str, ref: str) -> str | None:
        text = LexuzClient.page_text(html)
        m_art = re.match(r"art\.([\d-]+)(?:/p\.([\d-]+))?$", ref)
        if m_art:
            num = m_art.group(1)
            # Кодексы на lex.uz начинаются с оглавления, где заголовки статей идут
            # подряд (тело ~0 знаков). Берём вхождение с самым длинным телом — это
            # настоящая статья, а не строка содержания.
            best = None
            for pat in (rf"Статья\s+{num}\.", rf"{num}-модда\.", rf"{num}-modda\."):
                for mt in re.finditer(pat, text):
                    rest = text[mt.start():]
                    nxt = re.search(r"Статья\s+[\d-]+\.|[\d-]+-модда\.|[\d-]+-modda\.",
                                    rest[10:])
                    body = rest[: nxt.start() + 10] if nxt else rest
                    if best is None or len(body) > len(best):
                        best = body
            return best
        m_p = re.match(r"p\.([\d-]+)$", ref)
        if m_p:
            num = m_p.group(1)
            # «документа» — хвост UI-виджета lex.uz «Получить ссылку из элемента
            # документа», который предваряет каждый нумерованный пункт на ПКМ-страницах.
            start = re.search(rf"(?:^|[.;)]|документа)\s{num}\.\s", text)
            if not start:
                return None
            rest = text[start.end() - len(f"{num}. "):]
            nxt = re.search(r"(?:[.;]|документа)\s[\d-]+\.\s", rest[5:])
            return rest[: nxt.start() + 5] if nxt else rest[:2000]
        return None  # appN/rowM и прочее — сверка по всей странице (v1)
