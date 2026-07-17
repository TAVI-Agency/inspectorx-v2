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
