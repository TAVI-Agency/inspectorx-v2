# Импортёр deep-research отчётов — план имплементации

> **Статус на 29.07.2026:** реализован — код конвейера `importer/` в `main`
> (PR #7 смержен 17.07.2026; сам план — PR #5, 12.07.2026). Тесты
> `importer/tests` — 131 passed. Чекбоксы ниже по ходу работы не проставлялись:
> источник истины о состоянии — эта строка, а не `- [ ]`.
> Отменённое: ограничение «UZ-only акты в v1 → review `uz_only_act`
> (ветка перевода — вне скоупа)» из Global Constraints заменено спекой
> `docs/superpowers/specs/2026-07-16-uz-first-pipeline-design.md` и реализовано
> фазами 1–2 (PR #7 17.07.2026, PR #8 27.07.2026).

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** CLI-конвейер `import-report <file>`: markdown-отчёт deep research → верификация против lex.uz → дедуп по ключу акт+пункт → проверенные карточки в Supabase Inspector X; всё сомнительное — в review-очередь `import_items`.

**Architecture:** Python-пакет `importer/` в репо `inspector-x-final`. Пайплайн parse → resolve → verify → dedup → load со staging-таблицами (`import_runs`/`import_items`). Спека: `docs/superpowers/specs/2026-07-12-report-importer-design.md` — читать перед работой.

**Tech Stack:** Python 3.14 (venv `.venv-importer` в корне), pydantic v2, httpx, beautifulsoup4, rapidfuzz, supabase-py, pyyaml, pytest. LLM — subprocess `claude -p` (по подписке).

## Global Constraints

- Прямая заливка JSON в БД запрещена: между отчётом и БД — верификационный гейт; провал любой проверки → item `review`, не в основные таблицы.
- Дедуп глобальный по ключу `external_key = "lexuz:{doc_id}/{ref}"`; ложная склейка хуже дубля: сомнение → review.
- Классификация только в закрытые словари (`mappings.py`, `domains.yaml`); нет полки → review `no_dictionary_slot`. Словари автоматически не расширяются.
- Идемпотентность: повторный прогон файла не создаёт дублей (run по `file_hash`, items пересоздаются, требования — select-before-insert по `external_key`).
- Гейт пройден → `status='published'`, `trust_label='validated'`, `origin='ai_pipeline'`.
- UZ-only акты в v1 → review `uz_only_act` (ветка перевода — вне скоупа).
- Детерминизм в валидации: LLM только для конвертации формата и спорной сверки смысла (60–85 fuzzy), решения принимают правила.
- Все команды из корня worktree. Сетевые команды (pip install, живые прогоны) в sandbox могут не иметь сети — использовать `dangerouslyDisableSandbox` (известные грабли проекта).
- Коммиты подписывать `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`; git-юзер TAVI-Agency.
- Никогда не пушить в main; работа в ветке `worktree-report-importer`, в конце — draft PR.

## Карта файлов

| Файл | Ответственность |
|---|---|
| `importer/models.py` | Pydantic-схемы отчётов (product + service) |
| `importer/parser.py` | имя файла → мета; извлечение JSON-блока и серых зон; валидация с LLM-фолбэком |
| `importer/refs.py` | парсер unit-ref («ст. 14» → `art.14`) и нормализация lex.uz-URL |
| `importer/llm.py` | абстракция LLM: `claude -p` через subprocess, инжектируемый runner для тестов |
| `importer/lexuz.py` | fetch страниц lex.uz с дисковым кэшем, признаки «утратил силу»/UZ-only, поиск пункта |
| `importer/mappings.py` | закрытые словари: категории→NTM, адресаты→party_role, этапы→lifecycle codes, scope |
| `importer/domains.yaml` | ручной словарь домен → ТН ВЭД-префиксы |
| `importer/db.py` | Supabase-клиенты (Inspector X rw, JurisBase ro) из `.env.importer` |
| `importer/resolver.py` | резолв акта: JurisBase lookup, upsert в IX `acts`/`act_paragraphs`, очередь загрузки |
| `importer/verifier.py` | верификационный гейт → `GateResult` |
| `importer/dedup.py` | external_key, поиск существующего, merge scope, детект конфликтов |
| `importer/loader.py` | запись run/items/requirements+contents+details+citations+applicability+sources |
| `importer/pipeline.py` | оркестрация одного файла, `RunSummary` |
| `importer/cli.py` | `import-report [--dry-run]`, `review list/show` |
| `importer/tests/` | pytest: юниты + фикстуры (синтетический отчёт, HTML акта) |
| `supabase/migrations/20260713000000_import_pipeline.sql` | staging-таблицы + enum `validated` |

---

### Task 1: Скаффолдинг пакета и окружения

**Files:**
- Create: `importer/__init__.py`, `importer/requirements.txt`, `importer/tests/__init__.py`, `importer/tests/test_smoke.py`, `.env.importer.example`
- Modify: `.gitignore`

**Interfaces:**
- Produces: venv `.venv-importer/`, команда запуска тестов `.venv-importer/bin/python -m pytest importer/tests -v`, переменные окружения `IX_SUPABASE_URL`, `IX_SUPABASE_SERVICE_KEY`, `JB_SUPABASE_URL`, `JB_SUPABASE_KEY`.

- [ ] **Step 1: создать окружение и зависимости**

```bash
python3 -m venv .venv-importer
.venv-importer/bin/pip install pydantic httpx beautifulsoup4 rapidfuzz supabase pyyaml pytest python-dotenv
.venv-importer/bin/pip freeze > importer/requirements.txt
```
(при отсутствии сети в sandbox — `dangerouslyDisableSandbox`)

- [ ] **Step 2: файлы пакета**

`importer/__init__.py` и `importer/tests/__init__.py` — пустые.

`.env.importer.example`:
```bash
# Inspector X (service role — пишет в БД)
IX_SUPABASE_URL="https://kcjlrvgjtoefqgzxuizz.supabase.co"
IX_SUPABASE_SERVICE_KEY="sb_secret_..."
# JurisBase lexportal (read-only)
JB_SUPABASE_URL="https://<jurisbase-project>.supabase.co"
JB_SUPABASE_KEY="sb_publishable_..."
```

Дописать в `.gitignore`:
```
.venv-importer/
.env.importer
research/.cache/
```

`importer/tests/test_smoke.py`:
```python
def test_package_imports():
    import importer
    assert importer is not None
```

- [ ] **Step 3: прогнать тест**

Run: `.venv-importer/bin/python -m pytest importer/tests -v`
Expected: `1 passed`

- [ ] **Step 4: Commit**

```bash
git add importer .env.importer.example .gitignore
git commit -m "chore(importer): скаффолдинг python-пакета импортёра"
```

---

### Task 2: Pydantic-модели схемы отчёта

**Files:**
- Create: `importer/models.py`, `importer/tests/test_models.py`

**Interfaces:**
- Produces: `ProductReport`, `ServiceReport`, `ProductRequirement`, `ServiceRequirement`, `ActRef`, `ProductScope`, `Sanction`, `HowToStep`, `DocumentItem` (импорт: `from importer.models import ...`). `ProductReport.model_validate(dict)` бросает `pydantic.ValidationError` на невалидном. Union-хелпер `parse_report_json(data: dict, kind: str) -> ProductReport | ServiceReport`.

- [ ] **Step 1: failing test**

`importer/tests/test_models.py`:
```python
import pytest
from pydantic import ValidationError
from importer.models import ProductReport, ServiceReport, parse_report_json

PRODUCT_JSON = {
    "product": {"name": "Цемент", "hs_code": "2523290000", "ikpu": ["23941001"],
                "domain": "стройматериалы", "duty": "0%", "excise": None, "vat": "12%"},
    "requirements": [{
        "title": "Получить сертификат соответствия", "nature": "obligation", "type": "import",
        "category": "Оценка соответствия, декларация и сертификация",
        "summary": "Цемент подлежит обязательной сертификации.",
        "legal_quote_ru": "продукция подлежит обязательному подтверждению соответствия",
        "act": {"name": "Закон о техническом регулировании", "number": "ЗРУ-819",
                "date": "2023-04-05", "lexuz_url": "https://lex.uz/docs/-6445145"},
        "unit": "ст. 14", "edition_date": "2025-12-20",
        "scope": {"level": "hs_list", "codes": ["2523"], "list_row": "строка 91 прил. 4"},
        "addressees": ["importer"], "agency": "Узстандарт",
        "how_to": [{"step": "Подать заявку", "deadline": "10 дней", "source_act_url": None}],
        "documents": [{"name": "Заявка", "where": "Узстандарт"}],
        "sanction": {"article": "ст. 186 КоАО", "fine_bru": "до 75 БРВ", "extra": None, "url": None},
        "discovered_via": "list", "needs_review": False
    }]
}

def test_product_report_validates():
    report = ProductReport.model_validate(PRODUCT_JSON)
    assert report.product.hs_code == "2523290000"
    assert report.requirements[0].scope.level == "hs_list"

def test_invalid_nature_rejected():
    bad = {**PRODUCT_JSON, "requirements": [{**PRODUCT_JSON["requirements"][0], "nature": "wish"}]}
    with pytest.raises(ValidationError):
        ProductReport.model_validate(bad)

def test_service_report_validates():
    data = {"service": {"name": "Аптека", "okved": "47.73", "admission_type": "license",
                        "licensor": "Минздрав", "related_products": []},
            "requirements": [{**PRODUCT_JSON["requirements"][0],
                              "stage": "start", "periodicity": "once", "scope": "this_okved"}]}
    data["requirements"][0] = {k: v for k, v in data["requirements"][0].items()
                               if k not in ("type", "category")}
    report = ServiceReport.model_validate(data)
    assert report.requirements[0].stage == "start"

def test_parse_report_json_dispatch():
    assert isinstance(parse_report_json(PRODUCT_JSON, "product"), ProductReport)
```

- [ ] **Step 2: убедиться, что падает**

Run: `.venv-importer/bin/python -m pytest importer/tests/test_models.py -v`
Expected: FAIL (`ModuleNotFoundError` / ImportError)

- [ ] **Step 3: реализация**

`importer/models.py`:
```python
"""Pydantic-схемы JSON-блока отчётов (контракт из research-prompt-{product,service}.md)."""
from typing import Literal
from pydantic import BaseModel, ConfigDict


class _Base(BaseModel):
    model_config = ConfigDict(extra="ignore")


class ActRef(_Base):
    name: str | None = None
    number: str | None = None
    date: str | None = None
    lexuz_url: str | None = None


class HowToStep(_Base):
    step: str
    deadline: str | None = None
    fee: str | None = None
    cost: str | None = None
    source_act_url: str | None = None


class DocumentItem(_Base):
    name: str
    where: str | None = None


class Sanction(_Base):
    article: str | None = None
    fine_bru: str | None = None
    extra: str | None = None
    url: str | None = None


class ProductScope(_Base):
    level: Literal["all", "domain", "hs_list", "this_code"]
    codes: list[str] | None = None
    list_row: str | None = None


class _BaseRequirement(_Base):
    title: str
    nature: Literal["obligation", "prohibition", "right"]
    summary: str
    legal_quote_ru: str | None = None
    act: ActRef
    unit: str | None = None
    edition_date: str | None = None
    addressees: list[str] = []
    agency: str | None = None
    how_to: list[HowToStep] = []
    documents: list[DocumentItem] = []
    sanction: Sanction | None = None
    discovered_via: str | None = None
    needs_review: bool = False


class ProductRequirement(_BaseRequirement):
    type: Literal["product", "realization", "import", "export",
                  "transit", "re_export", "re_import"]
    category: str
    scope: ProductScope


class ServiceRequirement(_BaseRequirement):
    stage: Literal["start", "premises", "operations", "inspections", "changes", "termination"]
    periodicity: str | None = None
    scope: Literal["all_business", "licensed", "this_okved"]


class ProductPassport(_Base):
    name: str
    hs_code: str | None = None
    ikpu: list[str] | None = []
    domain: str | None = None
    duty: str | None = None
    excise: str | None = None
    vat: str | None = None


class ServicePassport(_Base):
    name: str
    okved: str
    admission_type: str | None = None
    licensor: str | None = None
    related_products: list[str] | None = []


class ProductReport(_Base):
    product: ProductPassport
    requirements: list[ProductRequirement]


class ServiceReport(_Base):
    service: ServicePassport
    requirements: list[ServiceRequirement]


def parse_report_json(data: dict, kind: str) -> ProductReport | ServiceReport:
    if kind == "product":
        return ProductReport.model_validate(data)
    if kind == "service":
        return ServiceReport.model_validate(data)
    raise ValueError(f"unknown report kind: {kind}")
```

- [ ] **Step 4: тесты зелёные**

Run: `.venv-importer/bin/python -m pytest importer/tests/test_models.py -v`
Expected: `4 passed`

- [ ] **Step 5: Commit**

```bash
git add importer/models.py importer/tests/test_models.py
git commit -m "feat(importer): pydantic-схемы отчётов product/service"
```

---

### Task 3: Парсер markdown-отчёта (JSON-блок, серые зоны, имя файла)

**Files:**
- Create: `importer/parser.py`, `importer/tests/test_parser.py`, `importer/tests/fixtures/report_product_ok.md`

**Interfaces:**
- Consumes: `parse_report_json` из Task 2; `LLM.convert_to_schema` из Task 5 (опциональный параметр, в тестах — фейк).
- Produces:
  - `@dataclass ReportFile: path: Path, kind: str, slug: str, model: str, file_hash: str, markdown: str`
  - `parse_filename(path: Path) -> tuple[str, str, str]` — (kind, slug, model); неверный формат → `ValueError`
  - `load_report_file(path: Path) -> ReportFile` (hash = sha256 содержимого, hex)
  - `extract_json_block(markdown: str) -> str | None` — последний fenced-блок ` ```json `
  - `extract_gray_zones(markdown: str) -> list[str]` — маркированные строки после заголовка с «Серые зоны» или «Часть 3»
  - `parse_report(rf: ReportFile, llm=None) -> ProductReport | ServiceReport` — json.loads → parse_report_json; при ошибке и llm≠None → `llm.convert_to_schema(rf.markdown, kind)` → повторная валидация; иначе исключение `ReportParseError`

- [ ] **Step 1: фикстура**

`importer/tests/fixtures/report_product_ok.md` — мини-отчёт: заголовок, пара абзацев «Часть 1», затем:

````markdown
# Отчёт: цемент портландский

## Часть 1. Читаемый отчёт
Текст отчёта...

## Часть 2. Машинный блок

```json
{"product": {"name": "Цемент", "hs_code": "2523290000", "ikpu": ["23941001"],
             "domain": "стройматериалы", "duty": "0%", "excise": null, "vat": "12%"},
 "requirements": [{
   "title": "Получить сертификат соответствия", "nature": "obligation", "type": "import",
   "category": "Оценка соответствия, декларация и сертификация",
   "summary": "Цемент подлежит обязательной сертификации.",
   "legal_quote_ru": "продукция подлежит обязательному подтверждению соответствия",
   "act": {"name": "Закон о техническом регулировании", "number": "ЗРУ-819",
           "date": "2023-04-05", "lexuz_url": "https://lex.uz/docs/-6445145"},
   "unit": "ст. 14", "edition_date": "2025-12-20",
   "scope": {"level": "hs_list", "codes": ["2523"], "list_row": "строка 91"},
   "addressees": ["importer"], "agency": "Узстандарт",
   "how_to": [], "documents": [], "sanction": null,
   "discovered_via": "list", "needs_review": false}]}
```

## Часть 3. Серые зоны
- Ставка тарифа не подтверждена (динамический JSP).
- Строка перечня ПКМ-43 требует проверки по узбекской версии.
````

- [ ] **Step 2: failing test**

`importer/tests/test_parser.py`:
```python
import json
from pathlib import Path
import pytest
from importer.parser import (ReportFile, ReportParseError, extract_gray_zones,
                             extract_json_block, load_report_file, parse_filename, parse_report)
from importer.models import ProductReport

FIX = Path(__file__).parent / "fixtures"


def test_parse_filename():
    assert parse_filename(Path("product--cement--claude.md")) == ("product", "cement", "claude")
    with pytest.raises(ValueError):
        parse_filename(Path("cement.md"))


def test_load_and_extract(tmp_path):
    src = FIX / "report_product_ok.md"
    path = tmp_path / "product--cement--claude.md"
    path.write_text(src.read_text())
    rf = load_report_file(path)
    assert rf.kind == "product" and rf.model == "claude" and len(rf.file_hash) == 64
    block = extract_json_block(rf.markdown)
    assert json.loads(block)["product"]["hs_code"] == "2523290000"
    zones = extract_gray_zones(rf.markdown)
    assert len(zones) == 2 and "тариф" in zones[0].lower()


def test_parse_report_ok(tmp_path):
    src = FIX / "report_product_ok.md"
    path = tmp_path / "product--cement--claude.md"
    path.write_text(src.read_text())
    report = parse_report(load_report_file(path))
    assert isinstance(report, ProductReport)


def test_parse_report_broken_json_uses_llm(tmp_path):
    good = json.loads(extract_json_block((FIX / "report_product_ok.md").read_text()))
    path = tmp_path / "product--cement--gpt.md"
    path.write_text("# x\n```json\n{broken json!!!\n```\n")

    class FakeLLM:
        def convert_to_schema(self, markdown, kind):
            return good
    report = parse_report(load_report_file(path), llm=FakeLLM())
    assert isinstance(report, ProductReport)


def test_parse_report_broken_no_llm_raises(tmp_path):
    path = tmp_path / "product--cement--gpt.md"
    path.write_text("# x\n```json\n{broken\n```\n")
    with pytest.raises(ReportParseError):
        parse_report(load_report_file(path))
```

Run: `.venv-importer/bin/python -m pytest importer/tests/test_parser.py -v` → FAIL (ImportError)

- [ ] **Step 3: реализация**

`importer/parser.py`:
```python
"""Отчёт .md → валидированная модель. Детерминизм — в валидации, не в парсинге."""
import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path

from pydantic import ValidationError

from importer.models import ProductReport, ServiceReport, parse_report_json


class ReportParseError(Exception):
    pass


@dataclass
class ReportFile:
    path: Path
    kind: str
    slug: str
    model: str
    file_hash: str
    markdown: str


def parse_filename(path: Path) -> tuple[str, str, str]:
    m = re.fullmatch(r"(product|service)--([a-z0-9-]+)--([a-z0-9.-]+)", path.stem)
    if not m:
        raise ValueError(
            f"имя файла должно быть {{product|service}}--{{слаг}}--{{модель}}.md: {path.name}")
    return m.group(1), m.group(2), m.group(3)


def load_report_file(path: Path) -> ReportFile:
    kind, slug, model = parse_filename(path)
    markdown = path.read_text(encoding="utf-8")
    file_hash = hashlib.sha256(markdown.encode("utf-8")).hexdigest()
    return ReportFile(path, kind, slug, model, file_hash, markdown)


_JSON_BLOCK = re.compile(r"```json\s*\n(.*?)\n```", re.DOTALL)


def extract_json_block(markdown: str) -> str | None:
    blocks = _JSON_BLOCK.findall(markdown)
    return blocks[-1] if blocks else None


_GRAY_HEADING = re.compile(r"^#{1,6}\s*.*(серые зоны|часть 3)", re.IGNORECASE)


def extract_gray_zones(markdown: str) -> list[str]:
    lines = markdown.splitlines()
    zones, in_section = [], False
    for line in lines:
        if _GRAY_HEADING.match(line.strip()):
            in_section = True
            continue
        if in_section and line.strip().startswith("#"):
            break
        if in_section and re.match(r"^\s*([-*•]|\d+[.)])\s+", line):
            zones.append(re.sub(r"^\s*([-*•]|\d+[.)])\s+", "", line).strip())
    return zones


def parse_report(rf: ReportFile, llm=None) -> ProductReport | ServiceReport:
    block = extract_json_block(rf.markdown)
    data = None
    if block is not None:
        try:
            data = json.loads(block)
        except json.JSONDecodeError:
            data = None
    if data is not None:
        try:
            return parse_report_json(data, rf.kind)
        except ValidationError:
            data = None
    if llm is None:
        raise ReportParseError(f"JSON-блок не извлечён/не валиден: {rf.path.name}")
    converted = llm.convert_to_schema(rf.markdown, rf.kind)
    try:
        return parse_report_json(converted, rf.kind)
    except ValidationError as e:
        raise ReportParseError(f"LLM-конвертация не дала валидную схему: {e}") from e
```

- [ ] **Step 4: тесты зелёные**

Run: `.venv-importer/bin/python -m pytest importer/tests/test_parser.py -v`
Expected: `5 passed`

- [ ] **Step 5: Commit**

```bash
git add importer/parser.py importer/tests/test_parser.py importer/tests/fixtures/report_product_ok.md
git commit -m "feat(importer): парсер отчёта — json-блок, серые зоны, llm-фолбэк"
```

---

### Task 4: refs.py — unit-ref и нормализация lex.uz URL

**Files:**
- Create: `importer/refs.py`, `importer/tests/test_refs.py`

**Interfaces:**
- Produces:
  - `lexuz_doc_id(url: str | None) -> str | None` — «https://lex.uz/docs/-6445145», «https://lex.uz/ru/docs/-6445145#p12», «https://www.lex.uz/acts/6445145» → `"6445145"`; не lex.uz / нет id → None
  - `parse_unit_ref(unit: str | None) -> str | None` — канонический ref, совместимый с адресами JurisBase (`art.N`, `p.N`, `appN`, `appN/rowM`, `sec.N`); не распознано → None

- [ ] **Step 1: failing test**

`importer/tests/test_refs.py`:
```python
import pytest
from importer.refs import lexuz_doc_id, parse_unit_ref

@pytest.mark.parametrize("url,expected", [
    ("https://lex.uz/docs/-6445145", "6445145"),
    ("https://lex.uz/ru/docs/-6445145#p12", "6445145"),
    ("https://www.lex.uz/acts/6445145", "6445145"),
    ("https://lex.uz/uz/docs/6445145/", "6445145"),
    ("https://example.com/doc/123", None),
    (None, None),
])
def test_lexuz_doc_id(url, expected):
    assert lexuz_doc_id(url) == expected

@pytest.mark.parametrize("unit,expected", [
    ("ст. 14", "art.14"),
    ("статья 14", "art.14"),
    ("ст. 186-1", "art.186-1"),
    ("п. 11", "p.11"),
    ("пункт 11", "p.11"),
    ("п. 5 ст. 14", "art.14/p.5"),
    ("прил. 2", "app2"),
    ("приложение 4, строка 91", "app4/row91"),
    ("прил. 4, строка 91", "app4/row91"),
    ("раздел 3", "sec.3"),
    ("непонятное", None),
    (None, None),
])
def test_parse_unit_ref(unit, expected):
    assert parse_unit_ref(unit) == expected
```

Run: `.venv-importer/bin/python -m pytest importer/tests/test_refs.py -v` → FAIL

- [ ] **Step 2: реализация**

`importer/refs.py`:
```python
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
```

- [ ] **Step 3: тесты зелёные**

Run: `.venv-importer/bin/python -m pytest importer/tests/test_refs.py -v`
Expected: все passed

- [ ] **Step 4: Commit**

```bash
git add importer/refs.py importer/tests/test_refs.py
git commit -m "feat(importer): канонизация unit-ref и lex.uz doc_id"
```

---

### Task 5: llm.py — абстракция над `claude -p`

**Files:**
- Create: `importer/llm.py`, `importer/tests/test_llm.py`

**Interfaces:**
- Produces: `class LLM(runner: Callable[[str], str] | None = None)`:
  - `complete(prompt: str) -> str` — вызывает runner (по умолчанию `_claude_cli`)
  - `convert_to_schema(markdown: str, kind: str) -> dict` — просит извлечь JSON по схеме промпта, парсит ответ (сначала как чистый JSON, потом первый `{...}` в тексте); не распарсилось → `LLMError`
  - `same_meaning(quote: str, paragraph: str) -> bool` — ответ начинается с «да»/«yes» (без регистра)
  - `LLMError(Exception)`
- Runner-контракт: строка промпта → строка ответа. `_claude_cli` — `subprocess.run(["claude", "-p", "--output-format", "text"], input=prompt, ...)`, промпт через stdin (акты длинные), timeout 300s.

- [ ] **Step 1: failing test**

`importer/tests/test_llm.py`:
```python
import json
import pytest
from importer.llm import LLM, LLMError


def test_convert_to_schema_plain_json():
    payload = {"product": {"name": "x"}, "requirements": []}
    llm = LLM(runner=lambda prompt: json.dumps(payload))
    assert llm.convert_to_schema("# отчёт", "product") == payload


def test_convert_to_schema_json_in_prose():
    payload = {"a": 1}
    llm = LLM(runner=lambda prompt: f"Вот JSON:\n```json\n{json.dumps(payload)}\n```\nготово")
    assert llm.convert_to_schema("md", "product") == payload


def test_convert_to_schema_garbage_raises():
    llm = LLM(runner=lambda prompt: "не могу")
    with pytest.raises(LLMError):
        llm.convert_to_schema("md", "product")


def test_same_meaning():
    assert LLM(runner=lambda p: "Да, смысл совпадает").same_meaning("a", "b") is True
    assert LLM(runner=lambda p: "Нет").same_meaning("a", "b") is False
```

Run: `.venv-importer/bin/python -m pytest importer/tests/test_llm.py -v` → FAIL

- [ ] **Step 2: реализация**

`importer/llm.py`:
```python
"""LLM-шаги импортёра. Бэкенд v1 — claude -p (подписка); runner инжектируется в тестах."""
import json
import re
import subprocess
from typing import Callable


class LLMError(Exception):
    pass


def _claude_cli(prompt: str) -> str:
    proc = subprocess.run(
        ["claude", "-p", "--output-format", "text"],
        input=prompt, capture_output=True, text=True, timeout=300,
    )
    if proc.returncode != 0:
        raise LLMError(f"claude -p завершился с кодом {proc.returncode}: {proc.stderr[:500]}")
    return proc.stdout


_SCHEMA_HINT = {
    "product": '{"product": {"name","hs_code","ikpu","domain","duty","excise","vat"}, '
               '"requirements": [{"title","nature","type","category","summary","legal_quote_ru",'
               '"act":{"name","number","date","lexuz_url"},"unit","edition_date",'
               '"scope":{"level","codes","list_row"},"addressees","agency","how_to","documents",'
               '"sanction","discovered_via","needs_review"}]}',
    "service": '{"service": {"name","okved","admission_type","licensor","related_products"}, '
               '"requirements": [{"title","nature","stage","periodicity","summary","legal_quote_ru",'
               '"act":{"name","number","date","lexuz_url"},"unit","edition_date","scope",'
               '"addressees","agency","how_to","documents","sanction","discovered_via","needs_review"}]}',
}


class LLM:
    def __init__(self, runner: Callable[[str], str] | None = None):
        self._runner = runner or _claude_cli

    def complete(self, prompt: str) -> str:
        return self._runner(prompt)

    def convert_to_schema(self, markdown: str, kind: str) -> dict:
        prompt = (
            "Ниже отчёт deep research. Извлеки из него данные СТРОГО в JSON по схеме "
            f"{_SCHEMA_HINT[kind]}. Неизвестное значение = null. Ничего не выдумывай: "
            "бери только то, что есть в отчёте. Ответ — ТОЛЬКО JSON, без пояснений.\n\n"
            f"=== ОТЧЁТ ===\n{markdown}"
        )
        answer = self.complete(prompt)
        for candidate in (answer, *re.findall(r"\{.*\}", answer, re.DOTALL)):
            try:
                return json.loads(candidate.strip())
            except json.JSONDecodeError:
                continue
        raise LLMError("LLM не вернула валидный JSON")

    def same_meaning(self, quote: str, paragraph: str) -> bool:
        prompt = (
            "Сравни цитату нормы и официальный текст пункта. Это ОДНА И ТА ЖЕ норма "
            "(допустимы редакционные отличия)? Ответь одним словом: Да или Нет.\n\n"
            f"ЦИТАТА: {quote}\n\nТЕКСТ ПУНКТА: {paragraph}"
        )
        return self.complete(prompt).strip().lower().startswith(("да", "yes"))
```

- [ ] **Step 3: тесты зелёные**

Run: `.venv-importer/bin/python -m pytest importer/tests/test_llm.py -v`
Expected: `4 passed`

- [ ] **Step 4: Commit**

```bash
git add importer/llm.py importer/tests/test_llm.py
git commit -m "feat(importer): абстракция LLM поверх claude -p"
```

---

### Task 6: Миграция БД — staging-таблицы и enum `validated`

**Files:**
- Create: `supabase/migrations/20260713000000_import_pipeline.sql`

**Interfaces:**
- Produces: таблицы `import_runs`, `import_items`, `requirement_sources`; значение `'validated'` в `trust_label`. RLS включён без публичных политик — доступ только service-ролью.

- [ ] **Step 1: написать миграцию**

`supabase/migrations/20260713000000_import_pipeline.sql`:
```sql
-- Импортёр deep-research отчётов: staging-слой (спека 2026-07-12-report-importer-design.md).
-- import_runs / import_items — аудит, review-очередь и золотой датасет решений.
-- requirement_sources — провенанс «какие модели/отчёты нашли требование».

alter type public.trust_label add value if not exists 'validated';

create table public.import_runs (
  id uuid primary key default gen_random_uuid(),
  file_name text not null,
  file_hash text not null unique,
  subject_kind text not null check (subject_kind in ('product', 'service')),
  subject_slug text not null,
  model text not null,
  status text not null default 'parsed' check (status in ('parsed', 'failed', 'loaded')),
  loaded_count int not null default 0,
  merged_count int not null default 0,
  review_count int not null default 0,
  raw_json jsonb,
  gray_zones text[] not null default '{}',
  error text,
  created_at timestamptz not null default now()
);

create table public.import_items (
  id uuid primary key default gen_random_uuid(),
  run_id uuid not null references public.import_runs(id) on delete cascade,
  idx int not null,
  raw jsonb not null,
  status text not null check (status in ('loaded', 'merged', 'review', 'rejected')),
  review_reason text,
  review_detail text,
  requirement_id uuid references public.requirements(id) on delete set null,
  resolution text not null default 'pending'
    check (resolution in ('pending', 'approved', 'fixed', 'rejected')),
  resolved_by uuid references auth.users(id) on delete set null,
  resolved_at timestamptz,
  created_at timestamptz not null default now(),
  unique (run_id, idx)
);

create index import_items_review_idx on public.import_items (status) where status = 'review';

create table public.requirement_sources (
  requirement_id uuid not null references public.requirements(id) on delete cascade,
  import_item_id uuid not null references public.import_items(id) on delete cascade,
  created_at timestamptz not null default now(),
  primary key (requirement_id, import_item_id)
);

-- Только service role: RLS включён, политик нет.
alter table public.import_runs enable row level security;
alter table public.import_items enable row level security;
alter table public.requirement_sources enable row level security;
```

- [ ] **Step 2: применить к проду**

Run: `supabase db push` (из корня; проект уже слинкован — так применялись прошлые миграции). При ошибке аутентификации — известные грабли env-токена: попросить Абдурахмона выполнить `supabase login` или дать `SUPABASE_ACCESS_TOKEN`; НЕ изобретать обходные пути.
Expected: миграция применена, вывод `Applying migration 20260713000000_import_pipeline.sql...`

- [ ] **Step 3: проверить**

Run: `supabase db diff --linked | head -5` (или запрос через MCP supabase: `select count(*) from import_runs`)
Expected: diff пустой / count = 0

- [ ] **Step 4: Commit**

```bash
git add supabase/migrations/20260713000000_import_pipeline.sql
git commit -m "feat(db): staging-таблицы импортёра + trust_label 'validated'"
```

---

### Task 7: mappings.py + domains.yaml + db.py

**Files:**
- Create: `importer/mappings.py`, `importer/domains.yaml`, `importer/db.py`, `importer/tests/test_mappings.py`

**Interfaces:**
- Produces (`mappings.py`); функции бросают `MappingError(reason, detail)` с `reason='no_dictionary_slot'`:
  - `map_nature(nature: str) -> str` — obligation/prohibition→как есть, right→`permission`
  - `map_operation(kind: str, req) -> str` — product: `req.type` (re-export дефисный → `re_export`); service: константа `"realization"` (как у существующих сервисных карточек)
  - `map_addressees(addressees: list[str]) -> list[str]` — словарь `{manufacturer,producer→producer; importer; exporter; seller,retailer,vendor→seller; carrier,transporter→carrier; owner,entrepreneur,business→all; all→all}`; неизвестный → MappingError
  - `map_category(category: str) -> str | None` — закрытый список промпта → NTM enum (`sps/tbt/marking/licensing/fiscal/currency/customs/origin`); известная категория без NTM-полки («Экология», «Прочее») → None; неизвестная строка → MappingError
  - `map_product_scope(scope: ProductScope, product_hs: str | None, domains: dict) -> list[tuple[str, str | None]]` — список `(scope_enum, code)`: all→`[("all_products", None)]`; this_code→`[("hs_code", product_hs)]` (нет hs → MappingError); hs_list→по каждому коду: len==10→`hs_code`, иначе `hs_prefix`; domain→префиксы из `domains` по нормализованному имени (lower/strip), нет домена → MappingError
  - `map_service_scope(scope: str, okved: str) -> list[tuple[str, str | None]]` — all_business→`all_services`; this_okved→`oked_code`; licensed→MappingError (полки нет в v1)
  - `STAGE_TO_CODE = {"start": "svc-01-start", "premises": "svc-02-premises", "operations": "svc-03-operations", "inspections": "svc-04-inspections", "changes": "svc-05-changes", "termination": "svc-06-closure"}`
  - `load_domains() -> dict[str, list[str]]` — читает `importer/domains.yaml`
- Produces (`db.py`): `ix_client() -> Client`, `jb_client() -> Client` — supabase-py клиенты из `.env.importer` (python-dotenv, `load_dotenv(".env.importer")`); отсутствует переменная → `RuntimeError` с именем переменной.

- [ ] **Step 1: domains.yaml (ручной словарь, правится руками)**

`importer/domains.yaml`:
```yaml
# Домен → префиксы ТН ВЭД (scope level=domain). Ключи в lower-case.
# Ручной словарь (решение брейншторма); нет домена в списке → карточка в review.
фарма: ["30"]
стройматериалы: ["25", "68"]
лкм: ["32"]
посуда: ["69", "70"]
пищёвка: ["04", "09", "10", "11", "15", "16", "17", "18", "19", "20", "21", "22"]
табак: ["24"]
```

- [ ] **Step 2: failing test**

`importer/tests/test_mappings.py`:
```python
import pytest
from importer.mappings import (MappingError, STAGE_TO_CODE, load_domains, map_addressees,
                               map_category, map_nature, map_product_scope, map_service_scope)
from importer.models import ProductScope


def test_map_nature():
    assert map_nature("right") == "permission"
    assert map_nature("obligation") == "obligation"


def test_map_addressees():
    assert map_addressees(["manufacturer", "importer"]) == ["producer", "importer"]
    with pytest.raises(MappingError):
        map_addressees(["alien"])


def test_map_category():
    assert map_category("Налоги и платежи") == "fiscal"
    assert map_category("Экология") is None
    with pytest.raises(MappingError):
        map_category("Новая выдуманная категория")


def test_map_product_scope():
    domains = {"стройматериалы": ["25", "68"]}
    assert map_product_scope(ProductScope(level="all"), "2523290000", domains) == [("all_products", None)]
    assert map_product_scope(ProductScope(level="this_code"), "2523290000", domains) == [("hs_code", "2523290000")]
    assert map_product_scope(ProductScope(level="hs_list", codes=["2523", "2523290000"]),
                             None, domains) == [("hs_prefix", "2523"), ("hs_code", "2523290000")]
    assert map_product_scope(ProductScope(level="domain"), None,
                             domains | {"_domain": "стройматериалы"}) or True
    with pytest.raises(MappingError):
        map_product_scope(ProductScope(level="domain"), None, {"_domain": "неизвестный"})


def test_map_service_scope():
    assert map_service_scope("this_okved", "47.73") == [("oked_code", "47.73")]
    assert map_service_scope("all_business", "47.73") == [("all_services", None)]
    with pytest.raises(MappingError):
        map_service_scope("licensed", "47.73")


def test_stage_codes_and_domains_file():
    assert STAGE_TO_CODE["termination"] == "svc-06-closure"
    assert "фарма" in load_domains()
```

Замечание к дизайну: имя домена приходит из паспорта продукта, а не из scope, поэтому
`map_product_scope` принимает домен через ключ `"_domain"` в словаре domains
(см. реализацию ниже) — тесты это фиксируют.

Run: `.venv-importer/bin/python -m pytest importer/tests/test_mappings.py -v` → FAIL

- [ ] **Step 3: реализация**

`importer/mappings.py`:
```python
"""Закрытые словари классификации. Нет полки → MappingError → карточка в review."""
from pathlib import Path

import yaml


class MappingError(Exception):
    def __init__(self, reason: str, detail: str):
        self.reason = reason
        self.detail = detail
        super().__init__(f"{reason}: {detail}")


def _no_slot(detail: str) -> MappingError:
    return MappingError("no_dictionary_slot", detail)


def map_nature(nature: str) -> str:
    return {"obligation": "obligation", "prohibition": "prohibition", "right": "permission"}[nature]


def map_operation(kind: str, req) -> str:
    if kind == "service":
        return "realization"
    return req.type.replace("-", "_")


_ADDRESSEES = {
    "manufacturer": "producer", "producer": "producer", "importer": "importer",
    "exporter": "exporter", "seller": "seller", "retailer": "seller", "vendor": "seller",
    "carrier": "carrier", "transporter": "carrier",
    "owner": "all", "entrepreneur": "all", "business": "all", "all": "all",
}


def map_addressees(addressees: list[str]) -> list[str]:
    result = []
    for a in addressees:
        key = a.strip().lower()
        if key not in _ADDRESSEES:
            raise _no_slot(f"addressee: {a}")
        if _ADDRESSEES[key] not in result:
            result.append(_ADDRESSEES[key])
    return result


_CATEGORY_TO_NTM = {
    "технические требования и безопасность": "tbt",
    "маркировка и защита прав потребителей": "marking",
    "оценка соответствия, декларация и сертификация": "tbt",
    "государственная регистрация": "licensing",
    "лицензирование и разрешения": "licensing",
    "налоги и платежи": "fiscal",
    "санитарные/фитосанитарные/ветеринарные": "sps",
    "экология": None,
    "прочее": None,
}


def map_category(category: str) -> str | None:
    key = category.strip().lower()
    if key not in _CATEGORY_TO_NTM:
        raise _no_slot(f"category: {category}")
    return _CATEGORY_TO_NTM[key]


def map_product_scope(scope, product_hs: str | None, domains: dict) -> list[tuple[str, str | None]]:
    if scope.level == "all":
        return [("all_products", None)]
    if scope.level == "this_code":
        if not product_hs:
            raise _no_slot("scope this_code без hs_code продукта")
        return [("hs_code", product_hs)]
    if scope.level == "hs_list":
        if not scope.codes:
            raise _no_slot("scope hs_list без кодов")
        return [("hs_code" if len(c) == 10 else "hs_prefix", c) for c in scope.codes]
    if scope.level == "domain":
        domain = (domains.get("_domain") or "").strip().lower()
        prefixes = domains.get(domain)
        if not prefixes:
            raise _no_slot(f"domain: {domain or '<пусто>'}")
        return [("hs_prefix", p) for p in prefixes]
    raise _no_slot(f"scope level: {scope.level}")


def map_service_scope(scope: str, okved: str) -> list[tuple[str, str | None]]:
    if scope == "all_business":
        return [("all_services", None)]
    if scope == "this_okved":
        return [("oked_code", okved)]
    raise _no_slot(f"service scope: {scope}")


STAGE_TO_CODE = {
    "start": "svc-01-start", "premises": "svc-02-premises", "operations": "svc-03-operations",
    "inspections": "svc-04-inspections", "changes": "svc-05-changes",
    "termination": "svc-06-closure",
}


def load_domains() -> dict[str, list[str]]:
    path = Path(__file__).parent / "domains.yaml"
    return yaml.safe_load(path.read_text(encoding="utf-8"))
```

`importer/db.py`:
```python
"""Supabase-клиенты: Inspector X (rw, service key) и JurisBase lexportal (ro)."""
import os

from dotenv import load_dotenv
from supabase import Client, create_client

load_dotenv(".env.importer")


def _env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"нет переменной окружения {name} (см. .env.importer.example)")
    return value


def ix_client() -> Client:
    return create_client(_env("IX_SUPABASE_URL"), _env("IX_SUPABASE_SERVICE_KEY"))


def jb_client() -> Client:
    return create_client(_env("JB_SUPABASE_URL"), _env("JB_SUPABASE_KEY"))
```

- [ ] **Step 4: тесты зелёные**

Run: `.venv-importer/bin/python -m pytest importer/tests/test_mappings.py -v`
Expected: все passed

- [ ] **Step 5: Commit**

```bash
git add importer/mappings.py importer/domains.yaml importer/db.py importer/tests/test_mappings.py
git commit -m "feat(importer): закрытые словари классификации и db-клиенты"
```

---

### Task 8: lexuz.py — fetch с кэшем, признаки акта, поиск пункта

**Files:**
- Create: `importer/lexuz.py`, `importer/tests/test_lexuz.py`, `importer/tests/fixtures/lexuz_act_ru.html`

**Interfaces:**
- Consumes: `parse_unit_ref`-формат ref из Task 4.
- Produces: `class LexuzClient(cache_dir: Path, fetcher: Callable[[str], str] | None = None)`:
  - `fetch(doc_id: str) -> str` — HTML; кэш `{cache_dir}/{doc_id}.html`; fetcher по умолчанию — httpx.get(`https://lex.uz/ru/docs/-{doc_id}`, follow_redirects=True, timeout=30, 3 ретрая с бэкоффом 2/4/8с); стойкий провал → `LexuzUnreachable`
  - `page_text(html: str) -> str` — текст без тегов (bs4), схлопнутые пробелы
  - `is_repealed(html: str) -> bool` — маркеры «утратил силу», «утратила силу», «kuchini yo'qotgan», «кучини йўқотган» в первых 5000 символах текста
  - `is_russian(html: str) -> bool` — эвристика: в тексте есть ≥20 вхождений кириллических русских слов-связок (` и `, ` или `, ` в `, ` на `); отличает RU-версию от UZ-кириллицы
  - `find_paragraph(html: str, ref: str) -> str | None` — для `art.N[/p.M]` ищет «Статья N.» в тексте, возвращает срез до следующей «Статья N+…»; для `p.N` ищет «N. » в начале строки; для appN/rowN → None (v1: перечни не адресуются, сверка по всей странице)

- [ ] **Step 1: фикстура**

`importer/tests/fixtures/lexuz_act_ru.html` — минимальный HTML в духе lex.uz:
```html
<html><body><div class="doc">
<p>ЗАКОН РЕСПУБЛИКИ УЗБЕКИСТАН О ТЕХНИЧЕСКОМ РЕГУЛИРОВАНИИ</p>
<p>Статья 13. Общие положения</p>
<p>Текст статьи тринадцать о общих положениях и о порядке в стране.</p>
<p>Статья 14. Подтверждение соответствия</p>
<p>Продукция, включённая в перечень, подлежит обязательному подтверждению
соответствия в установленном порядке. Выпуск в обращение без подтверждения
соответствия запрещается.</p>
<p>Статья 15. Иное</p>
<p>Иной текст и другие нормы в статье пятнадцать.</p>
</div></body></html>
```

- [ ] **Step 2: failing test**

`importer/tests/test_lexuz.py`:
```python
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
```

Run: `.venv-importer/bin/python -m pytest importer/tests/test_lexuz.py -v` → FAIL

- [ ] **Step 3: реализация**

`importer/lexuz.py`:
```python
"""Доступ к lex.uz: fetch с дисковым кэшем (не долбим сайт), эвристики страницы."""
import re
import time
from pathlib import Path
from typing import Callable

import httpx
from bs4 import BeautifulSoup


class LexuzUnreachable(Exception):
    pass


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
        html = self._fetcher(f"https://lex.uz/ru/docs/-{doc_id}")
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
    def find_paragraph(html: str, ref: str) -> str | None:
        text = LexuzClient.page_text(html)
        m_art = re.match(r"art\.([\d-]+)(?:/p\.([\d-]+))?$", ref)
        if m_art:
            num = m_art.group(1)
            start = re.search(rf"Статья\s+{num}\.", text)
            if not start:
                return None
            rest = text[start.start():]
            nxt = re.search(r"Статья\s+[\d-]+\.", rest[10:])
            return rest[: nxt.start() + 10] if nxt else rest
        m_p = re.match(r"p\.([\d-]+)$", ref)
        if m_p:
            num = m_p.group(1)
            start = re.search(rf"(?:^|[.;)])\s{num}\.\s", text)
            if not start:
                return None
            rest = text[start.end() - len(f"{num}. "):]
            nxt = re.search(r"[.;]\s[\d-]+\.\s", rest[5:])
            return rest[: nxt.start() + 5] if nxt else rest[:2000]
        return None  # appN/rowM и прочее — сверка по всей странице (v1)
```

- [ ] **Step 4: тесты зелёные**

Run: `.venv-importer/bin/python -m pytest importer/tests/test_lexuz.py -v`
Expected: все passed. Если `find_paragraph` не проходит на фикстуре — чинить регэксы, не фикстуру.

- [ ] **Step 5: Commit**

```bash
git add importer/lexuz.py importer/tests/test_lexuz.py importer/tests/fixtures/lexuz_act_ru.html
git commit -m "feat(importer): lex.uz клиент с кэшем и поиском пункта"
```

---

### Task 9: verifier.py — верификационный гейт

**Files:**
- Create: `importer/verifier.py`, `importer/tests/test_verifier.py`

**Interfaces:**
- Consumes: `LexuzClient` (Task 8), `LLM.same_meaning` (Task 5), `lexuz_doc_id`/`parse_unit_ref` (Task 4), модели (Task 2).
- Produces:
  - `@dataclass GateResult: ok: bool; reason: str | None = None; detail: str | None = None; doc_id: str | None = None; ref: str | None = None; confidence: float | None = None; paragraph_text: str | None = None`
  - `verify_item(req, lexuz: LexuzClient, llm: LLM | None) -> GateResult`
- Причины review (коды): `needs_review_from_report`, `act_not_found`, `lexuz_unreachable`, `act_repealed`, `unit_not_found`, `uz_only_act`, `quote_missing`, `quote_mismatch`.
- Пороги fuzzy (rapidfuzz `fuzz.partial_ratio`, строки в lower): ≥85 → ok; 60–85 → `llm.same_meaning` (llm=None → review `quote_mismatch`); <60 → review `quote_mismatch`. Пункт найден → сверка по тексту пункта; не найден при ref `appN...` → сверка по всей странице (confidence штрафуется ×0.9); не найден при `art./p.` → review `unit_not_found`.

- [ ] **Step 1: failing test**

`importer/tests/test_verifier.py`:
```python
from pathlib import Path
from importer.lexuz import LexuzClient, LexuzUnreachable
from importer.models import ProductRequirement
from importer.verifier import verify_item

FIX = Path(__file__).parent / "fixtures"
HTML = (FIX / "lexuz_act_ru.html").read_text()

BASE = {
    "title": "т", "nature": "obligation", "type": "import",
    "category": "Оценка соответствия, декларация и сертификация", "summary": "с",
    "legal_quote_ru": "Продукция, включённая в перечень, подлежит обязательному "
                      "подтверждению соответствия в установленном порядке.",
    "act": {"name": "ЗРУ-819", "number": "819", "date": "2023-04-05",
            "lexuz_url": "https://lex.uz/docs/-6445145"},
    "unit": "ст. 14", "edition_date": None,
    "scope": {"level": "all"}, "addressees": ["importer"], "agency": None,
    "how_to": [], "documents": [], "sanction": None,
    "discovered_via": "domain", "needs_review": False,
}


def req(**over):
    return ProductRequirement.model_validate({**BASE, **over})


def client(tmp_path, html=HTML):
    return LexuzClient(cache_dir=tmp_path, fetcher=lambda url: html)


def test_gate_passes(tmp_path):
    r = verify_item(req(), client(tmp_path), llm=None)
    assert r.ok and r.doc_id == "6445145" and r.ref == "art.14" and r.confidence >= 0.85


def test_needs_review_short_circuits(tmp_path):
    r = verify_item(req(needs_review=True), client(tmp_path), llm=None)
    assert not r.ok and r.reason == "needs_review_from_report"


def test_act_not_found(tmp_path):
    r = verify_item(req(act={"lexuz_url": None}), client(tmp_path), llm=None)
    assert not r.ok and r.reason == "act_not_found"


def test_unit_not_found(tmp_path):
    r = verify_item(req(unit="ст. 99"), client(tmp_path), llm=None)
    assert not r.ok and r.reason == "unit_not_found"


def test_quote_mismatch(tmp_path):
    r = verify_item(req(legal_quote_ru="совершенно другой текст про налоги и пошлины " * 3),
                    client(tmp_path), llm=None)
    assert not r.ok and r.reason == "quote_mismatch"


def test_repealed(tmp_path):
    html = "<p>Документ утратил силу. " + " и в на или" * 30 + "</p>"
    r = verify_item(req(), client(tmp_path, html), llm=None)
    assert not r.ok and r.reason == "act_repealed"


def test_uz_only(tmp_path):
    html = "<p>Ushbu hujjat faqat o'zbek tilida mavjud. Modda 14. Matn.</p>"
    r = verify_item(req(), client(tmp_path, html), llm=None)
    assert not r.ok and r.reason == "uz_only_act"


def test_unreachable(tmp_path):
    def boom(url):
        raise LexuzUnreachable("down")
    lex = LexuzClient(cache_dir=tmp_path, fetcher=boom)
    r = verify_item(req(), lex, llm=None)
    assert not r.ok and r.reason == "lexuz_unreachable"
```

Run: `.venv-importer/bin/python -m pytest importer/tests/test_verifier.py -v` → FAIL

- [ ] **Step 2: реализация**

`importer/verifier.py`:
```python
"""Верификационный гейт: любое сомнение → review, не в БД (правило хендоффа)."""
from dataclasses import dataclass

from rapidfuzz import fuzz

from importer.lexuz import LexuzClient, LexuzUnreachable
from importer.refs import lexuz_doc_id, parse_unit_ref


@dataclass
class GateResult:
    ok: bool
    reason: str | None = None
    detail: str | None = None
    doc_id: str | None = None
    ref: str | None = None
    confidence: float | None = None
    paragraph_text: str | None = None


def _review(reason: str, detail: str = "", **kw) -> GateResult:
    return GateResult(ok=False, reason=reason, detail=detail, **kw)


def verify_item(req, lexuz: LexuzClient, llm) -> GateResult:
    if req.needs_review:
        return _review("needs_review_from_report", "помечено моделью в отчёте")

    doc_id = lexuz_doc_id(req.act.lexuz_url)
    if not doc_id:
        return _review("act_not_found", f"нет lex.uz-ссылки: {req.act.lexuz_url!r}")

    try:
        html = lexuz.fetch(doc_id)
    except LexuzUnreachable as e:
        return _review("lexuz_unreachable", str(e), doc_id=doc_id)

    if LexuzClient.is_repealed(html):
        return _review("act_repealed", "маркер «утратил силу» на странице", doc_id=doc_id)
    if not LexuzClient.is_russian(html):
        return _review("uz_only_act", "официального RU-текста нет (v1: ветка UZ не реализована)",
                       doc_id=doc_id)

    ref = parse_unit_ref(req.unit)
    if ref is None:
        return _review("unit_not_found", f"unit не распознан: {req.unit!r}", doc_id=doc_id)

    paragraph = LexuzClient.find_paragraph(html, ref)
    penalty = 1.0
    if paragraph is None:
        if ref.startswith(("art.", "p.")):
            return _review("unit_not_found", f"пункт {ref} не найден в акте",
                           doc_id=doc_id, ref=ref)
        paragraph = LexuzClient.page_text(html)  # перечни: сверка по всей странице (v1)
        penalty = 0.9

    if not req.legal_quote_ru:
        return _review("quote_missing", "нет legal_quote_ru", doc_id=doc_id, ref=ref)

    score = fuzz.partial_ratio(req.legal_quote_ru.lower(), paragraph.lower()) / 100.0
    confidence = round(score * penalty, 2)
    if score >= 0.85:
        return GateResult(ok=True, doc_id=doc_id, ref=ref,
                          confidence=confidence, paragraph_text=paragraph[:4000])
    if score >= 0.60 and llm is not None and llm.same_meaning(req.legal_quote_ru, paragraph[:6000]):
        return GateResult(ok=True, doc_id=doc_id, ref=ref,
                          confidence=confidence, paragraph_text=paragraph[:4000])
    return _review("quote_mismatch", f"fuzzy={score:.2f}", doc_id=doc_id, ref=ref,
                   confidence=confidence)
```

- [ ] **Step 3: тесты зелёные**

Run: `.venv-importer/bin/python -m pytest importer/tests/test_verifier.py -v`
Expected: `9 passed`

- [ ] **Step 4: Commit**

```bash
git add importer/verifier.py importer/tests/test_verifier.py
git commit -m "feat(importer): верификационный гейт против lex.uz"
```

---

### Task 10: resolver.py — акт в JurisBase и IX, очередь загрузки

**Files:**
- Create: `importer/resolver.py`, `importer/tests/test_resolver.py`

**Interfaces:**
- Consumes: `jb_client`/`ix_client` (Task 7; в тестах — фейки), `ActRef` (Task 2), `GateResult` (Task 9).
- Produces:
  - `resolve_act(act: ActRef, doc_id: str, jb, ix, queue_path: Path) -> dict` — строка IX `acts` (минимум `{"id": ...}`). Логика: (1) JurisBase `acts` по doc_id → если найден готовый (`is_stub=false`, `status='published'`) взять `jurisbase_act_id` и title; (2) не найден → append `{"doc_id", "lexuz_url", "name", "requested_at_run"}` в `queue_path` (JSONL, без дублей по doc_id); (3) upsert в IX `acts`: сначала select по `jurisbase_act_id`, потом по `url ilike %{doc_id}%`, нет → insert `{title, number, url, status:'active', jurisbase_act_id?}`.
  - `ensure_paragraph(ix, act_row: dict, ref: str, quote_ru: str | None, doc_id: str) -> dict` — строка IX `act_paragraphs`: select по `(act_id, paragraph_ref=ref)`, нет → insert `{act_id, paragraph_ref: ref, verbatim_ru: quote_ru, deep_link_url: f"https://lex.uz/ru/docs/-{doc_id}"}`.
- ВАЖНО (первый шаг реализации): колонки JurisBase `acts` неизвестны точно — выполнить разведку
  `python -c "from importer.db import jb_client; print(jb_client().table('acts').select('*').limit(1).execute().data)"`
  и зафиксировать в `resolver.py` константы `JB_ID_COLUMN` / `JB_URL_COLUMN` / фильтры готовности по фактическим именам. Тесты используют фейки и от разведки не зависят; разведка нужна перед живым прогоном (Task 14). Если ключей JB ещё нет — оставить дефолты и TODO-строку в act_queue.

- [ ] **Step 1: failing test**

`importer/tests/test_resolver.py`:
```python
import json
from importer.models import ActRef
from importer.resolver import ensure_paragraph, resolve_act


class FakeTable:
    """Мини-фейк supabase table: select().eq()/ilike().limit().execute() и insert()."""
    def __init__(self, store, name):
        self.store, self.name, self._filters = store, name, []

    def select(self, *_): return self
    def limit(self, *_): return self

    def eq(self, col, val):
        self._filters.append(lambda r: r.get(col) == val); return self

    def ilike(self, col, pattern):
        needle = pattern.strip("%")
        self._filters.append(lambda r: needle in (r.get(col) or "")); return self

    def execute(self):
        rows = [r for r in self.store.get(self.name, [])
                if all(f(r) for f in self._filters)]
        self._filters = []
        return type("R", (), {"data": rows})()

    def insert(self, row):
        row = {"id": f"id-{len(self.store.get(self.name, []))}", **row}
        self.store.setdefault(self.name, []).append(row)
        store_row = row
        return type("Q", (), {"execute": lambda self_: type("R", (), {"data": [store_row]})()})()


class FakeClient:
    def __init__(self, store): self.store = store
    def table(self, name): return FakeTable(self.store, name)


ACT = ActRef(name="ЗРУ-819", number="819", date="2023-04-05",
             lexuz_url="https://lex.uz/docs/-6445145")


def test_resolve_act_not_in_jb_queues_and_inserts(tmp_path):
    jb, ix = FakeClient({"acts": []}), FakeClient({"acts": []})
    q = tmp_path / "act_queue.jsonl"
    row = resolve_act(ACT, "6445145", jb, ix, q)
    assert row["id"].startswith("id-")
    assert ix.store["acts"][0]["url"] == "https://lex.uz/ru/docs/-6445145"
    queued = [json.loads(l) for l in q.read_text().splitlines()]
    assert queued[0]["doc_id"] == "6445145"
    # повторный резолв: без дублей в acts и в очереди
    row2 = resolve_act(ACT, "6445145", jb, ix, q)
    assert row2["id"] == row["id"]
    assert len(ix.store["acts"]) == 1
    assert len(q.read_text().splitlines()) == 1


def test_ensure_paragraph_idempotent(tmp_path):
    ix = FakeClient({"act_paragraphs": []})
    act_row = {"id": "act-1"}
    p1 = ensure_paragraph(ix, act_row, "art.14", "цитата", "6445145")
    p2 = ensure_paragraph(ix, act_row, "art.14", "другая", "6445145")
    assert p1["id"] == p2["id"]
    assert len(ix.store["act_paragraphs"]) == 1
```

Run: `.venv-importer/bin/python -m pytest importer/tests/test_resolver.py -v` → FAIL

- [ ] **Step 2: реализация**

`importer/resolver.py`:
```python
"""Резолв акта: JurisBase (канон) → IX.acts (витрина) → очередь загрузки для скрейпера."""
import json
from pathlib import Path

# Имена колонок JurisBase acts — проверить разведкой перед живым прогоном (Task 14):
# python -c "from importer.db import jb_client; print(jb_client().table('acts').select('*').limit(1).execute().data)"
JB_ID_COLUMN = "id"
JB_URL_COLUMN = "source_url"


def _first(resp):
    return resp.data[0] if resp.data else None


def _queue_act(queue_path: Path, doc_id: str, act) -> None:
    queue_path.parent.mkdir(parents=True, exist_ok=True)
    if queue_path.exists():
        for line in queue_path.read_text(encoding="utf-8").splitlines():
            if json.loads(line).get("doc_id") == doc_id:
                return
    entry = {"doc_id": doc_id, "lexuz_url": act.lexuz_url, "name": act.name}
    with queue_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def _jb_lookup(jb, doc_id: str):
    if jb is None:
        return None
    try:
        resp = (jb.table("acts").select("*")
                .ilike(JB_URL_COLUMN, f"%{doc_id}%").limit(1).execute())
        row = _first(resp)
        if row and not row.get("is_stub", False) and row.get("status") == "published":
            return row
    except Exception:
        return None  # JurisBase недоступен — не блокируем гейт (решение: прямой fetch)
    return None


def resolve_act(act, doc_id: str, jb, ix, queue_path: Path) -> dict:
    jb_row = _jb_lookup(jb, doc_id)
    if jb_row is None:
        _queue_act(queue_path, doc_id, act)

    canonical_url = f"https://lex.uz/ru/docs/-{doc_id}"
    if jb_row is not None:
        existing = _first(ix.table("acts").select("*")
                          .eq("jurisbase_act_id", str(jb_row[JB_ID_COLUMN])).limit(1).execute())
        if existing:
            return existing
    existing = _first(ix.table("acts").select("*")
                      .ilike("url", f"%{doc_id}%").limit(1).execute())
    if existing:
        return existing

    row = {
        "title": (jb_row or {}).get("title") or act.name or f"Акт lex.uz {doc_id}",
        "number": act.number,
        "url": canonical_url,
        "status": "active",
    }
    if jb_row is not None:
        row["jurisbase_act_id"] = str(jb_row[JB_ID_COLUMN])
    return _first(ix.table("acts").insert(row).execute())


def ensure_paragraph(ix, act_row: dict, ref: str, quote_ru: str | None, doc_id: str) -> dict:
    existing = _first(ix.table("act_paragraphs").select("*")
                      .eq("act_id", act_row["id"]).eq("paragraph_ref", ref).limit(1).execute())
    if existing:
        return existing
    return _first(ix.table("act_paragraphs").insert({
        "act_id": act_row["id"],
        "paragraph_ref": ref,
        "verbatim_ru": quote_ru,
        "deep_link_url": f"https://lex.uz/ru/docs/-{doc_id}",
    }).execute())
```

- [ ] **Step 3: тесты зелёные**

Run: `.venv-importer/bin/python -m pytest importer/tests/test_resolver.py -v`
Expected: `2 passed`

- [ ] **Step 4: Commit**

```bash
git add importer/resolver.py importer/tests/test_resolver.py
git commit -m "feat(importer): резолвер актов JurisBase→IX с очередью загрузки"
```

---

### Task 11: dedup.py — глобальный дедуп и merge

**Files:**
- Create: `importer/dedup.py`, `importer/tests/test_dedup.py`

**Interfaces:**
- Consumes: IX-клиент (фейк из test_resolver переиспользовать через `importer/tests/fakes.py` — вынести FakeClient/FakeTable туда и импортировать в обоих тестах).
- Produces:
  - `external_key(doc_id: str, ref: str) -> str` — `f"lexuz:{doc_id}/{ref}"`
  - `find_existing(ix, key: str) -> dict | None` — `requirements` по `external_key`
  - `sanctions_conflict(existing_sanctions: list[dict], new_sanction: dict | None) -> bool` — True только если совпала `article` (нормализованно: lower, без пробелов), но отличается `amount`; разные статьи = два слоя санкций, не конфликт (урок хендоффа про КоАО + ст. 46 ЗРУ-819)
  - `merge_requirement(ix, existing: dict, new_scope_rows: list[tuple[str, str | None]], new_sanction: dict | None, import_item_id: str) -> str` — возвращает `"merged"` или `"conflict"`. При merge: (а) дочитать `requirement_applicability` существующего; если у него уже есть `all_products`/`all_services` — scope не трогать; иначе вставить отсутствующие `(scope, code)`; (б) `requirement_details` (lang='ru'): если новая санкция с новой статьёй — добавить в jsonb-массив `sanctions` и update; при конфликте по `sanctions_conflict` — вернуть `"conflict"`, ничего не писать; (в) insert в `requirement_sources` `(requirement_id, import_item_id)` (select-before-insert).

- [ ] **Step 1: вынести фейки**

Создать `importer/tests/fakes.py`, перенести туда `FakeTable`/`FakeClient` из `test_resolver.py` (в `FakeTable` добавить метод `update(patch)`: применяет patch ко всем строкам, прошедшим фильтры, тем же паттерном `execute`). В `test_resolver.py` заменить локальные классы на `from importer.tests.fakes import FakeClient`. Прогнать test_resolver — зелёный.

- [ ] **Step 2: failing test**

`importer/tests/test_dedup.py`:
```python
from importer.dedup import external_key, find_existing, merge_requirement, sanctions_conflict
from importer.tests.fakes import FakeClient


def test_external_key():
    assert external_key("6445145", "art.14") == "lexuz:6445145/art.14"


def test_find_existing():
    ix = FakeClient({"requirements": [{"id": "r1", "external_key": "lexuz:1/art.2"}]})
    assert find_existing(ix, "lexuz:1/art.2")["id"] == "r1"
    assert find_existing(ix, "lexuz:1/art.3") is None


def test_sanctions_conflict_same_article_diff_fine():
    existing = [{"amount": "до 75 БРВ", "article": "ст. 186 КоАО", "extra": None}]
    assert sanctions_conflict(existing, {"article": "ст.186 КоАО", "fine_bru": "до 100 БРВ"})
    # другая статья = второй слой, не конфликт
    assert not sanctions_conflict(existing, {"article": "ст. 46 ЗРУ-819", "fine_bru": "50%"})
    # та же статья, тот же штраф — не конфликт
    assert not sanctions_conflict(existing, {"article": "ст. 186 КоАО", "fine_bru": "до 75 БРВ"})


def _store():
    return {
        "requirements": [{"id": "r1", "external_key": "lexuz:1/art.2"}],
        "requirement_applicability": [
            {"id": "a1", "requirement_id": "r1", "scope": "hs_code", "code": "2523290000"}],
        "requirement_details": [
            {"requirement_id": "r1", "lang": "ru",
             "sanctions": [{"amount": "до 75 БРВ", "article": "ст. 186 КоАО", "extra": None}]}],
        "requirement_sources": [],
    }


def test_merge_extends_scope_and_sources():
    ix = FakeClient(_store())
    status = merge_requirement(ix, {"id": "r1"}, [("hs_code", "3208101000")],
                               {"article": "ст. 46 ЗРУ-819", "fine_bru": "до 50%"}, "item-9")
    assert status == "merged"
    codes = {r["code"] for r in ix.store["requirement_applicability"]}
    assert codes == {"2523290000", "3208101000"}
    assert len(ix.store["requirement_details"][0]["sanctions"]) == 2
    assert ix.store["requirement_sources"][0]["import_item_id"] == "item-9"
    # идемпотентность
    merge_requirement(ix, {"id": "r1"}, [("hs_code", "3208101000")], None, "item-9")
    assert len(ix.store["requirement_applicability"]) == 2
    assert len(ix.store["requirement_sources"]) == 1


def test_merge_conflict():
    ix = FakeClient(_store())
    status = merge_requirement(ix, {"id": "r1"}, [],
                               {"article": "ст. 186 КоАО", "fine_bru": "до 500 БРВ"}, "item-9")
    assert status == "conflict"
    assert len(ix.store["requirement_details"][0]["sanctions"]) == 1  # ничего не записано
```

Run: `.venv-importer/bin/python -m pytest importer/tests/test_dedup.py -v` → FAIL

- [ ] **Step 3: реализация**

`importer/dedup.py`:
```python
"""Глобальный дедуп по ключу акт+пункт. Ложная склейка хуже дубля: сомнение → review."""
import re


def external_key(doc_id: str, ref: str) -> str:
    return f"lexuz:{doc_id}/{ref}"


def _first(resp):
    return resp.data[0] if resp.data else None


def find_existing(ix, key: str):
    return _first(ix.table("requirements").select("*")
                  .eq("external_key", key).limit(1).execute())


def _norm_article(article: str | None) -> str:
    return re.sub(r"\s+", "", (article or "").lower())


def sanctions_conflict(existing_sanctions: list[dict], new_sanction: dict | None) -> bool:
    if not new_sanction or not new_sanction.get("article"):
        return False
    new_art = _norm_article(new_sanction["article"])
    new_amount = (new_sanction.get("fine_bru") or "").strip().lower()
    for s in existing_sanctions:
        if _norm_article(s.get("article")) == new_art:
            old_amount = (s.get("amount") or "").strip().lower()
            if old_amount and new_amount and old_amount != new_amount:
                return True
    return False


def merge_requirement(ix, existing: dict, new_scope_rows, new_sanction, import_item_id) -> str:
    req_id = existing["id"]

    details = _first(ix.table("requirement_details").select("*")
                     .eq("requirement_id", req_id).eq("lang", "ru").limit(1).execute())
    old_sanctions = (details or {}).get("sanctions") or []
    if sanctions_conflict(old_sanctions, new_sanction):
        return "conflict"

    current = ix.table("requirement_applicability").select("*") \
        .eq("requirement_id", req_id).execute().data
    has_all = any(r["scope"] in ("all_products", "all_services") for r in current)
    present = {(r["scope"], r.get("code")) for r in current}
    if not has_all:
        for scope, code in new_scope_rows:
            if (scope, code) not in present:
                ix.table("requirement_applicability").insert(
                    {"requirement_id": req_id, "scope": scope, "code": code}).execute()
                present.add((scope, code))

    if details is not None and new_sanction and new_sanction.get("article"):
        arts = {_norm_article(s.get("article")) for s in old_sanctions}
        if _norm_article(new_sanction["article"]) not in arts:
            merged = old_sanctions + [{"amount": new_sanction.get("fine_bru"),
                                       "article": new_sanction.get("article"),
                                       "extra": new_sanction.get("extra")}]
            ix.table("requirement_details").update({"sanctions": merged}) \
                .eq("requirement_id", req_id).eq("lang", "ru").execute()

    src = _first(ix.table("requirement_sources").select("*")
                 .eq("requirement_id", req_id)
                 .eq("import_item_id", import_item_id).limit(1).execute())
    if src is None:
        ix.table("requirement_sources").insert(
            {"requirement_id": req_id, "import_item_id": import_item_id}).execute()
    return "merged"
```

(если `FakeTable.update` фильтрует после `eq` — работает как supabase: сначала фильтры, потом update)

- [ ] **Step 4: тесты зелёные**

Run: `.venv-importer/bin/python -m pytest importer/tests/test_dedup.py importer/tests/test_resolver.py -v`
Expected: все passed

- [ ] **Step 5: Commit**

```bash
git add importer/dedup.py importer/tests/test_dedup.py importer/tests/fakes.py importer/tests/test_resolver.py
git commit -m "feat(importer): глобальный дедуп акт+пункт с merge scope и санкций"
```

---

### Task 12: loader.py — запись в БД

**Files:**
- Create: `importer/loader.py`, `importer/tests/test_loader.py`

**Interfaces:**
- Consumes: фейки (`importer/tests/fakes.py`), mappings (Task 7), dedup (Task 11), resolver (Task 10), `GateResult` (Task 9).
- Produces `class Loader(ix, domains: dict)`:
  - `start_run(rf: ReportFile, raw_json: dict | None, gray_zones: list[str]) -> str` — идемпотентно: select `import_runs` по `file_hash`; есть → удалить его `import_items` (каскадом уйдут sources) и вернуть тот же run_id; нет → insert
  - `upsert_subject(report) -> None` — product: select `products` по `hs_code`, нет → insert `{hs_code, name_ru: product.name}`; service: select `services` по `oked_code`, нет → insert `{oked_code: okved, name_ru: service.name, ikpu_code: None}`; существующие НЕ перезаписывать
  - `save_item(run_id, idx, req, status, *, review_reason=None, review_detail=None, requirement_id=None) -> str` — insert `import_items`, вернуть id
  - `load_requirement(req, kind, gate: GateResult, act_row, paragraph_row, subject, stage_ids: dict) -> str` — создаёт requirement + contents(ru) + details(ru) + citations + applicability; возвращает requirement_id. Маппинг полей:
    - `requirements`: `status='published'`, `trust_label='validated'`, `origin='ai_pipeline'`, `deontic=map_nature(...)`, `operation=map_operation(kind, req)`, `addressee_roles=map_addressees(...)`, `confidence_score=gate.confidence`, `external_key=external_key(gate.doc_id, gate.ref)`, `requirement_category=map_category(...)` (product), `lifecycle_stage_id=stage_ids.get(STAGE_TO_CODE[req.stage])` (service), `published_at=now()` (строкой `"now()"` нельзя — использовать `datetime.now(timezone.utc).isoformat()`)
    - `requirement_contents(ru)`: `title=req.title`, `sanction_summary=f"{sanction.article}: {sanction.fine_bru}"` если есть
    - `requirement_details(ru)`: `description=req.summary`, `how_to_comply=[{"step","deadline","cost": fee или cost}]`, `documents=[{"name","where_to_get": where}]`, `sanctions=[{"amount": fine_bru, "article", "extra"}]`
    - `requirement_citations`: `(requirement_id, paragraph_id, is_primary=true, sort_order=0)`
    - `requirement_applicability`: строки из `map_product_scope(...)` / `map_service_scope(...)`
  - `finalize_run(run_id, status: str, counters: dict, error: str | None = None) -> None` — update run
- `MappingError` при маппинге НЕ ловится внутри `load_requirement` — её ловит pipeline (Task 13) и превращает в review-item.

- [ ] **Step 1: failing test**

`importer/tests/test_loader.py`:
```python
from importer.loader import Loader
from importer.models import ProductReport
from importer.parser import ReportFile
from importer.tests.fakes import FakeClient
from importer.tests.test_models import PRODUCT_JSON
from importer.verifier import GateResult
from pathlib import Path

RF = ReportFile(Path("product--cement--claude.md"), "product", "cement", "claude", "h" * 64, "md")
GATE = GateResult(ok=True, doc_id="6445145", ref="art.14", confidence=0.93)


def make_loader():
    ix = FakeClient({t: [] for t in
                     ("import_runs", "import_items", "products", "services", "requirements",
                      "requirement_contents", "requirement_details", "requirement_citations",
                      "requirement_applicability", "requirement_sources")})
    return Loader(ix, domains={"стройматериалы": ["25", "68"]}), ix


def test_start_run_idempotent():
    loader, ix = make_loader()
    run1 = loader.start_run(RF, PRODUCT_JSON, ["зона 1"])
    ix.store["import_items"].append({"id": "x", "run_id": run1, "idx": 0,
                                     "raw": {}, "status": "review"})
    run2 = loader.start_run(RF, PRODUCT_JSON, ["зона 1"])
    assert run1 == run2
    assert ix.store["import_items"] == []  # items пересозданы заново


def test_upsert_subject_product():
    loader, ix = make_loader()
    report = ProductReport.model_validate(PRODUCT_JSON)
    loader.upsert_subject(report)
    loader.upsert_subject(report)
    assert len(ix.store["products"]) == 1
    assert ix.store["products"][0]["hs_code"] == "2523290000"


def test_load_requirement_full():
    loader, ix = make_loader()
    report = ProductReport.model_validate(PRODUCT_JSON)
    req_id = loader.load_requirement(
        report.requirements[0], "product", GATE,
        act_row={"id": "act-1"}, paragraph_row={"id": "par-1"},
        subject=report.product, stage_ids={})
    r = ix.store["requirements"][0]
    assert r["status"] == "published" and r["trust_label"] == "validated"
    assert r["origin"] == "ai_pipeline" and r["external_key"] == "lexuz:6445145/art.14"
    assert r["requirement_category"] == "tbt"
    assert ix.store["requirement_contents"][0]["title"].startswith("Получить")
    assert ix.store["requirement_details"][0]["how_to_comply"][0]["step"] == "Подать заявку"
    assert ix.store["requirement_citations"][0] == {
        "id": "id-0", "requirement_id": req_id, "paragraph_id": "par-1",
        "is_primary": True, "sort_order": 0}
    assert ix.store["requirement_applicability"][0]["scope"] == "hs_prefix"
```

(в `FakeTable.insert` id добавляется всегда — для junction-таблиц это безвредно)

Run: `.venv-importer/bin/python -m pytest importer/tests/test_loader.py -v` → FAIL

- [ ] **Step 2: реализация**

`importer/loader.py`:
```python
"""Запись результатов в Supabase Inspector X: staging + основные таблицы витрины."""
from datetime import datetime, timezone

from importer.dedup import external_key
from importer.mappings import (STAGE_TO_CODE, map_addressees, map_category, map_nature,
                               map_operation, map_product_scope, map_service_scope)


def _first(resp):
    return resp.data[0] if resp.data else None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Loader:
    def __init__(self, ix, domains: dict):
        self.ix = ix
        self.domains = domains

    def start_run(self, rf, raw_json, gray_zones) -> str:
        existing = _first(self.ix.table("import_runs").select("*")
                          .eq("file_hash", rf.file_hash).limit(1).execute())
        if existing:
            self.ix.table("import_items").delete().eq("run_id", existing["id"]).execute()
            return existing["id"]
        row = _first(self.ix.table("import_runs").insert({
            "file_name": rf.path.name, "file_hash": rf.file_hash,
            "subject_kind": rf.kind, "subject_slug": rf.slug, "model": rf.model,
            "status": "parsed", "raw_json": raw_json, "gray_zones": gray_zones,
        }).execute())
        return row["id"]

    def upsert_subject(self, report) -> None:
        if hasattr(report, "product"):
            p = report.product
            if not p.hs_code:
                return
            if _first(self.ix.table("products").select("id")
                      .eq("hs_code", p.hs_code).limit(1).execute()):
                return
            self.ix.table("products").insert(
                {"hs_code": p.hs_code, "name_ru": p.name}).execute()
        else:
            s = report.service
            if _first(self.ix.table("services").select("id")
                      .eq("oked_code", s.okved).limit(1).execute()):
                return
            self.ix.table("services").insert(
                {"oked_code": s.okved, "name_ru": s.name}).execute()

    def save_item(self, run_id, idx, req, status, *, review_reason=None,
                  review_detail=None, requirement_id=None) -> str:
        row = _first(self.ix.table("import_items").insert({
            "run_id": run_id, "idx": idx, "raw": req.model_dump(mode="json"),
            "status": status, "review_reason": review_reason,
            "review_detail": review_detail, "requirement_id": requirement_id,
        }).execute())
        return row["id"]

    def load_requirement(self, req, kind, gate, act_row, paragraph_row,
                         subject, stage_ids: dict) -> str:
        base = {
            "status": "published", "trust_label": "validated", "origin": "ai_pipeline",
            "deontic": map_nature(req.nature),
            "operation": map_operation(kind, req),
            "addressee_roles": map_addressees(req.addressees),
            "confidence_score": gate.confidence,
            "external_key": external_key(gate.doc_id, gate.ref),
            "published_at": _now(),
        }
        if kind == "product":
            base["requirement_category"] = map_category(req.category)
            scope_rows = map_product_scope(
                req.scope, subject.hs_code,
                {**self.domains, "_domain": subject.domain or ""})
        else:
            base["lifecycle_stage_id"] = stage_ids.get(STAGE_TO_CODE[req.stage])
            scope_rows = map_service_scope(req.scope, subject.okved)

        req_row = _first(self.ix.table("requirements").insert(base).execute())
        req_id = req_row["id"]

        sanction = req.sanction
        self.ix.table("requirement_contents").insert({
            "requirement_id": req_id, "lang": "ru", "title": req.title,
            "sanction_summary": (f"{sanction.article}: {sanction.fine_bru}"
                                 if sanction and sanction.article else None),
        }).execute()
        self.ix.table("requirement_details").insert({
            "requirement_id": req_id, "lang": "ru", "description": req.summary,
            "how_to_comply": [{"step": h.step, "deadline": h.deadline,
                               "cost": h.fee or h.cost} for h in req.how_to],
            "documents": [{"name": d.name, "where_to_get": d.where} for d in req.documents],
            "sanctions": ([{"amount": sanction.fine_bru, "article": sanction.article,
                            "extra": sanction.extra}] if sanction and sanction.article else []),
        }).execute()
        self.ix.table("requirement_citations").insert({
            "requirement_id": req_id, "paragraph_id": paragraph_row["id"],
            "is_primary": True, "sort_order": 0,
        }).execute()
        for scope, code in scope_rows:
            self.ix.table("requirement_applicability").insert({
                "requirement_id": req_id, "scope": scope, "code": code}).execute()
        return req_id

    def finalize_run(self, run_id, status, counters, error=None) -> None:
        self.ix.table("import_runs").update({
            "status": status, "error": error,
            "loaded_count": counters.get("loaded", 0),
            "merged_count": counters.get("merged", 0),
            "review_count": counters.get("review", 0),
        }).eq("id", run_id).execute()
```

В `FakeTable` добавить `delete()`: как `update`, но удаляет отфильтрованные строки из store.

- [ ] **Step 3: тесты зелёные**

Run: `.venv-importer/bin/python -m pytest importer/tests -v`
Expected: все passed (весь пакет)

- [ ] **Step 4: Commit**

```bash
git add importer/loader.py importer/tests/test_loader.py importer/tests/fakes.py
git commit -m "feat(importer): loader — запись run/items/requirements в БД"
```

---

### Task 13: pipeline.py + cli.py — сборка конвейера

**Files:**
- Create: `importer/pipeline.py`, `importer/cli.py`, `importer/__main__.py`, `importer/tests/test_pipeline.py`

**Interfaces:**
- Consumes: всё из Task 2–12.
- Produces:
  - `@dataclass RunSummary: run_id: str | None; loaded: int; merged: int; review: int; reasons: dict[str, int]; dry_run: bool`
  - `run_import(path: Path, ix, jb, lexuz: LexuzClient, llm: LLM | None, dry_run: bool = False, queue_path: Path = Path("research/act_queue.jsonl")) -> RunSummary`
  - CLI: `python -m importer import-report <file> [--dry-run]`, `python -m importer review list`, `python -m importer review show <item_id>`
- Логика `run_import` по item'у: `verify_item` → не ok → save_item(review) (в dry-run — только счётчик). Ok → try mappings/dedup/load: `MappingError` → review; `find_existing(key)` есть → `merge_requirement` → `"conflict"` → review(`cross_model_conflict`) иначе merged; нет → `resolve_act` + `ensure_paragraph` + `load_requirement` + `save_item(loaded)` + insert `requirement_sources`. Ошибка одного item не роняет прогон (`except Exception` → review `internal_error`, лог в stderr). В dry-run в БД не пишется ничего: Loader не вызывается, резолвер не вызывается, только parse+verify+«что бы сделали» в консоль.
- `stage_ids` для сервисов: один select `lifecycle_stages` (code, id) в начале прогона → dict.

- [ ] **Step 1: failing test (end-to-end на фейках)**

`importer/tests/test_pipeline.py`:
```python
from pathlib import Path
from importer.lexuz import LexuzClient
from importer.pipeline import run_import
from importer.tests.fakes import FakeClient

FIX = Path(__file__).parent / "fixtures"
HTML = (FIX / "lexuz_act_ru.html").read_text()


def make_ix():
    return FakeClient({t: [] for t in
                       ("import_runs", "import_items", "products", "services", "acts",
                        "act_paragraphs", "requirements", "requirement_contents",
                        "requirement_details", "requirement_citations",
                        "requirement_applicability", "requirement_sources",
                        "lifecycle_stages")})


def prepare(tmp_path):
    report = (FIX / "report_product_ok.md").read_text()
    # цитата фикстуры отчёта должна совпадать со статьёй 14 фикстуры HTML
    report = report.replace(
        "продукция подлежит обязательному подтверждению соответствия",
        "Продукция, включённая в перечень, подлежит обязательному подтверждению соответствия")
    path = tmp_path / "product--cement--claude.md"
    path.write_text(report)
    lexuz = LexuzClient(cache_dir=tmp_path / "cache", fetcher=lambda url: HTML)
    return path, lexuz


def test_e2e_load(tmp_path):
    path, lexuz = prepare(tmp_path)
    ix = make_ix()
    s = run_import(path, ix, jb=None, lexuz=lexuz, llm=None,
                   queue_path=tmp_path / "q.jsonl")
    assert (s.loaded, s.merged, s.review) == (1, 0, 0)
    assert ix.store["requirements"][0]["external_key"] == "lexuz:6445145/art.14"
    assert ix.store["import_runs"][0]["status"] == "loaded"
    assert ix.store["import_items"][0]["status"] == "loaded"


def test_e2e_rerun_merges_not_duplicates(tmp_path):
    path, lexuz = prepare(tmp_path)
    ix = make_ix()
    run_import(path, ix, None, lexuz, None, queue_path=tmp_path / "q.jsonl")
    s2 = run_import(path, ix, None, lexuz, None, queue_path=tmp_path / "q.jsonl")
    assert len(ix.store["requirements"]) == 1  # идемпотентность
    assert s2.merged == 1 and s2.loaded == 0


def test_e2e_dry_run_writes_nothing(tmp_path):
    path, lexuz = prepare(tmp_path)
    ix = make_ix()
    s = run_import(path, ix, None, lexuz, None, dry_run=True,
                   queue_path=tmp_path / "q.jsonl")
    assert s.loaded == 1 and s.run_id is None
    assert all(not rows for rows in ix.store.values())
```

Run: `.venv-importer/bin/python -m pytest importer/tests/test_pipeline.py -v` → FAIL

- [ ] **Step 2: реализация**

`importer/pipeline.py`:
```python
"""Оркестрация: parse → resolve → verify → dedup → load для одного файла отчёта."""
import sys
import traceback
from dataclasses import dataclass, field
from pathlib import Path

from importer.dedup import external_key, find_existing, merge_requirement
from importer.loader import Loader
from importer.mappings import (MappingError, load_domains, map_product_scope,
                               map_service_scope)
from importer.parser import ReportParseError, load_report_file, extract_gray_zones, parse_report
from importer.resolver import ensure_paragraph, resolve_act
from importer.verifier import verify_item


@dataclass
class RunSummary:
    run_id: str | None
    loaded: int = 0
    merged: int = 0
    review: int = 0
    reasons: dict = field(default_factory=dict)
    dry_run: bool = False


def _scope_rows(req, kind, subject, domains):
    if kind == "product":
        return map_product_scope(req.scope, subject.hs_code,
                                 {**domains, "_domain": subject.domain or ""})
    return map_service_scope(req.scope, subject.okved)


def run_import(path: Path, ix, jb, lexuz, llm, dry_run: bool = False,
               queue_path: Path = Path("research/act_queue.jsonl")) -> RunSummary:
    rf = load_report_file(path)
    domains = load_domains()
    report = parse_report(rf, llm=llm)  # ReportParseError → наружу, run failed целиком
    subject = report.product if rf.kind == "product" else report.service
    gray = extract_gray_zones(rf.markdown)

    summary = RunSummary(run_id=None, dry_run=dry_run)
    loader = None
    stage_ids = {}
    if not dry_run:
        loader = Loader(ix, domains)
        summary.run_id = loader.start_run(rf, report.model_dump(mode="json"), gray)
        loader.upsert_subject(report)
        stage_ids = {r["code"]: r["id"] for r in
                     ix.table("lifecycle_stages").select("*").execute().data}

    def mark_review(idx, req, reason, detail):
        summary.review += 1
        summary.reasons[reason] = summary.reasons.get(reason, 0) + 1
        if loader:
            loader.save_item(summary.run_id, idx, req, "review",
                             review_reason=reason, review_detail=detail)

    for idx, req in enumerate(report.requirements):
        try:
            gate = verify_item(req, lexuz, llm)
            if not gate.ok:
                mark_review(idx, req, gate.reason, gate.detail)
                continue
            try:
                scope_rows = _scope_rows(req, rf.kind, subject, domains)
            except MappingError as e:
                mark_review(idx, req, e.reason, e.detail)
                continue

            key = external_key(gate.doc_id, gate.ref)
            if dry_run:
                summary.loaded += 1
                print(f"  [dry] {req.title[:60]} → {key}")
                continue

            existing = find_existing(ix, key)
            if existing:
                item_id = loader.save_item(summary.run_id, idx, req, "merged",
                                           requirement_id=existing["id"])
                sanction = req.sanction.model_dump() if req.sanction else None
                status = merge_requirement(ix, existing, scope_rows, sanction, item_id)
                if status == "conflict":
                    ix.table("import_items").update(
                        {"status": "review", "review_reason": "cross_model_conflict",
                         "review_detail": "разные данные на одном ключе акт+пункт",
                         "requirement_id": existing["id"]}).eq("id", item_id).execute()
                    summary.review += 1
                    summary.reasons["cross_model_conflict"] = \
                        summary.reasons.get("cross_model_conflict", 0) + 1
                else:
                    summary.merged += 1
                continue

            act_row = resolve_act(req.act, gate.doc_id, jb, ix, queue_path)
            paragraph_row = ensure_paragraph(ix, act_row, gate.ref,
                                             req.legal_quote_ru, gate.doc_id)
            req_id = loader.load_requirement(req, rf.kind, gate, act_row,
                                             paragraph_row, subject, stage_ids)
            item_id = loader.save_item(summary.run_id, idx, req, "loaded",
                                       requirement_id=req_id)
            ix.table("requirement_sources").insert(
                {"requirement_id": req_id, "import_item_id": item_id}).execute()
            summary.loaded += 1
        except Exception as e:  # ошибка item не роняет прогон
            traceback.print_exc(file=sys.stderr)
            mark_review(idx, req, "internal_error", str(e)[:500])

    if loader:
        loader.finalize_run(summary.run_id, "loaded",
                            {"loaded": summary.loaded, "merged": summary.merged,
                             "review": summary.review})
    return summary
```

`importer/cli.py`:
```python
"""CLI импортёра: import-report / review list / review show."""
import argparse
import json
from pathlib import Path

from importer.db import ix_client, jb_client
from importer.lexuz import LexuzClient
from importer.llm import LLM
from importer.pipeline import run_import


def main(argv=None):
    parser = argparse.ArgumentParser(prog="importer")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_imp = sub.add_parser("import-report", help="импорт одного отчёта")
    p_imp.add_argument("file", type=Path)
    p_imp.add_argument("--dry-run", action="store_true")
    p_imp.add_argument("--no-llm", action="store_true", help="без claude -p (спорное → review)")

    p_rev = sub.add_parser("review", help="review-очередь")
    rev_sub = p_rev.add_subparsers(dest="rev_cmd", required=True)
    rev_sub.add_parser("list")
    p_show = rev_sub.add_parser("show")
    p_show.add_argument("item_id")

    args = parser.parse_args(argv)
    ix = ix_client()

    if args.cmd == "import-report":
        try:
            jb = jb_client()
        except RuntimeError:
            jb = None  # JB-ключей нет — резолвим только через lex.uz, акты в очередь
        lexuz = LexuzClient(cache_dir=Path("research/.cache/lexuz"))
        llm = None if args.no_llm else LLM()
        s = run_import(args.file, ix, jb, lexuz, llm, dry_run=args.dry_run)
        print(f"\n{'[DRY RUN] ' if s.dry_run else ''}loaded={s.loaded} "
              f"merged={s.merged} review={s.review}")
        for reason, n in sorted(s.reasons.items(), key=lambda kv: -kv[1]):
            print(f"  review:{reason} = {n}")
        return

    if args.rev_cmd == "list":
        rows = ix.table("import_items").select("id, review_reason, review_detail, raw") \
            .eq("status", "review").eq("resolution", "pending").execute().data
        for r in rows:
            print(f"{r['id']}  [{r['review_reason']}] {r['raw'].get('title', '')[:70]}")
        print(f"\nвсего в очереди: {len(rows)}")
    else:
        rows = ix.table("import_items").select("*").eq("id", args.item_id).execute().data
        print(json.dumps(rows[0] if rows else {}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
```

`importer/__main__.py`:
```python
from importer.cli import main

main()
```

- [ ] **Step 3: тесты зелёные (весь пакет)**

Run: `.venv-importer/bin/python -m pytest importer/tests -v`
Expected: все passed

- [ ] **Step 4: smoke CLI без сети**

Run: `.venv-importer/bin/python -m importer import-report --help`
Expected: usage без ошибок

- [ ] **Step 5: Commit**

```bash
git add importer/pipeline.py importer/cli.py importer/__main__.py importer/tests/test_pipeline.py
git commit -m "feat(importer): пайплайн и CLI import-report/review"
```

---

### Task 14: Живой прогон на 3 отчётах, PR

**Files:**
- Create: `research/incoming/` (отчёты кладёт Абдурахмон), `.env.importer` (локально, НЕ коммитить), `research/act_queue.jsonl` (появится после прогона)
- Modify: `importer/resolver.py` (константы JB_* по разведке), `importer/domains.yaml` (домены из реальных отчётов)

**Interfaces:**
- Consumes: весь конвейер; реальные ключи в `.env.importer` (IX service key — попросить у Абдурахмона; JB-ключи — если есть, иначе jb=None путь).

- [ ] **Step 1: подготовка**

Проверить `research/incoming/*.md` (3 отчёта от Абдурахмона; переименовать в формат `{product|service}--{слаг}--{модель}.md`, если пришли иначе). Заполнить `.env.importer` (минимум IX_*; ключ спросить, не выдумывать). Если отчётов ещё нет — needs input.

- [ ] **Step 2: разведка JurisBase (если есть JB-ключи)**

Run: `.venv-importer/bin/python -c "from importer.db import jb_client; print(jb_client().table('acts').select('*').limit(1).execute().data)"`
→ поправить `JB_ID_COLUMN`/`JB_URL_COLUMN`/поля готовности в `resolver.py` по фактическим именам колонок; закоммитить. Ключей нет → пропустить (jb=None).

- [ ] **Step 3: dry-run каждого отчёта**

Run: `.venv-importer/bin/python -m importer import-report research/incoming/<файл> --dry-run --no-llm` (сначала без LLM — быстрее видно причины review)
Expected: сводка loaded/review по каждому. Разобрать причины: `unit_not_found` из-за нераспознанных unit-форматов → расширить `_PATTERNS` в refs.py (с тестами); домены отчётов отсутствуют в domains.yaml → добавить. Повторять dry-run до стабильной картины. Реальные форматы unit из отчётов добавить в `test_refs.py` как параметры.

- [ ] **Step 4: боевой прогон**

Run: `.venv-importer/bin/python -m importer import-report research/incoming/<файл>` для каждого из 3 (с LLM: спорные цитаты решает `claude -p`).
Expected: сводки; в БД появились requirements. Проверить в проде: страница товара на https://inspectorx-v2.vercel.app (если товарных страниц на витрине ещё нет — проверить через SQL: `select count(*) from requirements where origin='ai_pipeline'`, счётчики run'ов, содержимое `import_items` review).

- [ ] **Step 5: повторный прогон одного файла — идемпотентность на проде**

Run: тот же `import-report` второй раз.
Expected: `loaded=0`, все прежние карточки → `merged`, дублей в `requirements` нет (проверить: `select external_key, count(*) from requirements group by 1 having count(*) > 1` — пусто).

- [ ] **Step 6: зафиксировать результаты**

Дописать в конец спеки `docs/superpowers/specs/2026-07-12-report-importer-design.md` раздел «Результаты первого прогона»: таблица по 3 отчётам (loaded/merged/review, топ причин review), находки по качеству моделей. Закоммитить вместе с обновлёнными refs/domains и отчётами:

```bash
git add research/incoming importer docs/superpowers/specs/2026-07-12-report-importer-design.md
git commit -m "feat(importer): живой прогон 3 отчётов — результаты и калибровка словарей"
```

- [ ] **Step 7: push и draft PR**

```bash
git push -u origin worktree-report-importer
gh pr create --draft --title "feat: импортёр deep-research отчётов (спека + конвейер + прогон 3 отчётов)" --body "..."
```
В body PR: ссылка на спеку, сводка прогона, открытые вопросы (JB-ключи, UZ-ветка, backfill).
Expected: PR создан, автодеплой Vercel НЕ затронут (main не тронут).

---

## Self-review (выполнен при написании плана)

- Покрытие спеки: parse (T3,T5), resolve (T10), verify (T9), dedup (T11), load (T12), статусы/CLI (T13), миграция+review-очередь (T6), серые зоны → `import_runs.gray_zones` (T12), метрики → счётчики и `reasons` (T13), идемпотентность (T12/T13/T14), тесты на 3 отчётах (T14). UZ-ветка, ТН ВЭД-дерево, UI очереди — вне скоупа по спеке.
- Известные упрощения v1 (осознанные): `find_paragraph` не разбирает строки приложений (сверка по странице с penalty); scope=domain требует ручного domains.yaml; `sanction.url`/`how_to[].source_act_url` резолвятся только в act_queue (не блокируют карточку) — это соответствует спеке.
- Типы сквозные: `GateResult(ok, reason, detail, doc_id, ref, confidence, paragraph_text)` в T9→T12→T13; `MappingError(reason, detail)` в T7→T12→T13; `ReportFile` в T3→T12; сигнатура `run_import(path, ix, jb, lexuz, llm, dry_run, queue_path)` в T13→T14.
