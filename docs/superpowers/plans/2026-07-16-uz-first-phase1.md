# UZ-first конвейер, фаза 1 «UZ-канонизация» — Implementation Plan

> **Статус на 29.07.2026:** реализована — код в `main`, PR #7 смержен
> 17.07.2026. Тесты `importer/tests` — 131 passed. Чекбоксы ниже по ходу
> работы не проставлялись: источник истины о состоянии — эта строка, а не
> `- [ ]`. Оговорка: код фазы 1 исправен, но данных не произвёл — входной
> поток остаётся русским (см. «Чего спека не предусмотрела» в
> `docs/superpowers/specs/2026-07-16-uz-first-pipeline-design.md`).

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Гейт верифицирует карточки по узбекской версии акта как канонической (уверенность 1.0), русская сверка становится вторичной (0.95), узбекские оригиналы параграфов копятся в `act_paragraphs.verbatim_uz`.

**Architecture:** Эволюция существующего пакета `importer/` (спека: `docs/superpowers/specs/2026-07-16-uz-first-pipeline-design.md`, фаза 1). Три точки изменений: `lexuz.py` (обнаружение языковых версий, латиница), `verifier.py` (UZ-first логика сверки), `resolver.py`+`pipeline.py` (запись verbatim_uz). Модели и дедуп не меняются.

**Tech Stack:** Python 3.14, pydantic v2, httpx, BeautifulSoup, rapidfuzz, pytest (фейки БД/lex.uz — сеть в тестах не нужна).

## Global Constraints

- Рабочая директория: worktree `/Users/abduraxmonturdiyev/inspector-x-final/.claude/worktrees/report-importer-impl`, ветка `report-importer-impl`.
- Тесты: `.venv-importer/bin/python -m pytest importer/tests -q` — запускать из корня worktree (venv лежит в самом worktree).
- После КАЖДОЙ задачи все существующие тесты зелёные (замерено 16.07: **87 passed**).
- Дедуп-ключ `external_key = lexuz:{gate.doc_id}/{gate.ref}`, где `doc_id` берётся из `req.act.lexuz_url` — НЕ МЕНЯТЬ (инвариант спеки).
- В БД мимо гейта — никогда. Prod-таблицы в этой фазе не трогаем (только код+тесты).
- Коммиты: осмысленное сообщение + `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`.
- **Факты lex.uz (проверено живьём 16.07.2026, Таможенный кодекс):** у каждой языковой версии акта СВОЙ doc_id (RU `2876352`, UZ-кириллица `2876354`, UZ-латиница `-2876354`); языковой префикс `/ru/`|`/uz/` в URL меняет только язык интерфейса, НЕ документа; знак doc_id семантики языка НЕ несёт (у ЗРУ-819 RU-версия = `-6445145`); ссылки на версии — в шапке страницы, блок `docContentHeader__item-link` с `onclick="openUrl('/ru/docs/{id}')"` и `title="Ўзбекча"|"O'zbekcha"|"Русча"|"English"`.

---

### Task 1: Зафиксировать языковую схему lex.uz + UZ-фикстуры

**Files:**
- Modify: `research-loop/DECISIONS.md` (дописать в конец)
- Create: `importer/tests/fixtures/lexuz_act_ru_langs.html`
- Create: `importer/tests/fixtures/lexuz_act_uz_cyr.html`
- Create: `importer/tests/fixtures/lexuz_act_uz_lat.html`

**Interfaces:**
- Produces: три HTML-фикстуры, на которые опираются тесты Task 2–5. Тексты цитат фикстур (используются в тестах дословно):
  - UZ-кириллица: `Рўйхатга киритилган маҳсулот белгиланган тартибда мувофиқликни мажбурий тасдиқлашдан ўтказилиши шарт.`
  - UZ-латиница: `Roʻyxatga kiritilgan mahsulot belgilangan tartibda muvofiqlikni majburiy tasdiqlashdan oʻtkazilishi shart.`
  - doc_id фикстур: RU `-6445145`, UZ-кир `6445146`, UZ-лат `-6445146`.

- [ ] **Step 1: Дописать решение в DECISIONS.md**

Добавить в конец `research-loop/DECISIONS.md`:

