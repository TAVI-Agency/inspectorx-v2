"""Канонизация адресов: unit из отчёта → ref в стиле JurisBase (art.N/p.M, appN/rowM)."""
import re
from urllib.parse import urlparse

_LEX_HOSTS = {"lex.uz", "www.lex.uz"}


def lexuz_doc_id(url: str | None) -> str | None:
    if not url:
        return None
    try:
        parsed = urlparse(url)
    except ValueError:
        return None
    if parsed.hostname not in _LEX_HOSTS:
        return None
    # Знак — часть идентификатора: на lex.uz /docs/-N и /docs/N — РАЗНЫЕ документы.
    m = re.search(r"/(?:docs|acts)/(-?\d+)", parsed.path)
    return m.group(1) if m else None


_NUM = r"(\d+(?:-\d+)?)"
_APP = r"прил(?:\.|ожение)?\s*№?\s*"
_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(rf"^п(?:\.|ункт)?\s*{_NUM}\s+ст(?:\.|атья|атьи)?\s*{_NUM}$", re.I), r"art.\2/p.\1"),
    (re.compile(rf"^ст(?:\.|атья|атьи)?\s*{_NUM}$", re.I), r"art.\1"),
    (re.compile(rf"^п(?:\.|ункт)?\s*{_NUM}$", re.I), r"p.\1"),
    (re.compile(rf"^{_APP}{_NUM}\s*,?\s*строк[аи]\s*{_NUM}$", re.I), r"app\1/row\2"),
    (re.compile(rf"^{_APP}{_NUM}\s*,\s*п(?:\.|ункт)?\s*{_NUM}$", re.I), r"app\1/p.\2"),
    (re.compile(rf"^{_APP}(\d+)\s*[–—-]\s*(\d+)$", re.I), r"app\1-\2"),
    (re.compile(rf"^{_APP}{_NUM}$", re.I), r"app\1"),
    (re.compile(rf"^раздел\s*{_NUM}$", re.I), r"sec.\1"),
]


def _match_full(text: str) -> str | None:
    for pattern, repl in _PATTERNS:
        if pattern.match(text):
            return pattern.sub(repl, text)
    return None


def parse_unit_ref(unit: str | None) -> str | None:
    if not unit:
        return None
    text = re.sub(r"\s+", " ", unit.strip().strip("«»\"'"))
    ref = _match_full(text)
    if ref:
        return ref
    # пояснения в скобках мешают точным паттернам: «прил. № 1, п. 5 (гл. 3)»
    stripped = re.sub(r"\s*\([^)]*\)", "", text)
    stripped = re.sub(r"\s+", " ", stripped).strip().strip(";,")
    if stripped and stripped != text:
        ref = _match_full(stripped)
        if ref:
            return ref
    # составной unit («ст. 4; гл. 3», «ст. 254, ст. 258») — первый распознанный
    # сегмент; правильность привязки дальше решает гейт сверкой цитаты
    for seg in re.split(r"[;,]", stripped or text):
        ref = _match_full(seg.strip())
        if ref:
            return ref
    return None
