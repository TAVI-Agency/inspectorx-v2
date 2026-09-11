"""Нормализация узбекского скрипта — латиница ↔ кириллица (Задача 5).

Пары в `test_roundtrip_pairs` — из узбекского латинского алфавита 1995 г.,
взяты дословно из брифа задачи."""
import pytest

from importer.build.uzscript import (
    alt_script, cyrillic_to_latin, detect_script, has_uzbek_markers, latin_to_cyrillic,
    normalize_for_match, unify_apostrophes,
)


@pytest.mark.parametrize("latin,cyr", [
    ("Oʻzbekiston Respublikasi", "Ўзбекистон Республикаси"),
    ("Vazirlar Mahkamasi qarori", "Вазирлар Маҳкамаси қарори"),
    ("mahsulot", "маҳсулот"),
    ("qonun", "қонун"),
    ("gʻisht", "ғишт"),
    ("shartnoma", "шартнома"),
    ("choʻchqa", "чўчқа"),
    ("yangi", "янги"),
    ("Yoʻriqnoma", "Йўриқнома"),
])
def test_roundtrip_pairs(latin, cyr):
    assert latin_to_cyrillic(latin) == cyr
    assert cyrillic_to_latin(cyr) == latin


def test_unify_apostrophes():
    assert unify_apostrophes("o‘ g’ oʻ gʼ o`") == "o' g' o' g' o'"


def test_detect_script():
    assert detect_script("sut mahsulotlari") == "latin"
    assert detect_script("сут маҳсулотлари") == "cyrillic"
    assert detect_script("sut маҳсулот") == "mixed"
    assert detect_script("2026 №737") == "none"


def test_normalize_for_match_makes_scripts_equal():
    assert normalize_for_match("Ўзбекистон Республикаси Вазирлар Маҳкамаси") == \
           normalize_for_match("O‘zbekiston  Respublikasi Vazirlar Mahkamasi")


def test_normalize_for_match_keeps_digits_and_punctuation():
    """№, дефисы, точки и цифры не транслитерируются и не съедаются —
    транслитерируются только буквы."""
    assert normalize_for_match("ПКМ №290-1, п. 24") == "pkm №290-1, p. 24"


def test_has_uzbek_markers_and_alt_script():
    assert has_uzbek_markers("маҳсулот") and has_uzbek_markers("o'zbek")
    assert not has_uzbek_markers("постановление кабинета министров")
    assert alt_script("маҳсулот") == "mahsulot"
    assert alt_script("постановление") is None


def test_alt_script_latin_to_cyrillic():
    assert alt_script("o'zbek") == "ўзбек"


def test_cyrillic_to_latin_digraph_case_restoration():
    """Одиночная кириллическая буква, дающая диграф (ш/ч/ё/ю/я/ц/щ) в
    латинице, не должна путать «слово с заглавной первой буквой» с «слово
    целиком в верхнем регистре» — регистр решает контекст (следующая
    буква исходного текста), а не тривиальный `.isupper()` фрагмента из
    одного символа."""
    assert cyrillic_to_latin("Шартнома") == "Shartnoma"
    assert cyrillic_to_latin("ШАРТНОМА") == "SHARTNOMA"
    assert cyrillic_to_latin("Чўчқа") == "Choʻchqa"
    assert cyrillic_to_latin("Ш") == "Sh"
    assert latin_to_cyrillic("SHARTNOMA") == "ШАРТНОМА"
    assert latin_to_cyrillic("Shartnoma") == "Шартнома"