```markdown
## 2026-07-16 — языковая схема lex.uz (разведка живьём, фаза 1 UZ-first)

Факт: у каждой языковой версии акта СВОЙ doc_id. Таможенный кодекс: RU 2876352,
UZ-кириллица 2876354 (1600 «модда», 0 «Статья»), UZ-латиница -2876354 (1600 «modda»).
Префикс /ru/|/uz/ в URL меняет только язык интерфейса. Знак doc_id семантики языка
НЕ несёт (ЗРУ-819: RU-версия = -6445145). Единственный надёжный способ найти
UZ-версию — ссылки в шапке страницы (docContentHeader__item-link, title=«Ўзбекча»/
«O'zbekcha»). Следствия: (1) отдельный кэш по языку из спеки НЕ нужен — кэш и так
по doc_id; (2) гейту нужен парсер шапки language_versions(); (3) выбор графики
(кир/лат) — по графике самой цитаты legal_quote_uz.
```

- [ ] **Step 2: Создать фикстуру RU-страницы со ссылками на языковые версии**

`importer/tests/fixtures/lexuz_act_ru_langs.html` (копия `lexuz_act_ru.html` + шапка, воспроизводящая живой HTML lex.uz):

```html
<html><body>
<div class="docContentHeader">
<div class="docContentHeader__item-link" onclick="openUrl('/ru/docs/6445146')" title="Ўзбекча">Ўзб</div>
<div class="docContentHeader__item-link" onclick="openUrl('/ru/docs/-6445146')" title="O'zbekcha">O’zb</div>
<div class="docContentHeader__item-link" onclick="openUrl('/ru/docs/-6445145')" title="Русча">Рус</div>
</div>
<div class="doc">
<p>ЗАКОН РЕСПУБЛИКИ УЗБЕКИСТАН О ТЕХНИЧЕСКОМ РЕГУЛИРОВАНИИ</p>
<p>Статья 13. Общие положения</p>
<p>Текст статьи тринадцать о общих положениях и о порядке в стране, и на территории,
и в организациях, и на предприятиях, и в учреждениях, и в органах, и на местах.</p>
<p>Статья 14. Подтверждение соответствия</p>
<p>Продукция, включённая в перечень, подлежит обязательному подтверждению
соответствия в установленном порядке и в надлежащем виде. Выпуск в обращение без
подтверждения соответствия запрещается, и на рынке, и в торговле, и на складах.</p>
<p>Статья 15. Иное</p>
<p>Иной текст и другие нормы в статье пятнадцать, и на практике, и в целом,
и в применении, и на деле.</p>
</div></body></html>
```

- [ ] **Step 3: Создать UZ-фикстуры (кириллица и латиница)**

`importer/tests/fixtures/lexuz_act_uz_cyr.html`:

```html
<html><body><div class="doc">
<p>ЎЗБЕКИСТОН РЕСПУБЛИКАСИНИНГ ҚОНУНИ ТЕХНИК ЖИҲАТДАН ТАРТИБГА СОЛИШ ТЎҒРИСИДА</p>
<p>13-модда. Умумий қоидалар</p>
<p>Ўн учинчи модданинг матни умумий қоидалар ҳақида баён этилади.</p>
<p>14-модда. Мувофиқликни тасдиқлаш</p>
<p>Рўйхатга киритилган маҳсулот белгиланган тартибда мувофиқликни мажбурий
тасдиқлашдан ўтказилиши шарт. Мувофиқлик тасдиқланмасдан муомалага чиқариш
тақиқланади.</p>
<p>15-модда. Бошқа қоидалар</p>
<p>Ўн бешинчи модда матни бошқа қоидалар ҳақида.</p>
</div></body></html>
```

`importer/tests/fixtures/lexuz_act_uz_lat.html`:

```html
<html><body><div class="doc">
<p>OʻZBEKISTON RESPUBLIKASINING QONUNI TEXNIK JIHATDAN TARTIBGA SOLISH TOʻGʻRISIDA</p>
<p>13-modda. Umumiy qoidalar</p>
<p>Oʻn uchinchi moddaning matni umumiy qoidalar haqida bayon etiladi.</p>
<p>14-modda. Muvofiqlikni tasdiqlash</p>
<p>Roʻyxatga kiritilgan mahsulot belgilangan tartibda muvofiqlikni majburiy
tasdiqlashdan oʻtkazilishi shart. Muvofiqlik tasdiqlanmasdan muomalaga chiqarish
taqiqlanadi.</p>
<p>15-modda. Boshqa qoidalar</p>
<p>Oʻn beshinchi modda matni boshqa qoidalar haqida.</p>
</div></body></html>
```

