from pathlib import Path
import pytest
from importer.lexuz import LexuzClient, LexuzUnreachable

FIX = Path(__file__).parent / "fixtures"
HTML = (FIX / "lexuz_act_ru.html").read_text()


def make_client(tmp_path, responses):
    calls = []
    def fetcher(url):
        calls.append(url)
        r = responses.pop(0)
        if isinstance(r, Exception):
            raise r
        return r
    return LexuzClient(cache_dir=tmp_path, fetcher=fetcher), calls


def test_fetch_caches(tmp_path):
    client, calls = make_client(tmp_path, [HTML])
    assert client.fetch("6445145") == HTML
    assert client.fetch("6445145") == HTML  # второй раз из кэша
    assert len(calls) == 1


def test_fetch_unreachable(tmp_path):
    client, _ = make_client(tmp_path, [LexuzUnreachable("boom")])
    with pytest.raises(LexuzUnreachable):
        client.fetch("1")


def test_find_paragraph_article():
    text = LexuzClient.find_paragraph(HTML, "art.14")
    assert "обязательному подтверждению" in text
    assert "статье пятнадцать" not in text


def test_find_paragraph_missing():
    assert LexuzClient.find_paragraph(HTML, "art.99") is None
    assert LexuzClient.find_paragraph(HTML, "app4/row91") is None


def test_is_russian_and_repealed():
    assert LexuzClient.is_russian(HTML) is True
    assert LexuzClient.is_repealed(HTML) is False
    assert LexuzClient.is_repealed("<p>Документ утратил силу 01.01.2025</p>") is True


def test_find_paragraph_uz_modda():
    from importer.lexuz import LexuzClient
    html = "<p>12-модда. Аввалги матн. 13-модда. Керакли модда матни бу ерда. 14-модда. Кейинги.</p>"
    para = LexuzClient.find_paragraph(html, "art.13")
    assert para and "Керакли модда матни" in para and "Кейинги" not in para


def test_find_paragraph_skips_toc_picks_body():
    from importer.lexuz import LexuzClient
    # Кодекс: оглавление (заголовки подряд) + настоящее тело ниже
    html = ("<p>Статья 30. Экспорт Статья 31. Реэкспорт Статья 32. Импорт</p>"
            "<p>Статья 30. Экспорт " + "существенный текст статьи про экспорт. " * 8
            + "Статья 31. Дальше.</p>")
    para = LexuzClient.find_paragraph(html, "art.30")
    assert para and "существенный текст" in para and len(para) > 120


RU_LANGS_HTML = (FIX / "lexuz_act_ru_langs.html").read_text()

UZ_CYR_HTML = (FIX / "lexuz_act_uz_cyr.html").read_text()
UZ_LAT_HTML = (FIX / "lexuz_act_uz_lat.html").read_text()


def test_language_versions_parses_header():
    v = LexuzClient.language_versions(RU_LANGS_HTML)
    assert v == {"uz_cyr": "6445146", "uz_lat": "-6445146", "ru": "-6445145"}


def test_language_versions_empty_when_no_header():
    assert LexuzClient.language_versions("<p>страница без шапки</p>") == {}


def test_find_paragraph_uz_latin_article():
    body = LexuzClient.find_paragraph(UZ_LAT_HTML, "art.14")
    assert body is not None and "majburiy tasdiqlashdan" in body
    assert "15-modda" not in body  # граница следующей статьи соблюдена


def test_find_paragraph_uz_cyr_article_still_works():
    body = LexuzClient.find_paragraph(UZ_CYR_HTML, "art.14")
    assert body is not None and "мажбурий тасдиқлашдан" in body


def test_quote_script():
    assert LexuzClient.quote_script("мувофиқликни тасдиқлаш шарт") == "cyr"
    assert LexuzClient.quote_script("muvofiqlikni tasdiqlash shart") == "lat"


def test_language_versions_recognizes_okina_apostrophe():
    # Официальный узбекский апостроф — U+02BB (ʻ), а не U+0027/U+2019/U+2018.
    html = ("<a onclick=\"openUrl('/uz/docs/-777')\" "
            "title=\"Oʻzbekcha\">Oʻzbekcha</a>")
    assert LexuzClient.language_versions(html) == {"uz_lat": "-777"}