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
    # реальные отчёты пишут и по-русски
    "производитель": "producer", "изготовитель": "producer",
    "импортёр": "importer", "импортер": "importer",
    "экспортёр": "exporter", "экспортер": "exporter",
    "продавец": "seller", "ритейлер": "seller", "розничный продавец": "seller",
    "перевозчик": "carrier",
    "владелец": "all", "предприниматель": "all", "бизнес": "all", "все": "all",
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