- [ ] **Step 4: Прогнать все тесты (регрессия — фикстуры ничего не ломают)**

Run: `.venv-importer/bin/python -m pytest importer/tests -q`
Expected: все зелёные (87 passed)

- [ ] **Step 5: Commit**

```bash
git add research-loop/DECISIONS.md importer/tests/fixtures/lexuz_act_ru_langs.html importer/tests/fixtures/lexuz_act_uz_cyr.html importer/tests/fixtures/lexuz_act_uz_lat.html
git commit -m "docs(loop): языковая схема lex.uz (doc_id на язык) + UZ-фикстуры для фазы 1

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 2: `LexuzClient.language_versions()` — парсер ссылок на языковые версии

**Files:**
- Modify: `importer/lexuz.py` (добавить метод + словарь `_LANG_TITLES` на уровне модуля)
- Test: `importer/tests/test_lexuz.py` (дописать)

**Interfaces:**
- Consumes: фикстура `lexuz_act_ru_langs.html` из Task 1.
- Produces: `LexuzClient.language_versions(html: str) -> dict[str, str]` — ключи `"uz_cyr" | "uz_lat" | "ru" | "en"` (присутствуют только найденные), значения — doc_id со знаком. Task 4 вызывает этот метод из verifier.

- [ ] **Step 1: Write the failing test**

Дописать в `importer/tests/test_lexuz.py` (в файле уже есть `FIX = Path(__file__).parent / "fixtures"` — если импортов Path/FIX нет, добавить по образцу test_verifier.py):

```python
RU_LANGS_HTML = (FIX / "lexuz_act_ru_langs.html").read_text()


def test_language_versions_parses_header():
    v = LexuzClient.language_versions(RU_LANGS_HTML)
    assert v == {"uz_cyr": "6445146", "uz_lat": "-6445146", "ru": "-6445145"}


def test_language_versions_empty_when_no_header():
    assert LexuzClient.language_versions("<p>страница без шапки</p>") == {}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv-importer/bin/python -m pytest importer/tests/test_lexuz.py -q`
Expected: FAIL — `AttributeError: ... has no attribute 'language_versions'`

- [ ] **Step 3: Write minimal implementation**

В `importer/lexuz.py` на уровне модуля (после определения `LexuzUnreachable`):

```python
# Заголовки языковых ссылок шапки lex.uz → наш код языка.
# Язык версии определяется ТОЛЬКО по title: знак doc_id семантики не несёт
# (см. research-loop/DECISIONS.md, запись 2026-07-16).
_LANG_TITLES = {
    "Ўзбекча": "uz_cyr",
    "O'zbekcha": "uz_lat", "O’zbekcha": "uz_lat", "O‘zbekcha": "uz_lat",
    "Русча": "ru", "Русский": "ru",
    "English": "en", "Инглизча": "en",
}
```

Метод в класс `LexuzClient`:

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv-importer/bin/python -m pytest importer/tests/test_lexuz.py -q`
Expected: PASS (все тесты файла)

- [ ] **Step 5: Commit**

