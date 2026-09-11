"""Нормализация узбекского скрипта: латиница ↔ кириллица (Задача 5).

## Зачем

Узбекский — канонический язык данных конвейера (ADR по UZ-first дизайну), но
исходные тексты (акты LegalX, запросы Retriever'а, реквизиты golden-сета)
приходят вперемешку и латиницей, и кириллицей — иногда даже внутри одного
документа. Бенчмарк Uzbek Legal RAG показывает: смешение скриптов ломает
~5% ссылок на законы (поиск/сравнение по буквальной строке не находит
совпадение между "oʻzbekiston" и "ўзбекистон", хотя это одно и то же слово).
Этот модуль — чистые функции транслитерации и нормализации для сравнения,
без зависимостей от остального конвейера: три точки применения
(`legalx_mock.py`, `eval_golden.py`, `agents.py`) используют его, чтобы
поиск и сравнение реквизитов не зависели от того, каким скриптом записан
исходник.

## Алфавит

Узбекский латинский алфавит 1995 г. Диграфы `sh`/`ch`/`yo`/`yu`/`ya`/`ts` и
апострофные буквы `oʻ`(ў)/`gʻ`(ғ) обрабатываются как единицы транслитерации
до одиночных букв — иначе, например, "sh" превратилось бы в "с"+"х" вместо
"ш". Порядок замен латиница→кириллица важен ЕЩЁ и внутри самих диграфов:
`oʻ`/`gʻ` — первыми (после унификации апострофов), чтобы "Yoʻriqnoma" не
съело "Yo" как "ё" раньше, чем "oʻ" — как "ў" (получилось бы "Ёриқнома"
вместо верного "Йўриқнома", где "Y" — отдельная буква "й", а "oʻ" — "ў").
"""
from __future__ import annotations

import re
import unicodedata
from typing import Literal

# ── Унификация апострофов ────────────────────────────────────────────────
# Источники дают тутуқ белгиси (ʻ/ʼ) вперемешку с типографскими кавычками и
# диакритикой — все варианты сводим к простому ASCII-апострофу.
_APOSTROPHE_VARIANTS = "‘’ʻʼ`´"
_APOSTROPHE_TABLE = str.maketrans({ch: "'" for ch in _APOSTROPHE_VARIANTS})


def unify_apostrophes(text: str) -> str:
    """Сводит все варианты тутуқ белгиси/кавычек-апострофов к `'`."""
    return text.translate(_APOSTROPHE_TABLE)


# ── Таблицы транслитерации ───────────────────────────────────────────────
# Латиница -> кириллица: применяются ПОСЛЕДОВАТЕЛЬНО отдельными стадиями
# (не одним regex'ом на все ключи сразу) — порядок стадий разруливает
# конфликт "yo" (диграф "ё") против "y"+"oʻ" ("й"+"ў"), см. докстринг модуля.
_LAT_TO_CYR_APOSTROPHE_DIGRAPHS = {"o'": "ў", "g'": "ғ"}
_LAT_TO_CYR_DIGRAPHS = {
    "sh": "ш", "ch": "ч", "yo": "ё", "yu": "ю", "ya": "я", "ts": "ц",
}
_LAT_TO_CYR_SINGLES = {
    "a": "а", "b": "б", "d": "д", "e": "е", "f": "ф", "g": "г", "h": "ҳ",
    "i": "и", "j": "ж", "k": "к", "l": "л", "m": "м", "n": "н", "o": "о",
    "p": "п", "q": "қ", "r": "р", "s": "с", "t": "т", "u": "у", "v": "в",
    "x": "х", "y": "й", "z": "з",
}
_LAT_TO_CYR_TUTUQ = {"'": "ъ"}

