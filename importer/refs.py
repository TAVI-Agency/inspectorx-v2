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
    m = re.search(r"/(?:docs|acts)/-?(\d+)", parsed.path)
    return m.group(1) if m else None


_NUM = r"(\d+(?:-\d+)?)"
_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(rf"^п(?:\.|ункт)?\s*{_NUM}\s+ст(?:\.|атья|атьи)?\s*{_NUM}$", re.I), r"art.\2/p.\1"),
    (re.compile(rf"^ст(?:\.|атья|атьи)?\s*{_NUM}$", re.I), r"art.\1"),
    (re.compile(rf"^п(?:\.|ункт)?\s*{_NUM}$", re.I), r"p.\1"),
    (re.compile(rf"^прил(?:\.|ожение)?\s*{_NUM}\s*,?\s*строк[аи]\s*{_NUM}$", re.I), r"app\1/row\2"),
    (re.compile(rf"^прил(?:\.|ожение)?\s*{_NUM}$", re.I), r"app\1"),
    (re.compile(rf"^раздел\s*{_NUM}$", re.I), r"sec.\1"),
]


def parse_unit_ref(unit: str | None) -> str | None:
    if not unit:
        return None
    text = re.sub(r"\s+", " ", unit.strip().strip("«»\"'"))
    for pattern, repl in _PATTERNS:
        m = pattern.match(text)
        if m:
            return pattern.sub(repl, text)
    return None