```bash
git add importer/lexuz.py importer/tests/test_lexuz.py
git commit -m "feat(gate): language_versions() — обнаружение UZ/RU/EN версий акта по шапке lex.uz

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 3: Латиница в `find_paragraph` + определение графики цитаты

**Files:**
- Modify: `importer/lexuz.py:64-92` (`find_paragraph`) + новый статик-метод `quote_script`
- Test: `importer/tests/test_lexuz.py` (дописать)

**Interfaces:**
- Consumes: фикстуры `lexuz_act_uz_cyr.html`, `lexuz_act_uz_lat.html` из Task 1.
- Produces: `find_paragraph` находит `N-modda.` (латиница); `LexuzClient.quote_script(text: str) -> str` возвращает `"cyr"` или `"lat"`. Task 4 использует оба.

- [ ] **Step 1: Write the failing tests**

Дописать в `importer/tests/test_lexuz.py`:

```python
UZ_CYR_HTML = (FIX / "lexuz_act_uz_cyr.html").read_text()
UZ_LAT_HTML = (FIX / "lexuz_act_uz_lat.html").read_text()


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
```

- [ ] **Step 2: Run tests to verify the latin one fails**

Run: `.venv-importer/bin/python -m pytest importer/tests/test_lexuz.py -q`
Expected: FAIL — `test_find_paragraph_uz_latin_article` (латиница не распознаётся) и `test_quote_script` (метода нет)

- [ ] **Step 3: Write minimal implementation**

В `find_paragraph` (lexuz.py) заменить две строки:

```python
            for pat in (rf"Статья\s+{num}\.", rf"{num}-модда\."):
```
→
```python
            for pat in (rf"Статья\s+{num}\.", rf"{num}-модда\.", rf"{num}-modda\."):
```

и границу следующей статьи:

```python
                    nxt = re.search(r"Статья\s+[\d-]+\.|[\d-]+-модда\.", rest[10:])
```
→
```python
                    nxt = re.search(r"Статья\s+[\d-]+\.|[\d-]+-модда\.|[\d-]+-modda\.",
                                    rest[10:])
```

Новый статик-метод в `LexuzClient`:

```python
    @staticmethod
    def quote_script(text: str) -> str:
        """Графика узбекской цитаты: 'cyr' | 'lat' — для выбора версии акта."""
        low = text.lower()
        cyr = len(re.findall(r"[а-яёўқғҳ]", low))
        lat = len(re.findall(r"[a-z]", low))
        return "lat" if lat > cyr else "cyr"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv-importer/bin/python -m pytest importer/tests/test_lexuz.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add importer/lexuz.py importer/tests/test_lexuz.py
git commit -m "feat(gate): латиница N-modda в find_paragraph + quote_script() для выбора графики

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 4: UZ-first логика гейта в `verifier.py`

**Files:**
- Modify: `importer/verifier.py` (GateResult + verify_item)
- Test: `importer/tests/test_verifier.py` (новые тесты + правка двух существующих)

**Interfaces:**
- Consumes: `LexuzClient.language_versions()` (Task 2), `quote_script()` и латиница в `find_paragraph` (Task 3), фикстуры Task 1.
- Produces: `GateResult` получает поля `verified_lang: str | None` (`"uz"` | `"ru"`), `uz_backfill_needed: bool`, `uz_doc_id: str | None`. Семантика: `verified_lang="uz"` + `penalty 1.0` — канон; RU-сверка — `penalty 0.95` + `uz_backfill_needed=True`. Новая причина review: `uz_version_not_found`. Task 5 читает `gate.verified_lang`; фаза 3 (gap-ресёрчер) будет добивать карточки с `uz_backfill_needed`.

- [ ] **Step 1: Write the failing tests**

Дописать в `importer/tests/test_verifier.py`:

```python
RU_LANGS_HTML = (FIX / "lexuz_act_ru_langs.html").read_text()
UZ_CYR_HTML = (FIX / "lexuz_act_uz_cyr.html").read_text()
UZ_LAT_HTML = (FIX / "lexuz_act_uz_lat.html").read_text()
UZ_QUOTE_CYR = ("Рўйхатга киритилган маҳсулот белгиланган тартибда мувофиқликни "
                "мажбурий тасдиқлашдан ўтказилиши шарт.")
UZ_QUOTE_LAT = ("Roʻyxatga kiritilgan mahsulot belgilangan tartibda muvofiqlikni "
                "majburiy tasdiqlashdan oʻtkazilishi shart.")


def routed_client(tmp_path):
    """RU-страница с шапкой; UZ-версии отдаются по своим doc_id."""
    def fetcher(url):
        if url.endswith("/docs/6445146"):
            return UZ_CYR_HTML
        if url.endswith("/docs/-6445146"):
            return UZ_LAT_HTML
        return RU_LANGS_HTML
    return LexuzClient(cache_dir=tmp_path, fetcher=fetcher)


def test_uz_canonical_via_header_links(tmp_path):
    # Узбекская цитата + RU-страница с шапкой → гейт сам находит UZ-версию,
    # сверяет по ней с полным доверием; ключ дедупа остаётся от act.lexuz_url.
    r = verify_item(req(legal_quote_uz=UZ_QUOTE_CYR), routed_client(tmp_path), llm=None)
    assert r.ok and r.verified_lang == "uz"
    assert r.confidence >= 0.95           # канон: penalty 1.0
    assert r.doc_id == "-6445145"          # инвариант дедупа
    assert r.uz_doc_id == "6445146"
    assert not r.uz_backfill_needed


def test_uz_latin_quote_routes_to_latin_version(tmp_path):
    r = verify_item(req(legal_quote_uz=UZ_QUOTE_LAT), routed_client(tmp_path), llm=None)
    assert r.ok and r.verified_lang == "uz" and r.uz_doc_id == "-6445146"


def test_ru_fallback_flags_backfill(tmp_path):
    # Только RU-цитата, страница без шапки → вторичная сверка 0.95 + флаг добивки.
    r = verify_item(req(), client(tmp_path), llm=None)
    assert r.ok and r.verified_lang == "ru" and r.uz_backfill_needed
    assert r.confidence == 0.95


def test_uz_quote_but_no_uz_link(tmp_path):
    # Узбекская цитата, но RU-страница без ссылок на UZ-версии → review.
    r = verify_item(req(legal_quote_uz=UZ_QUOTE_CYR), client(tmp_path), llm=None)
    assert not r.ok and r.reason == "uz_version_not_found"
```

Обновить ДВА существующих теста (семантика поменялась):

`test_gate_passes` — RU-сверка теперь вторичная:

```python
def test_gate_passes(tmp_path):
    r = verify_item(req(), client(tmp_path), llm=None)
    assert r.ok and r.doc_id == "-6445145" and r.ref == "art.14"
    assert r.confidence >= 0.85
    assert r.verified_lang == "ru" and r.uz_backfill_needed  # переходный режим
```

`test_uz_branch_verifies_uz_quote_on_uz_only_page` — UZ-цитата на UZ-only странице теперь канон (penalty 1.0; остаётся только штраф 0.9 за сверку перечня по всей странице):

```python
def test_uz_branch_verifies_uz_quote_on_uz_only_page(tmp_path):
    # UZ-only страница + legal_quote_uz → канон: сверка по самой странице, penalty 1.0
    r = verify_item(req(legal_quote_uz=UZ_ROW, unit="прил. № 4, строка 9",
                        legal_quote_ru=None),
                    client(tmp_path, UZ_HTML), llm=None)
    assert r.ok and r.verified_lang == "uz" and r.ref == "app4/row9"
    assert 0.85 <= r.confidence <= 0.95   # 1.0 * 0.9 (fallback по всей странице)
```

- [ ] **Step 2: Run tests to verify new ones fail**

Run: `.venv-importer/bin/python -m pytest importer/tests/test_verifier.py -q`
Expected: FAIL — `TypeError`/`AttributeError` (нет полей verified_lang/uz_doc_id/uz_backfill_needed), `uz_version_not_found` не существует

- [ ] **Step 3: Write the implementation**

`importer/verifier.py` — новый `GateResult` (добавить 3 поля):

```python
@dataclass
class GateResult:
    ok: bool
    reason: str | None = None
    detail: str | None = None
    doc_id: str | None = None
    ref: str | None = None
    confidence: float | None = None
    paragraph_text: str | None = None
    verified_lang: str | None = None      # "uz" — канон, "ru" — переходный режим
    uz_backfill_needed: bool = False      # карточку надо добить UZ-цитатой (фаза 3)
    uz_doc_id: str | None = None          # doc_id узбекской версии, если найден
```

Переписать блок выбора цитаты/страницы в `verify_item` (строки 41–65 старой версии — от комментария «UZ-ветка» до конца `elif not LexuzClient.is_russian(html)`) на:

