"""Pydantic-схемы JSON-блока отчётов (контракт из research-prompt-{product,service}.md)."""
from typing import Literal
from pydantic import BaseModel, ConfigDict, field_validator


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


def _clean_hs(value):
    """«8703 80» → «870380»; «4011 (4011 10 — ...)» → «4011»; мусор → None.

    БД: check (hs_code ~ '^[0-9]{2,10}$'). Берём ведущую цифровую группу
    (цифры и пробелы до первого постороннего символа), пробелы убираем.
    """
    if not value or not isinstance(value, str):
        return None
    import re
    m = re.match(r"\s*(\d[\d ]*)", value)
    if not m:
        return None
    code = m.group(1).replace(" ", "")
    return code if 2 <= len(code) <= 10 else None


class ProductScope(_Base):
    level: Literal["all", "domain", "hs_list", "this_code"]
    codes: list[str] | None = None
    list_row: str | None = None

    @field_validator("codes", mode="before")
    @classmethod
    def _clean_codes(cls, v):
        if isinstance(v, list):
            return [c for c in (_clean_hs(x) for x in v) if c]
        return v


class _BaseRequirement(_Base):
    title: str
    nature: Literal["obligation", "prohibition", "right"]
    summary: str
    legal_quote_ru: str | None = None
    # UZ-ветка гейта (решение 13.07.2026): дословная узбекская цитата + страница,
    # по которой её сверять (приложения ПКМ публикуются только на UZ-странице акта).
    # Дедуп-ключ по-прежнему считается от act.lexuz_url — verify_url только для сверки.
    legal_quote_uz: str | None = None
    verify_url: str | None = None
    act: ActRef
    unit: str | None = None
    edition_date: str | None = None
    addressees: list[str] = []
    agency: str | None = None
    how_to: list[HowToStep] = []
    documents: list[DocumentItem] = []

    @field_validator("documents", mode="before")
    @classmethod
    def _drop_empty_documents(cls, v):
        # реальные отчёты: [{"name": null, "where": null}] = «документов нет»
        if isinstance(v, list):
            return [d for d in v if not (isinstance(d, dict) and not d.get("name"))]
        return v
    sanction: Sanction | None = None
    discovered_via: str | None = None
    needs_review: bool = False
    # Фаза 2 UZ-first: язык витринных полей карточки (title/summary/how_to/documents).
    # DR-отчёты сегодня русские → дефолт "ru"; gap-ресёрчер фазы 3 ставит "uz",
    # тогда RU-строки генерируются переводом (translation_origin='machine').
    content_lang: Literal["ru", "uz"] = "ru"


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

    @field_validator("hs_code", mode="before")
    @classmethod
    def _normalize_hs(cls, v):
        return _clean_hs(v)

    @field_validator("ikpu", mode="before")
    @classmethod
    def _drop_null_ikpu(cls, v):
        # реальные отчёты: ikpu=[null] = «код не найден»
        if isinstance(v, list):
            return [c for c in v if c]
        return v
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

    @field_validator("okved", mode="before")
    @classmethod
    def _clean_okved(cls, v):
        # реальные отчёты: «47.91 Розничная торговля через …» → «47.91»
        # (чек-констрейнт services_oked_code_check пускает только код)
        if isinstance(v, str):
            import re
            m = re.match(r"\s*(\d{2}(?:\.\d{1,2}){0,2})", v)
            if m:
                return m.group(1)
        return v


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