# Кириллица -> латиница: все ключи — одиночные символы, порядок замен между
# ними не влияет на результат (совпадений по подстрокам быть не может), так
# что это один проход через объединённую таблицу.
_CYR_TO_LAT_TABLE = {
    "ў": "oʻ", "ғ": "gʻ", "ш": "sh", "ч": "ch", "ё": "yo", "ю": "yu",
    "я": "ya", "ц": "ts", "ҳ": "h", "х": "x", "қ": "q", "ж": "j", "й": "y",
    "ъ": "ʼ", "э": "e", "ь": "", "щ": "sh", "ы": "i",
    # Остальные буквы — прямая таблица (см. докстринг модуля).
    "а": "a", "б": "b", "д": "d", "е": "e", "ф": "f", "г": "g", "и": "i",
    "к": "k", "л": "l", "м": "m", "н": "n", "о": "o", "п": "p", "р": "r",
    "с": "s", "т": "t", "у": "u", "в": "v", "з": "z",
}


def _compile_pattern(table: dict[str, str]) -> re.Pattern[str] | None:
    """Компилирует regex по ключам `table` (длинные ключи первыми, чтобы
    диграф не терялся под своей первой буквой), без учёта регистра.
    Вызывается один раз на таблицу при загрузке модуля — не на каждый
    вызов `_translit`."""
    if not table:
        return None
    keys = sorted(table, key=len, reverse=True)
    return re.compile("|".join(re.escape(k) for k in keys), re.IGNORECASE)


# Пары (таблица, прекомпилированный паттерн) — по одной на стадию замены.
_LAT_TO_CYR_APOSTROPHE_DIGRAPHS_RE = _compile_pattern(_LAT_TO_CYR_APOSTROPHE_DIGRAPHS)
_LAT_TO_CYR_DIGRAPHS_RE = _compile_pattern(_LAT_TO_CYR_DIGRAPHS)
_LAT_TO_CYR_SINGLES_RE = _compile_pattern(_LAT_TO_CYR_SINGLES)
_LAT_TO_CYR_TUTUQ_RE = _compile_pattern(_LAT_TO_CYR_TUTUQ)
_CYR_TO_LAT_TABLE_RE = _compile_pattern(_CYR_TO_LAT_TABLE)


def _translit(text: str, table: dict[str, str], pattern: re.Pattern[str] | None) -> str:
    """Заменяет вхождения ключей `table` (найденные прекомпилированным
    `pattern`) на значения таблицы, восстанавливая регистр совпавшего
    фрагмента: весь фрагмент в верхнем регистре -> `.upper()` результата;
    первая буква фрагмента заглавная -> заглавная первая буква результата;
    иначе — результат как есть (таблица хранит нижний регистр).

    Особый случай — однобуквенный фрагмент, дающий многобуквенную замену
    (кириллические диграфы `ш/ч/ё/ю/я/ц/щ` -> `sh/ch/yo/yu/ya/ts/sh`):
    заглавность одной буквы сама по себе не говорит, набрано ли всё слово
    капсом (-> `SH`) или это просто заглавная первая буква слова (-> `Sh`).
    Различаем по контексту — следующей букве исходного текста: заглавная
    буква дальше -> считаем слово капсом, иначе -> `.capitalize()`."""
    if pattern is None:
        return text

    def repl(match: re.Match[str]) -> str:
        frag = match.group(0)
        replacement = table[frag.lower()]
        if frag.isupper():
            if len(frag) == 1 and len(replacement) > 1:
                next_char = text[match.end():match.end() + 1]
                if next_char.isalpha() and next_char.isupper():
                    return replacement.upper()
                return replacement[:1].upper() + replacement[1:]
            return replacement.upper()
        if frag[:1].isupper():
            return replacement[:1].upper() + replacement[1:]
        return replacement

    return pattern.sub(repl, text)


def latin_to_cyrillic(text: str) -> str:
    """Транслитерирует узбекскую латиницу (алфавит 1995 г.) в кириллицу,
    сохраняя регистр. Апострофы унифицируются перед разбором (см.
    `unify_apostrophes`)."""
    text = unify_apostrophes(text)
    text = _translit(text, _LAT_TO_CYR_APOSTROPHE_DIGRAPHS, _LAT_TO_CYR_APOSTROPHE_DIGRAPHS_RE)
    text = _translit(text, _LAT_TO_CYR_DIGRAPHS, _LAT_TO_CYR_DIGRAPHS_RE)
    text = _translit(text, _LAT_TO_CYR_SINGLES, _LAT_TO_CYR_SINGLES_RE)
    text = _translit(text, _LAT_TO_CYR_TUTUQ, _LAT_TO_CYR_TUTUQ_RE)
    return text