```python
    # UZ-first (фаза 1, спека 2026-07-16): канон — узбекская цитата против
    # узбекской версии акта (у неё СВОЙ doc_id, ищем по шапке страницы).
    # RU-сверка — вторичная (penalty 0.95) + флаг добивки для фазы 3.
    quote = None
    penalty = 1.0
    verified_lang = None
    uz_backfill = False
    uz_doc_id = None
    page = html

    if getattr(req, "verify_url", None):
        # Явный оверрайд страницы сверки из отчёта (прежнее поведение).
        verify_doc = lexuz_doc_id(req.verify_url)
        if not verify_doc:
            return _review("act_not_found", f"verify_url не lex.uz: {req.verify_url!r}",
                           doc_id=doc_id)
        try:
            page = lexuz.fetch(verify_doc)
        except LexuzUnreachable as e:
            return _review("lexuz_unreachable", str(e), doc_id=doc_id)
        if getattr(req, "legal_quote_uz", None):
            quote, verified_lang, uz_doc_id = req.legal_quote_uz, "uz", verify_doc
        else:
            quote, verified_lang, uz_backfill = req.legal_quote_ru, "ru", True
        penalty = 0.95  # страница указана отчётом, не подтверждена шапкой акта
    elif getattr(req, "legal_quote_uz", None):
        quote, verified_lang = req.legal_quote_uz, "uz"
        if LexuzClient.is_russian(html):
            versions = LexuzClient.language_versions(html)
            script = LexuzClient.quote_script(quote)
            uz_doc_id = (versions.get(f"uz_{script}")
                         or versions.get("uz_cyr") or versions.get("uz_lat"))
            if uz_doc_id is None:
                return _review("uz_version_not_found",
                               "на RU-странице нет ссылки на UZ-версию акта",
                               doc_id=doc_id)
            try:
                page = lexuz.fetch(uz_doc_id)
            except LexuzUnreachable as e:
                return _review("lexuz_unreachable", str(e), doc_id=doc_id)
        # страница сама UZ → сверяем по ней; penalty остаётся 1.0 (канон)
    elif not LexuzClient.is_russian(html):
        return _review("uz_only_act",
                       "официального RU-текста нет и нет legal_quote_uz для UZ-сверки",
                       doc_id=doc_id)
    else:
        # Переходный режим: только RU-цитата против RU-страницы.
        quote, verified_lang, uz_backfill = req.legal_quote_ru, "ru", True
        penalty = 0.95
```

Дальше по функции: заменить все обращения к `html` на `page` (в `find_paragraph` и `page_text`), и в ТРЁХ местах возврата результата пробросить новые поля:

```python
    paragraph = LexuzClient.find_paragraph(page, ref)
    if paragraph is None:
        if ref.startswith(("art.", "p.")):
            return _review("unit_not_found", f"пункт {ref} не найден в акте",
                           doc_id=doc_id, ref=ref)
        paragraph = LexuzClient.page_text(page)  # перечни: сверка по всей странице (v1)
        penalty *= 0.9

    if not quote:
        return _review("quote_missing", "нет legal_quote_ru/uz", doc_id=doc_id, ref=ref)

    score = fuzz.partial_ratio(quote.lower(), paragraph.lower()) / 100.0
    confidence = round(score * penalty, 2)
    extra = {"verified_lang": verified_lang, "uz_backfill_needed": uz_backfill,
             "uz_doc_id": uz_doc_id}
    if score >= 0.85:
        return GateResult(ok=True, doc_id=doc_id, ref=ref, confidence=confidence,
                          paragraph_text=paragraph[:4000], **extra)
    if score >= 0.60 and llm is not None and llm.same_meaning(quote, paragraph[:6000]):
        return GateResult(ok=True, doc_id=doc_id, ref=ref, confidence=confidence,
                          paragraph_text=paragraph[:4000], **extra)
    return _review("quote_mismatch", f"fuzzy={score:.2f}", doc_id=doc_id, ref=ref,
                   confidence=confidence)
```

Проверка `is_repealed` остаётся на странице из `act.lexuz_url` (как сейчас, строка 38) — не двигать.

- [ ] **Step 4: Run the full verifier suite**

Run: `.venv-importer/bin/python -m pytest importer/tests/test_verifier.py -q`
Expected: PASS (все, включая обновлённые test_gate_passes и test_uz_branch_*)

- [ ] **Step 5: Run ALL tests (регрессия — pipeline/seeds зависят от verify_item)**

Run: `.venv-importer/bin/python -m pytest importer/tests -q`
Expected: все зелёные

