"""Eval-харнесс отчётов deep research по рубрике handoff-research-loop §4.

Рубрика зафиксирована 12.07.2026, меняется только через research-loop/DECISIONS.md:
schema_valid, section_coverage, citation_pass_rate (из гейта), field_completeness,
needs_review_rate, cross_model_agreement, verified-карточек/час (процессная, вне модуля).
"""
from dataclasses import dataclass, field
from pathlib import Path

from importer.dedup import external_key
from importer.parser import ReportParseError, load_report_file, parse_report
from importer.refs import lexuz_doc_id, parse_unit_ref

PRODUCT_SECTIONS = ["product", "realization", "import", "export",
                    "transit", "re_export", "re_import"]
SERVICE_STAGES = ["start", "premises", "operations", "inspections",
                  "changes", "termination"]


@dataclass
class FieldStats:
    unit: int = 0
    how_to: int = 0          # непустой how_to с source_act_url хотя бы у одного шага
    documents: int = 0
    sanction_sum: int = 0    # sanction с fine_bru
    complete: int = 0        # все четыре поля разом


@dataclass
class ReportScore:
    path: Path
    kind: str = ""
    slug: str = ""
    model: str = ""
    schema_valid: bool = False
    parse_error: str | None = None
    total: int = 0
    sections: dict = field(default_factory=dict)   # секция → число требований
    section_coverage: float = 0.0                  # доля секций рамки с >=1 требованием
    fields: FieldStats = field(default_factory=FieldStats)
    needs_review: int = 0
    keys: set = field(default_factory=set)         # ключи акт+пункт (как у дедупа)
    unkeyed: int = 0                               # требования без распознанного ключа

    @property
    def needs_review_rate(self) -> float:
        return self.needs_review / self.total if self.total else 0.0

    @property
    def frame(self) -> list[str]:
        return PRODUCT_SECTIONS if self.kind == "product" else SERVICE_STAGES


def requirement_key(req) -> str | None:
    """Ключ акт+пункт — та же канонизация, что у глобального дедупа."""
    doc_id = lexuz_doc_id(req.act.lexuz_url)
    ref = parse_unit_ref(req.unit)
    if doc_id and ref:
        return external_key(doc_id, ref)
    if doc_id:
        return f"lexuz:{doc_id}/?"
    return None


def score_report(path: Path) -> ReportScore:
    score = ReportScore(path=path)
    try:
        rf = load_report_file(path)
    except ValueError as exc:
        score.parse_error = str(exc)
        return score
    score.kind, score.slug, score.model = rf.kind, rf.slug, rf.model
    try:
        report = parse_report(rf)
    except ReportParseError as exc:
        score.parse_error = str(exc)
        return score
    score.schema_valid = True
    score.total = len(report.requirements)
    for section in score.frame:
        score.sections[section] = 0
    for req in report.requirements:
        section = req.type if score.kind == "product" else req.stage
        score.sections[section] = score.sections.get(section, 0) + 1
        if req.needs_review:
            score.needs_review += 1
        unit_ok = bool(req.unit)
        how_to_ok = bool(req.how_to) and any(s.source_act_url for s in req.how_to)
        documents_ok = bool(req.documents)
        sanction_ok = bool(req.sanction and req.sanction.fine_bru)
        score.fields.unit += unit_ok
        score.fields.how_to += how_to_ok
        score.fields.documents += documents_ok
        score.fields.sanction_sum += sanction_ok
        score.fields.complete += all((unit_ok, how_to_ok, documents_ok, sanction_ok))
        key = requirement_key(req)
        if key:
            score.keys.add(key)
        else:
            score.unkeyed += 1
    covered = sum(1 for s in score.frame if score.sections.get(s))
    score.section_coverage = covered / len(score.frame)
    return score


@dataclass
class Agreement:
    common: int
    only_a: int
    only_b: int

    @property
    def jaccard(self) -> float:
        union = self.common + self.only_a + self.only_b
        return self.common / union if union else 0.0


def cross_agreement(a: ReportScore, b: ReportScore) -> Agreement:
    """§4.6: доля требований, совпавших по ключу акт+пункт, между двумя прогонами."""
    common = a.keys & b.keys
    return Agreement(len(common), len(a.keys - b.keys), len(b.keys - a.keys))
