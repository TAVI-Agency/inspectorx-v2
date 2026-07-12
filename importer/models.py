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