- [ ] **Step 6: Commit**

```bash
git add importer/verifier.py importer/tests/test_verifier.py
git commit -m "feat(gate): UZ-first — узбекская версия акта канонична (1.0), RU вторична (0.95, uz_backfill)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 5: `verbatim_uz` в библиотеку оригиналов (resolver + pipeline)

**Files:**
- Modify: `importer/resolver.py:67-77` (`ensure_paragraph`)
- Modify: `importer/pipeline.py:95-96` (вызов `ensure_paragraph`)
- Test: `importer/tests/test_resolver.py` (дописать)

**Interfaces:**
- Consumes: `gate.verified_lang` из Task 4; `req.legal_quote_uz` (модель, есть).
- Produces: `ensure_paragraph(ix, act_row, ref, quote_ru, doc_id, *, quote_uz=None) -> dict` — новый keyword-параметр; пишет `verbatim_uz` при вставке и ДОСАЖИВАЕТ его в существующую строку, если там пусто (библиотека оригиналов копится, элемент Б спеки).

- [ ] **Step 1: Write the failing tests**

Дописать в `importer/tests/test_resolver.py`:

```python
def test_ensure_paragraph_writes_verbatim_uz(tmp_path):
    ix = FakeClient({"act_paragraphs": []})
    p = ensure_paragraph(ix, {"id": "act-1"}, "art.14", "цитата ру", "6445145",
                         quote_uz="иқтибос ўз")
    assert p["verbatim_uz"] == "иқтибос ўз" and p["verbatim_ru"] == "цитата ру"


def test_ensure_paragraph_backfills_verbatim_uz(tmp_path):
    # Старая строка без UZ — новая цитата досаживает оригинал, не создавая дубля.
    ix = FakeClient({"act_paragraphs": []})
    p1 = ensure_paragraph(ix, {"id": "act-1"}, "art.14", "цитата ру", "6445145")
    assert p1.get("verbatim_uz") is None
    p2 = ensure_paragraph(ix, {"id": "act-1"}, "art.14", "цитата ру", "6445145",
                          quote_uz="иқтибос ўз")
    assert p2["id"] == p1["id"]
    assert len(ix.store["act_paragraphs"]) == 1
    assert ix.store["act_paragraphs"][0]["verbatim_uz"] == "иқтибос ўз"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv-importer/bin/python -m pytest importer/tests/test_resolver.py -q`
Expected: FAIL — `TypeError: ensure_paragraph() got an unexpected keyword argument 'quote_uz'`

- [ ] **Step 3: Write the implementation**

`importer/resolver.py`, заменить `ensure_paragraph` целиком:

```python
def ensure_paragraph(ix, act_row: dict, ref: str, quote_ru: str | None, doc_id: str,
                     *, quote_uz: str | None = None) -> dict:
    existing = _first(ix.table("act_paragraphs").select("*")
                      .eq("act_id", act_row["id"]).eq("paragraph_ref", ref).limit(1).execute())
    if existing:
        if quote_uz and not existing.get("verbatim_uz"):
            # Библиотека оригиналов копится: досаживаем UZ-текст в старую строку.
            ix.table("act_paragraphs").update({"verbatim_uz": quote_uz}) \
                .eq("id", existing["id"]).execute()
            existing = {**existing, "verbatim_uz": quote_uz}
        return existing
    return _first(ix.table("act_paragraphs").insert({
        "act_id": act_row["id"],
        "paragraph_ref": ref,
        "verbatim_ru": quote_ru,
        "verbatim_uz": quote_uz,
        "deep_link_url": f"https://lex.uz/ru/docs/{doc_id}",
    }).execute())
```

`importer/pipeline.py`, заменить вызов (строки 95–96):

```python
            paragraph_row = ensure_paragraph(
                ix, act_row, gate.ref, req.legal_quote_ru, gate.doc_id,
                quote_uz=(req.legal_quote_uz if gate.verified_lang == "uz" else None))
