"""Eval golden set (Задача 28, ADR-0003 «Блок 2», СТОП-ТОЧКА ②).

## Почему отдельный модуль, а не новый режим `importer/evalharness.py`

`importer/evalharness.py` — рубрика §4 handoff-research-loop (12.07.2026,
`research-loop/DECISIONS.md`): оценивает КАЧЕСТВО ОТЧЁТОВ deep research
ДО импорта (`schema_valid`, `section_coverage`, `citation_pass_rate`,
`cross_model_agreement` двух прогонов одного отчёта) — вход: файл отчёта на
диске, домен: продуктовые/сервисные секции рамки (`PRODUCT_SECTIONS`/
`SERVICE_STAGES`). Этот модуль оценивает КАЧЕСТВО GENERIC-АГЕНТОВ
Build-конвейера (Retriever/Verifier/Classifier, `agents.py`) на кураторском
golden-наборе ПОСЛЕ того, как карточки уже опубликованы — вход: YAML golden
set + живые `LegalXClient`/`AgentLLMClient`, домен: реквизиты акта, санкции,
категории NTM, даты ЖЦ. Общего кода по существу нет (разные структуры
данных, разные источники входа, разные потребители результата — research-
loop инструментарий vs Build-гейт ②) — совмещение в одном модуле означало бы
либо развилку по несвязанным веткам, либо натягивание чужой рубрики на
несовместимые метрики. Решение: отдельный модуль, `evalharness.py` не
трогаем (см. отчёт задачи).

## Что мерим — 4 роли конвейера, каждая через РЕАЛЬНЫЙ generic-агент agents.py

- **retrieval_hit** (`Retriever`): нашёл ли `LegalXClient.search_norms` по
  `canonical_question` фрагмент, чьи (акт, статья) совпадают с golden
  `source_act` — сравнение с толерантностью к формату (`source_acts_match`
  ниже: разная пунктуация, ведущая нумерация актов, суффиксы дедупа пункта).
  Айтемы БЕЗ `source_act` (реальный пробел контента — «Источник не указан»,
  см. `scripts/generate_golden_set.py`) исключены из знаменателя hit-rate —
  отдельный счётчик `no_source_act`.
- **verifier_agreement** (`Verifier`): pass на ПРАВИЛЬНОМ фрагменте этого
  айтема, fail на ПОДЛОЖНОМ (фрагмент другого айтема golden-набора,
  соседнего по списку). Фрагмент/источник для Verifier'а строятся из
  собственных полей golden-айтема (`expected_item` + `source_act`) — не из
  результата Retriever'а: agreement обязан быть измерим ДАЖЕ когда retrieval
  промахнулся (большинство айтемов на моке, см. `docs/…task-28-brief.md`).
- **category_accuracy** (`Classifier`, профиль `steps_classify.CLASSIFY_PROFILE`):
  предсказанный `category_slug` по `expected_item` против golden `category_slug`.
- **lifecycle_date_accuracy** (`Classifier`, профиль
  `steps_scope_lifecycle.LIFECYCLE_PROFILE`): предсказанные даты ЖЦ по
  `expected_item` против golden `lifecycle_dates` — доля из 3 полей,
  совпавших ровно. Сейчас ВСЕ golden-даты `null` (в БД 03.08.2026 ни у
  одного published-требования нет дат ЖЦ) — метрика тривиальна, пока
  конвейер не начнёт давать реальные даты (см. отчёт задачи).

## `HeuristicBaselineLLM` — заглушка ТОЛЬКО для baseline.json (backend='mock')

Живого LLM-ключа в контуре нет (тот же принцип отсрочки, что и везде в
Build — `importer/build/llm_client.py`, `_default_llm_runner` в
`steps_norm.py`/`steps_classify.py`/`steps_scope_lifecycle.py`). Юнит-тесты
этого модуля используют `ScriptedLLM`-паттерн (`test_agents.py`) с ПОЛНЫМ
контролем ответов — никакой эвристики там нет. Но Шаг 3 брифа требует
прогнать eval «на моках» и зафиксировать `baseline.json` — а без ЛЮБОГО
`AgentLLMClient` `Retriever`/`Verifier`/`Classifier` вызвать нельзя. Вместо
падения `NotImplementedError` (как у остальных `_default_llm_runner`, где
CLI-команда просто недоступна до живого ключа) здесь заглушка ОТВЕЧАЕТ —
но не семантикой, а механическим пересечением слов (тот же грубый приём,
что `legalx_mock.py` уже применяет к поиску, и та же оговорка: «контракт от
качества ранжирования не зависит»). `baseline.json` несёт `backend='mock'`
ИМЕННО поэтому: числа в нём — smoke-проверка, что вся цепочка
golden→агент→метрика работает end-to-end, а не оценка качества LLM
(LLM в baseline вообще не участвует). Настоящая оценка verifier_agreement/
category_accuracy — с живым LLM (Задача 42, гейт D1); численно она
УЖЕ должна начинаться с чистого листа, `baseline.json` — не ориентир
качества, только регресс-сигнал самого харнесса между прогонами.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

import yaml

from importer.build.agents import (
    Classifier,
    ModelsConfig,
    Retriever,
    Verifier,
    load_models_config,
    verifier_model_for,
)
from importer.build.legalx import LegalXClient
from importer.build.llm_client import AgentLLMClient, AgentLLMError
from importer.build.profiles import Profile
from importer.build.steps_classify import CLASSIFY_PROFILE
from importer.build.steps_scope_lifecycle import LIFECYCLE_PROFILE

# Те же 3 датовых поля, что `steps_scope_lifecycle._LIFECYCLE_DATE_FIELDS` —
# не импортируем приватную константу другого модуля, дублируем один tuple
# (репутационный контракт `LIFECYCLE_PROFILE.response_schema` и так фиксирует
# ровно эти три плюс `repealed_by_ref`, который golden set не несёт).
_LIFECYCLE_DATE_FIELDS = ("effective_from", "transition_until", "valid_to")

# ══════════════════════════════════════════════════════════════════════════
# Golden set — модель данных + загрузка YAML (`generate_golden_set.py`)
# ══════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class SourceAct:
    act: str | None
    article: str | None


@dataclass(frozen=True)
class LifecycleDates:
    effective_from: str | None
    transition_until: str | None
    valid_to: str | None

    def as_dict(self) -> dict:
        return {
            "effective_from": self.effective_from,
            "transition_until": self.transition_until,
            "valid_to": self.valid_to,
        }


@dataclass(frozen=True)
class GoldenOrigin:
    requirement_id: str
    kind: str | None
    code: str | None
    name: str | None


@dataclass(frozen=True)
class GoldenItem:
    id: str
    expected_item: str
    category_slug: str | None
    canonical_question: str
    source_act: SourceAct
    lifecycle_dates: LifecycleDates
    sanction_article: str | None
    origin: GoldenOrigin


def _golden_item_from_dict(raw: dict) -> GoldenItem:
    source_act = raw.get("source_act") or {}
    lifecycle = raw.get("lifecycle_dates") or {}
    origin = raw.get("origin") or {}
    return GoldenItem(
        id=raw["id"],
        expected_item=raw["expected_item"],
        category_slug=raw.get("category_slug"),
        canonical_question=raw["canonical_question"],
        source_act=SourceAct(act=source_act.get("act"), article=source_act.get("article")),
        lifecycle_dates=LifecycleDates(
            effective_from=lifecycle.get("effective_from"),
            transition_until=lifecycle.get("transition_until"),
            valid_to=lifecycle.get("valid_to"),
        ),
        sanction_article=raw.get("sanction_article"),
        origin=GoldenOrigin(
            requirement_id=origin.get("requirement_id"),
            kind=origin.get("kind"),
            code=origin.get("code"),
            name=origin.get("name"),
        ),
    )


def load_golden_set(path: Path) -> list[GoldenItem]:
    """Загружает golden-набор из YAML (`importer/golden/golden_set.yaml`,
    формат — `scripts/generate_golden_set.py`). Порядок `items` сохраняется —
    важно для `verifier_agreement_for_item` (подложный фрагмент — сосед по
    списку, см. докстринг модуля)."""
    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    return [_golden_item_from_dict(item) for item in doc["items"]]


# ══════════════════════════════════════════════════════════════════════════
# Сравнение реквизитов с толерантностью к формату (retrieval_hit)
# ══════════════════════════════════════════════════════════════════════════

# Номер после "№" — самый однозначный сигнал (постановления/законы с явным
# номером: "Постановление ... №149 от 02.04.2022"). Пробуем ПЕРВЫМ, иначе
# regex ниже мог бы по ошибке зацепить "от 02" (день даты) как номер акта.
_ACT_NUMBER_SIGN_RE = re.compile(r"№\s*(\d+)")
# Слитный код-аббревиатура без "№" ("ПКМ-290", "ЗРУ-701", "УП-13") — буквы
# ОГРАНИЧЕНЫ 2–4 символами и требуют пробел/дефис ПЕРЕД цифрой, чтобы не
# зацепить случайный предлог перед датой ("... от 14.07.2021").
_ACT_CODE_RE = re.compile(r"\b([a-zа-яё]{2,4})[\s-]+(\d+)\b", re.IGNORECASE)
_PAREN_SUFFIX_RE = re.compile(r"\(.*?\)")
_LEADING_ENUM_RE = re.compile(r"^\d+\.\s*")
_DIGITS_RE = re.compile(r"\d+")
_WHITESPACE_RE = re.compile(r"\s+")


def normalize_act(act: str | None) -> str | None:
    """Нормализует заголовок акта до сравнимого ключа — см. докстринг
    модуля и `_ACT_NUMBER_SIGN_RE`/`_ACT_CODE_RE` про порядок приоритета."""
    if not act:
        return None
    s = _LEADING_ENUM_RE.sub("", act.strip().lower())
    m = _ACT_NUMBER_SIGN_RE.search(s)
    if m:
        return f"№{m.group(1)}"
    m = _ACT_CODE_RE.search(s)
    if m:
        return f"{m.group(1)}{m.group(2)}"
    return _WHITESPACE_RE.sub(" ", s).strip() or None


def normalize_article(article: str | None) -> str | None:
    """Нормализует ссылку на статью/пункт. Числовые пункты («п. 33»,
    «п. 35 (37b7)» — суффикс дедупа в скобках снимается) сравниваются по
    номеру. Текстовые дескрипторы без номера («обязательная маркировка») —
    по нормализованному тексту целиком; совпадают только со строго таким же
    текстовым дескриптором (см. докстринг модуля: для карточек без
    номерного пункта точное сравнение реквизитов структурно недостижимо —
    известное ограничение, не баг)."""
    if not article:
        return None
    s = _PAREN_SUFFIX_RE.sub("", article).strip().lower()
    m = _DIGITS_RE.search(s)
    if m:
        return f"#{m.group(0)}"
    normalized = _WHITESPACE_RE.sub(" ", s).strip()
    return normalized or None


def source_acts_match(a: SourceAct, b: SourceAct) -> bool:
    act_a, act_b = normalize_act(a.act), normalize_act(b.act)
    art_a, art_b = normalize_article(a.article), normalize_article(b.article)
    if act_a is None or act_b is None or art_a is None or art_b is None:
        return False
    return act_a == act_b and art_a == art_b


# ══════════════════════════════════════════════════════════════════════════
# retrieval_hit — через РЕАЛЬНЫЙ Retriever (agents.py)
# ══════════════════════════════════════════════════════════════════════════

RetrievalOutcome = Literal["hit", "miss", "no_source_act", "error"]

RETRIEVAL_PROFILE = Profile(
    name="norm",
    system_prompt=(
        "Ты ищешь норму права, которая отвечает на канонический вопрос "
        "golden-набора Задачи 28."
    ),
    response_schema={"type": "object"},
    tier="mid",
)


@dataclass
class RetrievalResult:
    item_id: str
    outcome: RetrievalOutcome
    error: str | None = None


def retrieval_hit_for_item(
    item: GoldenItem,
    legalx: LegalXClient,
    llm: AgentLLMClient,
    *,
    jurisdiction: str = "UZ",
    models: ModelsConfig | None = None,
) -> RetrievalResult:
    if item.source_act.act is None or item.source_act.article is None:
        return RetrievalResult(item_id=item.id, outcome="no_source_act")
    try:
        result = Retriever(legalx, llm, models).run(item.canonical_question, jurisdiction, RETRIEVAL_PROFILE)
    except AgentLLMError as exc:
        return RetrievalResult(item_id=item.id, outcome="error", error=str(exc))

    if result.outcome != "found":
        return RetrievalResult(item_id=item.id, outcome="miss")
    hit = any(
        source_acts_match(item.source_act, SourceAct(act=f.act_title, article=f.article_ref))
        for f in result.fragments
    )
    return RetrievalResult(item_id=item.id, outcome="hit" if hit else "miss")


# ══════════════════════════════════════════════════════════════════════════
# verifier_agreement — через РЕАЛЬНЫЙ Verifier (agents.py)
# ══════════════════════════════════════════════════════════════════════════

VERIFY_PROFILE = Profile(
    name="norm",
    system_prompt=(
        "Ты независимо проверяешь, действительно ли фрагмент отвечает на "
        "канонический вопрос golden-набора Задачи 28 и не противоречит "
        "источнику."
    ),
    response_schema={"type": "object"},
    tier="mid",
)


def _item_fragment_text(item: GoldenItem) -> str:
    """Синтетический текст фрагмента из СОБСТВЕННЫХ полей golden-айтема —
    не из результата Retriever'а (см. докстринг модуля: agreement обязан
    быть измерим даже при промахе retrieval)."""
    act = item.source_act.act or "источник не указан"
    article = item.source_act.article or "?"
    return f"{item.expected_item} ({act}, {article})"


def _item_source_text(item: GoldenItem) -> str:
    act = item.source_act.act or "источник не указан"
    article = item.source_act.article or "?"
    return f"{act}, {article}"


def _pick_decoy(items: list[GoldenItem], index: int) -> GoldenItem:
    """Подложный айтем для verifier_agreement — ближайший СЛЕДУЮЩИЙ по
    списку (с обёрткой по кругу), чей `source_act` (акт И статья) реально
    ОТЛИЧАЕТСЯ от текущего. Наивное «просто следующий по индексу» иногда
    подставляло бы фактически ТУ ЖЕ цитату: несколько процедурных карточек
    golden-набора (напр. customs-шаги растаможки) делят один и тот же пункт
    ПКМ-290 («п. 24») — тогда «подложный» фрагмент был бы неотличим от
    настоящего не по вине Verifier'а, а по конструкции golden-набора. Если у
    ВСЕХ айтемов сета один и тот же `source_act` (вырожденный случай) —
    возвращает соседа по индексу, agreement в этом случае структурно
    неизмерим, это ожидаемо."""
    n = len(items)
    current = (normalize_act(items[index].source_act.act), normalize_article(items[index].source_act.article))
    for offset in range(1, n):
        candidate = items[(index + offset) % n]
        pair = (normalize_act(candidate.source_act.act), normalize_article(candidate.source_act.article))
        if pair != current:
            return candidate
    return items[(index + 1) % n]


@dataclass
class VerifierAgreementResult:
    item_id: str
    decoy_item_id: str
    correct_passed: bool | None
    substituted_passed: bool | None
    error: str | None = None

    @property
    def agreement(self) -> bool | None:
        if self.correct_passed is None or self.substituted_passed is None:
            return None
        return self.correct_passed and not self.substituted_passed


def verifier_agreement_for_item(
    item: GoldenItem,
    decoy: GoldenItem,
    llm: AgentLLMClient,
    *,
    models: ModelsConfig | None = None,
) -> VerifierAgreementResult:
    models = models or load_models_config()
    producer_model = models.tiers[VERIFY_PROFILE.tier]
    verifier = Verifier(llm=llm, model=verifier_model_for(producer_model, models))

    try:
        correct_verdict = verifier.run(
            question=item.canonical_question,
            fragment=_item_fragment_text(item),
            source=_item_source_text(item),
            profile=VERIFY_PROFILE,
        )
        substituted_verdict = verifier.run(
            question=item.canonical_question,
            fragment=_item_fragment_text(decoy),  # ПОДЛОЖНЫЙ фрагмент — другой айтем сета
            source=_item_source_text(item),
            profile=VERIFY_PROFILE,
        )
    except AgentLLMError as exc:
        return VerifierAgreementResult(
            item_id=item.id, decoy_item_id=decoy.id,
            correct_passed=None, substituted_passed=None, error=str(exc),
        )

    return VerifierAgreementResult(
        item_id=item.id, decoy_item_id=decoy.id,
        correct_passed=correct_verdict.passed, substituted_passed=substituted_verdict.passed,
    )


# ══════════════════════════════════════════════════════════════════════════
# category_accuracy — через РЕАЛЬНЫЙ Classifier + профиль steps_classify.py
# ══════════════════════════════════════════════════════════════════════════


@dataclass
class CategoryResult:
    item_id: str
    predicted: str | None
    expected: str | None
    correct: bool | None
    error: str | None = None


def _category_profile(valid_slugs: list[str]) -> Profile:
    """Тот же приём, что `ClassifyStep._make_profile` (`steps_classify.py`):
    живой список слагов дописывается в системный промпт, а не хардкодится."""
    system_prompt = f"{CLASSIFY_PROFILE.system_prompt}\n\nДоступные коды категорий: {', '.join(valid_slugs)}"
    return Profile(
        name=CLASSIFY_PROFILE.name, system_prompt=system_prompt,
        response_schema=CLASSIFY_PROFILE.response_schema, tier=CLASSIFY_PROFILE.tier,
    )


def category_accuracy_for_item(
    item: GoldenItem,
    llm: AgentLLMClient,
    valid_slugs: list[str],
    *,
    models: ModelsConfig | None = None,
) -> CategoryResult:
    if item.category_slug is None:
        return CategoryResult(item_id=item.id, predicted=None, expected=None, correct=None)
    try:
        result = Classifier(llm, models).run(item.expected_item, _category_profile(valid_slugs))
    except AgentLLMError as exc:
        return CategoryResult(item_id=item.id, predicted=None, expected=item.category_slug, correct=None, error=str(exc))
    predicted = result.get("category_slug")
    return CategoryResult(
        item_id=item.id, predicted=predicted, expected=item.category_slug,
        correct=predicted == item.category_slug,
    )


# ══════════════════════════════════════════════════════════════════════════
# lifecycle_date_accuracy — через РЕАЛЬНЫЙ Classifier + профиль steps_scope_lifecycle.py
# ══════════════════════════════════════════════════════════════════════════


@dataclass
class LifecycleResult:
    item_id: str
    predicted: dict | None
    expected: dict
    field_accuracy: float | None  # доля из 3 полей, совпавших ровно
    exact_match: bool | None
    error: str | None = None


def lifecycle_date_accuracy_for_item(
    item: GoldenItem,
    llm: AgentLLMClient,
    *,
    models: ModelsConfig | None = None,
) -> LifecycleResult:
    expected = item.lifecycle_dates.as_dict()
    try:
        raw = Classifier(llm, models).run(item.expected_item, LIFECYCLE_PROFILE)
    except AgentLLMError as exc:
        return LifecycleResult(item_id=item.id, predicted=None, expected=expected,
                                field_accuracy=None, exact_match=None, error=str(exc))

    predicted = {f: raw.get(f) for f in _LIFECYCLE_DATE_FIELDS}
    matches = sum(1 for f in _LIFECYCLE_DATE_FIELDS if predicted.get(f) == expected.get(f))
    return LifecycleResult(
        item_id=item.id, predicted=predicted, expected=expected,
        field_accuracy=matches / len(_LIFECYCLE_DATE_FIELDS),
        exact_match=matches == len(_LIFECYCLE_DATE_FIELDS),
    )


# ══════════════════════════════════════════════════════════════════════════
# Агрегация + отчёт (таблица по ролям + JSON) + дельта против baseline.json
# ══════════════════════════════════════════════════════════════════════════


def _rate(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


@dataclass
class AggregateMetrics:
    total_items: int
    retrieval_hit_rate: float | None
    retrieval_hits: int
    retrieval_misses: int
    retrieval_no_source_act: int
    retrieval_errors: int
    verifier_agreement_rate: float | None
    verifier_accept_correct_rate: float | None
    verifier_reject_substituted_rate: float | None
    verifier_errors: int
    category_accuracy: float | None
    category_measured: int
    category_errors: int
    lifecycle_date_field_accuracy: float | None
    lifecycle_date_exact_match_rate: float | None
    lifecycle_errors: int

    def to_dict(self) -> dict:
        return {
            "total_items": self.total_items,
            "retrieval_hit_rate": self.retrieval_hit_rate,
            "retrieval_hits": self.retrieval_hits,
            "retrieval_misses": self.retrieval_misses,
            "retrieval_no_source_act": self.retrieval_no_source_act,
            "retrieval_errors": self.retrieval_errors,
            "verifier_agreement_rate": self.verifier_agreement_rate,
            "verifier_accept_correct_rate": self.verifier_accept_correct_rate,
            "verifier_reject_substituted_rate": self.verifier_reject_substituted_rate,
            "verifier_errors": self.verifier_errors,
            "category_accuracy": self.category_accuracy,
            "category_measured": self.category_measured,
            "category_errors": self.category_errors,
            "lifecycle_date_field_accuracy": self.lifecycle_date_field_accuracy,
            "lifecycle_date_exact_match_rate": self.lifecycle_date_exact_match_rate,
            "lifecycle_errors": self.lifecycle_errors,
        }


def _aggregate(
    total_items: int,
    retrieval: list[RetrievalResult],
    verifier: list[VerifierAgreementResult],
    category: list[CategoryResult],
    lifecycle: list[LifecycleResult],
) -> AggregateMetrics:
    hits = sum(1 for r in retrieval if r.outcome == "hit")
    misses = sum(1 for r in retrieval if r.outcome == "miss")
    no_source = sum(1 for r in retrieval if r.outcome == "no_source_act")
    retrieval_errors = sum(1 for r in retrieval if r.outcome == "error")

    v_measured = [v for v in verifier if v.error is None]
    verifier_errors = len(verifier) - len(v_measured)
    agreements = sum(1 for v in v_measured if v.agreement)
    accepts_correct = sum(1 for v in v_measured if v.correct_passed)
    rejects_substituted = sum(1 for v in v_measured if v.substituted_passed is False)

    c_measured = [c for c in category if c.correct is not None]
    category_errors = sum(1 for c in category if c.error is not None)
    category_correct = sum(1 for c in c_measured if c.correct)

    lc_measured = [lc for lc in lifecycle if lc.field_accuracy is not None]
    lifecycle_errors = sum(1 for lc in lifecycle if lc.error is not None)
    field_acc_sum = sum(lc.field_accuracy for lc in lc_measured)
    exact_matches = sum(1 for lc in lc_measured if lc.exact_match)

    return AggregateMetrics(
        total_items=total_items,
        retrieval_hit_rate=_rate(hits, hits + misses),
        retrieval_hits=hits, retrieval_misses=misses,
        retrieval_no_source_act=no_source, retrieval_errors=retrieval_errors,
        verifier_agreement_rate=_rate(agreements, len(v_measured)),
        verifier_accept_correct_rate=_rate(accepts_correct, len(v_measured)),
        verifier_reject_substituted_rate=_rate(rejects_substituted, len(v_measured)),
        verifier_errors=verifier_errors,
        category_accuracy=_rate(category_correct, len(c_measured)),
        category_measured=len(c_measured), category_errors=category_errors,
        lifecycle_date_field_accuracy=_rate(field_acc_sum, len(lc_measured)) if lc_measured else None,
        lifecycle_date_exact_match_rate=_rate(exact_matches, len(lc_measured)),
        lifecycle_errors=lifecycle_errors,
    )


def _fmt(rate: float | None) -> str:
    return "—" if rate is None else f"{rate:.0%}"


def _build_markdown(backend: str, metrics: AggregateMetrics, delta: dict[str, float | None] | None) -> str:
    lines = [
        f"# Eval golden set — backend={backend}",
        "",
        f"Всего айтемов: {metrics.total_items}",
        "",
        "| Роль (агент) | Метрика | Значение |",
        "|---|---|---|",
        f"| Retriever | retrieval_hit_rate ({metrics.retrieval_hits}/{metrics.retrieval_hits + metrics.retrieval_misses}, "
        f"no_source_act={metrics.retrieval_no_source_act}, errors={metrics.retrieval_errors}) | {_fmt(metrics.retrieval_hit_rate)} |",
        f"| Verifier | verifier_agreement_rate (errors={metrics.verifier_errors}) | {_fmt(metrics.verifier_agreement_rate)} |",
        f"| Verifier | accept_correct_rate | {_fmt(metrics.verifier_accept_correct_rate)} |",
        f"| Verifier | reject_substituted_rate | {_fmt(metrics.verifier_reject_substituted_rate)} |",
        f"| Classifier (category) | category_accuracy ({metrics.category_measured} измерено, errors={metrics.category_errors}) | {_fmt(metrics.category_accuracy)} |",
        f"| Classifier (lifecycle) | lifecycle_date_field_accuracy | {_fmt(metrics.lifecycle_date_field_accuracy)} |",
        f"| Classifier (lifecycle) | lifecycle_date_exact_match_rate (errors={metrics.lifecycle_errors}) | {_fmt(metrics.lifecycle_date_exact_match_rate)} |",
    ]
    if delta is not None:
        lines += ["", "## Дельта против baseline.json", "", "| Метрика | было | стало | Δ |", "|---|---|---|---|"]
        for key, d in delta.items():
            if d is None:
                continue
            lines.append(f"| {key} | {_fmt(d['baseline'])} | {_fmt(d['current'])} | {d['delta']:+.0%} |")
    return "\n".join(lines) + "\n"


_DELTA_METRICS = (
    "retrieval_hit_rate", "verifier_agreement_rate", "category_accuracy",
    "lifecycle_date_field_accuracy", "lifecycle_date_exact_match_rate",
)


def compute_delta(current: AggregateMetrics, baseline: dict) -> dict[str, dict | None]:
    """Дельта по метрикам, для которых есть значение и сейчас, и в baseline
    (`None` в любой стороне -> запись `None`, не участвует в выводе)."""
    current_dict = current.to_dict()
    delta: dict[str, dict | None] = {}
    for key in _DELTA_METRICS:
        cur = current_dict.get(key)
        base = baseline.get(key)
        if cur is None or base is None:
            delta[key] = None
            continue
        delta[key] = {"baseline": base, "current": cur, "delta": cur - base}
    return delta


@dataclass
class EvalReport:
    backend: str
    generated_at: str
    metrics: AggregateMetrics
    retrieval: list[RetrievalResult] = field(default_factory=list)
    verifier: list[VerifierAgreementResult] = field(default_factory=list)
    category: list[CategoryResult] = field(default_factory=list)
    lifecycle: list[LifecycleResult] = field(default_factory=list)
    markdown: str = ""

    def to_json_dict(self) -> dict:
        return {
            "backend": self.backend,
            "generated_at": self.generated_at,
            **self.metrics.to_dict(),
        }


def run_eval(
    items: list[GoldenItem],
    *,
    legalx: LegalXClient,
    llm: AgentLLMClient,
    valid_category_slugs: list[str],
    jurisdiction: str = "UZ",
    models: ModelsConfig | None = None,
    backend: str = "mock",
    baseline: dict | None = None,
) -> EvalReport:
    """Прогоняет golden-набор через РЕАЛЬНЫЕ generic-агенты `agents.py`
    (см. докстринг модуля) и агрегирует 4 метрики по ролям."""
    models = models or load_models_config()

    retrieval = [
        retrieval_hit_for_item(item, legalx, llm, jurisdiction=jurisdiction, models=models)
        for item in items
    ]
    verifier = [
        verifier_agreement_for_item(item, _pick_decoy(items, i), llm, models=models)
        for i, item in enumerate(items)
    ] if len(items) > 1 else []
    category = [category_accuracy_for_item(item, llm, valid_category_slugs, models=models) for item in items]
    lifecycle = [lifecycle_date_accuracy_for_item(item, llm, models=models) for item in items]

    metrics = _aggregate(len(items), retrieval, verifier, category, lifecycle)
    delta = compute_delta(metrics, baseline) if baseline is not None else None
    markdown = _build_markdown(backend, metrics, delta)

    return EvalReport(
        backend=backend,
        generated_at=datetime.now(timezone.utc).isoformat(),
        metrics=metrics,
        retrieval=retrieval, verifier=verifier, category=category, lifecycle=lifecycle,
        markdown=markdown,
    )


# ══════════════════════════════════════════════════════════════════════════
# HeuristicBaselineLLM — заглушка ТОЛЬКО для baseline.json (см. докстринг модуля)
# ══════════════════════════════════════════════════════════════════════════

_WORD_RE = re.compile(r"[\w']+", re.UNICODE)


def _words(text: str) -> set[str]:
    return set(_WORD_RE.findall(text.lower()))


_CATEGORY_KEYWORDS: dict[str, tuple[str, ...]] = {
    "sps": ("санитар", "эпидемиолог", "пищев", "медосмотр", "haccp", "санпин"),
    "marking": ("маркиров", "этикет", "упаковк", "предупрежд", "цифровой"),
    "licensing": ("лицензи", "разрешен", "фарминспекц"),
    "fiscal": ("налог", "ккм", "касс", "пошлин"),
    "currency": ("валют", "контракт", "предоплат", "еэисво"),
    "customs": ("таможен", "декларац", "досмотр", "пропуск"),
    "origin": ("происхожден",),
    "tbt": ("техническ", "регламент", "сертифика", "смол", "никотин", "ингредиент", "сигарет"),
}


def _extract_between(text: str, start_marker: str, end_marker: str | None) -> str:
    start = text.find(start_marker)
    if start < 0:
        return ""
    start += len(start_marker)
    end = text.find(end_marker, start) if end_marker else -1
    return text[start:end if end >= 0 else None].strip()


class HeuristicBaselineLLM:
    """Заглушка `AgentLLMClient` без семантики — см. докстринг модуля
    («Почему baseline вообще может ответить без живого LLM-ключа»).
    Диспетчеризация по МАРКЕРАМ, которые сами `Retriever.run`/`Verifier.run`/
    `Classifier.run` (agents.py) кладут в промпт (см. их исходники) —
    заглушка ничего не придумывает про формат промпта, только читает его."""

    def complete(self, prompt: str, model: str) -> str:
        if "Исходный запрос:" in prompt:  # Retriever._reformulate_or_signal_no_norm
            return json.dumps({"no_norm": True})
        if "Фрагмент:" in prompt and "Источник:" in prompt:  # Verifier.run
            return self._verify(prompt)
        if '"category_slug"' in prompt:  # Classifier.run, профиль category
            return self._classify_category(prompt)
        if '"effective_from"' in prompt:  # Classifier.run, профиль lifecycle
            return json.dumps({
                "effective_from": None, "transition_until": None,
                "valid_to": None, "repealed_by_ref": None,
            })
        raise AgentLLMError(f"HeuristicBaselineLLM: неопознанный тип промпта: {prompt[:120]!r}")

    @staticmethod
    def _verify(prompt: str) -> str:
        """`passed` = нормализованный `source` (акт+статья, «Источник:» в
        промпте Verifier'а) буквально ВЛОЖЕН в `fragment` — не дробное
        пересечение слов (было в первой версии): дробный overlap ложно
        засчитывал совпадение почти для ЛЮБОЙ пары табачных айтемов golden-
        набора, потому что все они делят токены заголовка акта «ПКМ-290,
        ТР» — различалась только цифра статьи, которая тонет в общей массе
        совпавших слов. Точное вложение реагирует именно на различие
        статьи (см. `_pick_decoy` в `eval_golden.py` — тот же принцип)."""
        fragment = _extract_between(prompt, "Фрагмент:", "Источник:")
        source = _extract_between(prompt, "Источник:", "\n\n")
        normalized_source = _WHITESPACE_RE.sub(" ", source.strip().lower())
        normalized_fragment = _WHITESPACE_RE.sub(" ", fragment.strip().lower())
        passed = bool(normalized_source) and normalized_source in normalized_fragment
        return json.dumps({"passed": passed, "reason": "эвристика: source вложен в fragment" if passed else "эвристика: source не найден в fragment"})

    @staticmethod
    def _classify_category(prompt: str) -> str:
        text = _extract_between(prompt, "Текст:", "\n\n")
        words = _words(text)
        best_slug, best_score = None, 0
        for slug, keywords in _CATEGORY_KEYWORDS.items():
            score = sum(1 for kw in keywords if any(kw in w for w in words))
            if score > best_score:
                best_slug, best_score = slug, score
        return json.dumps({"category_slug": best_slug or "tbt"})
