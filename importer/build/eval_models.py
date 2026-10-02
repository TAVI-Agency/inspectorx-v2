"""Сравнение моделей на golden set (Задача 6, ночь 11.09.2026): CLI-команда
`build eval-models --set cheap=…,mid=…,expensive=… [--set ...]` прогоняет
`run_eval` (`eval_golden.py`) по каждому переданному набору тиров и
раскладывает метрики РЯДОМ, в одну markdown-таблицу.

## Почему выбор моделей делается по ДАННЫМ golden set, а не по прайсу

`models.yaml: pricing` уже даёт стоимость запроса за токен (`trace.py:
cost_report`), но не даёт качество — дешёвая модель, которая промахивается
по retrieval или пропускает Verifier на подложном фрагменте, на практике
обходится дороже дорогой модели: её ошибки уходят прямо в опубликованные
карточки. Поэтому эта команда не выбирает «лучший» набор сама и не считает
никакого сводного скора — она гоняет ОДИН и тот же `run_eval` (те же
generic-агенты, та же агрегация метрик, что и `build eval-golden`) по
нескольким наборам моделей и оставляет сравнение и решение владельцу
(утренний ревью, брифинг задачи).

## Наборы vs baseline.json

`run_eval` умеет сравнивать текущий прогон с прошлым через `baseline.json`
(`compute_delta` в `eval_golden.py`) — это дельта ОДНОГО набора моделей во
времени. Здесь сравнение другое: НЕСКОЛЬКО наборов моделей в ОДИН момент
времени, друг с другом. `run_model_sets` поэтому вызывает `run_eval` с
`baseline=None` для каждого набора — дельта каждого прогона против
baseline.json тут неуместна (наборы не привязаны к предыдущему прогону),
а сравнение между наборами делает `compare_table` ниже.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

from importer.build.agents import ModelsConfig, assert_distinct_tier_models
from importer.build.eval_golden import GoldenItem, run_eval
from importer.build.legalx import LegalXClient
from importer.build.llm_client import AgentLLMClient

# Порядок тиров в спецификации `--set` и в slug'е — тот же, что и в
# `ModelsConfig.tiers`/`models.yaml` (agents.py: `_TIERS`).
_TIERS = ("cheap", "mid", "expensive")

# Колонки итоговой markdown-таблицы сравнения наборов: метрики run_eval
# (см. `AggregateMetrics.to_dict()` в eval_golden.py) плюс отдельная сводная
# `errors` (сумма всех `*_errors` полей набора).
_METRIC_COLUMNS = (
    "retrieval_hit_rate",
    "verifier_pass_on_correct_rate",
    "verifier_fail_on_gross_decoy_rate",
    "verifier_fail_on_near_miss_decoy_rate",
    "category_accuracy",
    "lifecycle_date_field_accuracy",
)

_ERROR_FIELDS = ("retrieval_errors", "verifier_errors", "category_errors", "lifecycle_errors")

# Недопустимые для slug'а символы (всё, кроме букв/цифр/точки/дефиса) -> "-".
_SLUG_UNSAFE_RE = re.compile(r"[^A-Za-z0-9.]+")


def parse_tier_set(spec: str) -> dict[str, str]:
    """Разбирает `--set` вида `"cheap=a,mid=b,expensive=c"` в словарь тир ->
    модель. Не хватает хотя бы одного из трёх тиров (`_TIERS`) -> `ValueError`
    с именем недостающего тира в тексте (см. тест `test_parse_tier_set_ok_and_missing`).

    Две одинаковые модели в наборе — тоже `ValueError`
    (`agents.assert_distinct_tier_models`): такой набор ломает независимость
    Verifier'а (`agents.verifier_model_for` вернул бы модель producer'а), и
    метрики прогона были бы про другую систему, чем настоящий конвейер."""
    tiers: dict[str, str] = {}
    for pair in spec.split(","):
        pair = pair.strip()
        if not pair:
            continue
        key, sep, value = pair.partition("=")
        if not sep:
            raise ValueError(f"--set: не разобрана пара {pair!r}, ожидался формат tier=model")
        tiers[key.strip()] = value.strip()
    missing = [t for t in _TIERS if t not in tiers]
    if missing:
        raise ValueError(f"--set {spec!r}: не хватает тиров {missing} (ожидались {_TIERS})")
    assert_distinct_tier_models(tiers, source=f"--set {spec!r}")
    return tiers


def slug_for(tiers: dict[str, str]) -> str:
    """Имя набора для файла отчёта и колонки таблицы:
    `cheap-<модель>__mid-<модель>__expensive-<модель>`, недопустимые для
    имени файла символы модели (`/`, пробелы и т.п.) заменены на `-`."""
    parts = []
    for tier in _TIERS:
        safe_model = _SLUG_UNSAFE_RE.sub("-", tiers[tier])
        parts.append(f"{tier}-{safe_model}")
    return "__".join(parts)


def _fmt_metric(value) -> str:
    return "—" if value is None else f"{value:.2f}"


def compare_table(reports: dict[str, dict]) -> str:
    """Markdown-таблица сравнения наборов моделей: строка на набор
    (`reports` — `{slug: EvalReport.to_json_dict()}`), колонки — метрики
    `_METRIC_COLUMNS` плюс сводная `errors` (сумма `_ERROR_FIELDS`,
    отсутствующие в отчёте поля считаются нулём). Отсутствующая метрика ->
    `—`, число форматируется `%.2f`."""
    header = ["slug", *_METRIC_COLUMNS, "errors"]
    lines = [
        f"| {' | '.join(header)} |",
        f"|{'---|' * len(header)}",
    ]
    for slug, report in reports.items():
        errors = sum(report.get(field) or 0 for field in _ERROR_FIELDS)
        row = [slug, *(_fmt_metric(report.get(col)) for col in _METRIC_COLUMNS), str(errors)]
        lines.append(f"| {' | '.join(row)} |")
    return "\n".join(lines) + "\n"


def run_model_sets(
    items: list[GoldenItem],
    *,
    sets: list[dict[str, str]],
    base_config: ModelsConfig,
    legalx: LegalXClient,
    llm: AgentLLMClient,
    valid_category_slugs: list[str],
    out_dir: Path,
    jurisdiction: str = "UZ",
) -> dict[str, dict]:
    """Прогоняет `run_eval` по каждому набору тиров из `sets` (тир -> модель;
    `pricing`/`providers` берутся из `base_config` — набор меняет только
    выбор модели, не прайс и не маршрутизацию по провайдерам). Пишет JSON-
    отчёт каждого набора в `out_dir/<YYYYMMDD-HHMMSS>-<slug>.json` и
    возвращает `{slug: EvalReport.to_json_dict()}` для `compare_table`.

    `baseline=None` для каждого прогона — сравнение здесь между наборами
    (см. докстринг модуля), не с прошлым baseline.json."""
    out_dir.mkdir(parents=True, exist_ok=True)
    results: dict[str, dict] = {}
    for tiers in sets:
        slug = slug_for(tiers)
        models = ModelsConfig(tiers=tiers, pricing=base_config.pricing, providers=base_config.providers)
        report = run_eval(
            items,
            legalx=legalx,
            llm=llm,
            valid_category_slugs=valid_category_slugs,
            jurisdiction=jurisdiction,
            models=models,
            backend=f"live:{slug}",
            baseline=None,
        )
        report_dict = report.to_json_dict()
        report_path = out_dir / f"{datetime.now(timezone.utc):%Y%m%d-%H%M%S}-{slug}.json"
        report_path.write_text(json.dumps(report_dict, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        results[slug] = report_dict
    return results