```

(UZ-цитата пишется в библиотеку ТОЛЬКО когда гейт подтвердил её по узбекской странице — непроверенный текст в оригиналы не попадает.)

- [ ] **Step 4: Run resolver + pipeline tests**

Run: `.venv-importer/bin/python -m pytest importer/tests/test_resolver.py importer/tests/test_pipeline.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add importer/resolver.py importer/pipeline.py importer/tests/test_resolver.py
git commit -m "feat(originals): verbatim_uz в act_paragraphs — библиотека узбекских оригиналов копится через гейт

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 6: Сквозная регрессия + смоук на живом lex.uz + отчёт

**Files:**
- Modify: `research-loop/DECISIONS.md` (итог фазы 1)

**Interfaces:**
- Consumes: всё из Task 1–5.
- Produces: подтверждение «фаза 1 готова»; заметка в DECISIONS с результатом смоука.

- [ ] **Step 1: Полный прогон всех тестов**

Run: `.venv-importer/bin/python -m pytest importer/tests -q`
Expected: все зелёные (~95+ passed: старые 87 + новые из Task 2–5)

- [ ] **Step 2: Смоук на живом lex.uz (сеть; вне песочницы)**

Одноразовый скрипт (не коммитить), проверяет связку language_versions + find_paragraph на настоящем Таможенном кодексе:

```bash
.venv-importer/bin/python - <<'EOF'
from pathlib import Path
from importer.lexuz import LexuzClient

lex = LexuzClient(cache_dir=Path("/tmp/lexuz_smoke"))
html_ru = lex.fetch("2876352")                       # Таможенный кодекс, RU
v = LexuzClient.language_versions(html_ru)
print("versions:", v)
assert v.get("uz_cyr") == "2876354", v
html_uz = lex.fetch(v["uz_cyr"])
body = LexuzClient.find_paragraph(html_uz, "art.29")
assert body and "модда" in body, body[:200] if body else None
print("art.29 UZ ok:", body[:120])
html_lat = lex.fetch(v["uz_lat"])
body_lat = LexuzClient.find_paragraph(html_lat, "art.29")
assert body_lat and "modda" in body_lat
print("art.29 UZ-latin ok:", body_lat[:120])
EOF
```

Expected: `versions: {...'uz_cyr': '2876354'...}`, обе статьи найдены. Если сеть в песочнице недоступна — запускать с отключённой песочницей (известные грабли).

- [ ] **Step 3: Дописать итог в DECISIONS.md**

```markdown
## 2026-07-16 — фаза 1 UZ-first: готово

Гейт UZ-first: узбекская версия акта канонична (penalty 1.0, verified_lang=uz),
RU-сверка вторична (0.95 + uz_backfill_needed для фазы 3). Новая причина review:
uz_version_not_found. verbatim_uz копится в act_paragraphs через гейт (только
подтверждённые цитаты). Смоук на живом Таможенном кодексе: [вписать результат].
Метрика для фазы 3: доля act_paragraphs с verbatim_uz.
```

- [ ] **Step 4: Commit**

```bash
git add research-loop/DECISIONS.md
git commit -m "docs(loop): итог фазы 1 UZ-first — гейт канонизирован, смоук на живом lex.uz

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

## Вне скоупа фазы 1 (следующие планы)

- ~~**Фаза 2 (перевод):**~~ **сделана** — PR #8 смержен 27.07.2026: колонка `translation_origin` (миграция `20260717120000_translation_origin.sql`, накатана на прод), `importer/translator.py`, `lang="uz"`-строки contents/details, параметризация `lang` в loader/dedup. Вторая половина оговорки в силе и на 29.07.2026: contents остаются RU (в проде 345 строк `lang='ru'`, 0 — `lang='uz'`), потому что тексты отчётов русские; писать их как `lang="uz"` было бы ложью.
- **Фаза 3 (оркестратор):** не начата — gap-ресёрчер, добивка `uz_backfill_needed`-карточек (запрос: `act_paragraphs.verbatim_uz IS NULL`), авторазбор очереди. Именно она оживляет фазы 1–2: без узбекского входа они данных не производят.
- **Фаза 4:** не начата — аудитор, reconciliation. Backfill старых карточек из фазы 4 вынесен вперёд и выполнен 28.07.2026 инструментом `research-loop/backfill_verbatim_uz.py` (PR #11): `verbatim_uz` заполнен у 75 из 200 параграфов, 7 не найдены, 118 пропущены как легаси-ref из переноса v1.