def cyrillic_to_latin(text: str) -> str:
    """Транслитерирует узбекскую кириллицу в латиницу (алфавит 1995 г.),
    сохраняя регистр. `ў`/`ғ` дают модификаторную букву `ʻ` (U+02BB) —
    как в исходных узбекских текстах, не ASCII-апостроф."""
    return _translit(text, _CYR_TO_LAT_TABLE, _CYR_TO_LAT_TABLE_RE)


# ── Определение скрипта ──────────────────────────────────────────────────

def _char_script(ch: str) -> str | None:
    if not ch.isalpha():
        return None
    name = unicodedata.name(ch, "")
    if "CYRILLIC" in name:
        return "cyrillic"
    if "LATIN" in name:
        return "latin"
    return None


def detect_script(text: str) -> Literal["latin", "cyrillic", "mixed", "none"]:
    """Определяет скрипт по буквам (цифры/пунктуация/`№` не считаются):
    `mixed`, если и латиница, и кириллица — каждая ≥ 20 % от всех букв;
    `none`, если букв нет вовсе."""
    cyr_count = 0
    lat_count = 0
    for ch in text:
        script = _char_script(ch)
        if script == "cyrillic":
            cyr_count += 1
        elif script == "latin":
            lat_count += 1
    total = cyr_count + lat_count
    if total == 0:
        return "none"
    cyr_ratio = cyr_count / total
    lat_ratio = lat_count / total
    if cyr_ratio >= 0.2 and lat_ratio >= 0.2:
        return "mixed"
    return "cyrillic" if cyr_count > lat_count else "latin"


_WHITESPACE_RE = re.compile(r"\s+")


def normalize_for_match(text: str) -> str:
    """Приводит текст к сравнимому виду вне зависимости от скрипта записи:
    унификация апострофов -> (если скрипт кириллица/mixed) транслитерация в
    латиницу -> нижний регистр -> схлопывание пробелов. Цифры, `№`, дефисы
    и точки не трогаются — транслитерируются только буквы."""
    text = unify_apostrophes(text)
    if detect_script(text) in ("cyrillic", "mixed"):
        text = cyrillic_to_latin(text)
        # cyrillic_to_latin даёт модификаторную ʻ (U+02BB) в "oʻ"/"gʻ" —
        # унифицируем ещё раз, чтобы латинская сторона (обычная ASCII "o'")
        # и кириллическая сторона (после транслитерации) сравнивались как
        # один и тот же апостроф.
        text = unify_apostrophes(text)
    text = text.lower()
    return _WHITESPACE_RE.sub(" ", text).strip()


# ── Узбекские маркеры и альтернативный скрипт ────────────────────────────

_CYRILLIC_MARKERS = ("ў", "ғ", "қ", "ҳ")


def has_uzbek_markers(text: str) -> bool:
    """Сигнал «это узбекский текст», а не, например, русский: кириллица со
    спецбуквами `ў ғ қ ҳ` (любой регистр), либо латиница, где после
    унификации апострофов встречается `o'`/`g'`."""
    unified = unify_apostrophes(text).lower()
    if any(marker in unified for marker in _CYRILLIC_MARKERS):
        return True
    return "o'" in unified or "g'" in unified


def alt_script(text: str) -> str | None:
    """Тот же текст в другом скрипте, если в нём есть узбекские маркеры
    (`has_uzbek_markers`) — иначе `None` (не узбекский текст, скрипт
    менять незачем, например обычный русский). Направление перевода —
    по `detect_script`: латиница -> кириллица, иначе (кириллица/mixed)
    -> латиница."""
    if not has_uzbek_markers(text):
        return None
    if detect_script(text) == "latin":
        return latin_to_cyrillic(text)
    return cyrillic_to_latin(text)
