"""Шаг 'rule' Build-конвейера (ADR-0003 решение 5: «критическая точка»
Rule-maker -> Verifier; реактивация — Задача 10, Волна 2 фотоконтроля,
поправка 5 к ADR-0003).

## Роль реактивирована (09.08.2026)

Rule-maker был приостановлен поправкой 4 к ADR-0003 (06.08.2026) до этапа 6
плана фотоконтроля — этот этап наступил, но роль вернулась НЕ в прежнем виде.
Источник правды машинных правил фото-чека по-прежнему YAML-пакеты
`config/requirements/*.yaml` в `inspectorx-vision` (решение владельца по
развилке 5, `PHOTOCONTROL_DECISIONS.md`), а не таблица `requirement_rules`
(она остаётся deprecated, шаг 'load' в неё не пишет и раньше не писал).

Новая роль шага — «машина предлагает, человек утверждает»: он превращает
текст нормы в ЧЕРНОВИК атомарной проверки в формате vision-пакета и кладёт
его файлом-кандидатом в `config/requirements/candidates/` репозитория
vision, рядом со сценарной фикстурой. Ничего не мёржится автоматически ни в
пакет vision, ни тем более в базу InspectorX — `ctx.data['rules']`
по-прежнему ВСЕГДА `[]` (контракт с шагом 'load', Задача 26, не меняется),
новый выход — `ctx.data['rule_candidates']` (пути к файлам-кандидатам).

## Шаг применяется не ко всем айтемам

Машинные правила осмысленны только для категории маркировки/упаковки
(`category_slug == 'marking'`): у санитарного или таможенного требования,
например, физически нет «поля этикетки», которое можно бы проверить
фото-чеком — это норма, а не дефект. Поэтому для любой ДРУГОЙ категории
(включая отсутствие `category_slug` в контексте вовсе — например, партиальный
`rerun_item` не с начала) шаг — не fail, а осознанный no-op:
`StepResult(ok)` с пустым `ctx.data['rules'] = []` и пометкой
`ctx.data['skipped_rule_step'] = True`, ноль обращений к LLM.
`category_slug` берётся из `ctx.data` (положен туда шагом 'category',
`steps_classify.py`, который в STEP_ORDER идёт прямо перед 'rule') — НЕ из
`ctx.item.category_slug` (черновая классификация Cartographer'а из карты,
см. докстринг `steps_norm.py:_map_item_from_ctx`).

## Verifier — критическая точка (ADR-0003 решение 5)

«Кривое правило = кривой фото-чек пользователю, а не просто неточный абзац»
(ADR-0003) -> верификация здесь строже, чем у любого другого шага: не один
общий вердикт на весь список, а ОТДЕЛЬНЫЙ вызов `Verifier` на КАЖДОЕ
правило (вопрос «правило точно соответствует норме?», `fragment` — само
правило, `source` — исходный текст нормы). Правило, которое `Verifier`
отклонил, исключается; но если исключено ХОТЯ БЫ одно правило из
сгенерированного набора — весь `StepResult` уходит в `fail`, а не только
список без этого правила (консервативная политика: частично проверенный
набор — не то же самое, что подтверждённый набор целиком; выбраковывается
весь набор, ретрай ЦЕЛОГО шага делает оркестратор, не публикуется то, что
уже подтвердилось). После `MAX_STEP_RETRIES=3` провалов подряд `Orchestrator`
эскалирует айтем в `needs_attention` — обычный путь `Orchestrator._run_from`.

Все вердикты (и pass, и fail) попадают в `StepResult.verdicts` независимо
от итогового статуса шага.

## Формат кандидата

После того как Verifier подтвердил ВСЕ правила набора, каждое проходит ещё
и локальный линтер `validate_candidate` (мини-версия vision
`scripts/lint_params.py` — полный линтер прогонит CI vision по каталогу
`candidates/`); дефект линтера бракует весь набор так же, как отклонение
Verifier'а. Прошедшее правило пишется файлом
`<candidates_dir>/<item_id>-<index>.yaml`:

    candidate: true
    generated_by: build-pipeline/rule-step
    item_id: <ctx.item.id>
    requirement_title_ru: <ctx.item.expected_item>
    source: {quote_ru: <norm_fragment.content[:800]>}
    check: {id, kind, severity, group, subject, params, level, question_ru, hint_ru}
    review: "НЕ мёржить автоматически: ревью человеком, ..."

Рядом — `<item_id>-<index>-scenario.yaml`: сценарная фикстура в форме
`tests/scenarios/*.yaml` vision (Волна 1, `product`/`pack`/`cases:
[{check, level, question, pass, fail}]`, кейсы исполняет
`tests/scenario_runner.py`, который этот шаг не трогает и не дублирует).
`product`/`pack` на этом шаге конвейеру неизвестны (у `ItemContext` нет
привязки к vision-профилю товара — только `expected_item`/`category_slug`),
поэтому фикстура несёт явные TODO-плейсхолдеры: их заполняет человек при
переносе кандидата в реальный пакет, тем же движением, что мёржит сам файл
кандидата.

## Опциональный PR

`RULE_CANDIDATE_PR=1` в окружении (и наличие `gh` в PATH) — после того как
файлы кандидата уже записаны на диск, шаг пробует открыть PR в
`inspectorx-vision` (только создание ветки/коммита/PR, БЕЗ мёржа). Любая
ошибка `git`/`gh` не валит шаг — кандидат уже сохранён — а попадает
предупреждением в `ctx.data['rule_pr_warning']`.

## Почему шаг ловит исключения сам

Тот же принцип, что и в `steps_norm.py`/`steps_classify.py`:
`Orchestrator._run_from` вызывает `step_fn(ctx)` без try/except вокруг
вызова, поэтому необработанное исключение прервало бы весь `run_group`
(все айтемы прогона), а не только текущий айтем. `AgentLLMError`/
`ValueError` (мусорный ответ LLM у `Verifier`) здесь перехватываются и
превращаются в обычный `StepResult(fail)`.

## Регистрация

Тот же паттерн отсрочки, что и `steps_norm.py`/`steps_classify.py`:
`_default_llm_runner` падает `NotImplementedError` только при РЕАЛЬНОМ
вызове модели, не при импорте/регистрации шага.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

import yaml

from importer.build.agents import (
    Classifier,
    ModelsConfig,
    Verdict,
    Verifier,
    load_models_config,
    verifier_model_for,
)
from importer.build.legalx import NormFragment
from importer.build.llm_client import AgentLLMClient, AgentLLMError, RunnerAgentLLM
from importer.build.profiles import Profile
from importer.build.steps import ItemContext, StepResult, register_step

if TYPE_CHECKING:  # только тип — импорт по значению создал бы цикл steps_rule<->trace
    from importer.build.trace import Tracer

# Единственная категория, для которой машинные правила фото-чека вообще
# имеют смысл (решение контроллера задачи) — для остальных шаг skip-ok.
MARKING_CATEGORY_SLUG = "marking"

RULE_PROFILE = Profile(
    name="rule",
    system_prompt=(
        "Ты превращаешь текст нормы права о маркировке/упаковке в ЧЕРНОВИК "
        "атомарной машинной проверки для фото-чека (формат пакетов inspectorx-vision). "
        'Каждое правило — объект: {"kind": "presence|absence|text_semantic|geometry", '
        '"severity": "critical|major|minor|info", "subject": str, "params": object, '
        '"question_ru": str, "hint_ru": str}. Правил может быть несколько — по одному '
        "на каждое проверяемое условие. Ничего не придумывай: каждое правило обязано "
        "напрямую следовать из текста нормы."
    ),
    response_schema={
        "type": "object",
        "properties": {"rules": {"type": "array", "minItems": 1, "items": {"type": "object"}}},
        "required": ["rules"],
    },
    tier="mid",
)

CHECK_KINDS = {"presence", "absence", "text_semantic", "geometry"}
SEVERITIES = {"critical", "major", "minor", "info"}
DEFAULT_CANDIDATES_DIR = "/Users/abduraxmonturdiyev/inspectorx-vision/config/requirements/candidates"


def validate_candidate(check: dict) -> list[str]:
    """Локальный линтер кандидата — дефекты ловятся ДО того, как начнут
    стоить ревью-часов (мини-версия vision `scripts/lint_params.py`; полный
    линтер прогонит CI vision по каталогу `candidates/`). Возвращает список
    проблем (пустой — кандидат чист)."""
    problems = []
    if check.get("kind") not in CHECK_KINDS:
        problems.append(f"kind вне словаря: {check.get('kind')!r}")
    if check.get("severity") not in SEVERITIES:
        problems.append(f"severity вне словаря: {check.get('severity')!r}")
    if not isinstance(check.get("params"), dict):
        problems.append("params отсутствует или не объект")
    if not check.get("question_ru"):
        problems.append("нет question_ru")
    return problems


def _rules_from_maker_output(data: object) -> list[dict] | None:
    """Достаёт список правил из ответа Rule-maker'а либо `None`, если ответ
    не проходит минимальный контракт (не список / пуст / элементы — не
    объекты) — сигнал «невалидный вывод → ретрай»."""
    if isinstance(data, dict):
        candidate = data.get("rules")
    else:
        candidate = data  # на случай голого массива без обёртки {"rules": [...]}
    if not isinstance(candidate, list) or len(candidate) == 0:
        return None
    if not all(isinstance(rule, dict) for rule in candidate):
        return None
    return candidate


class RuleStep:
    """Шаговый callable 'rule' (см. докстринг модуля)."""

    def __init__(
        self,
        llm: AgentLLMClient,
        *,
        models: ModelsConfig | None = None,
        profile: Profile = RULE_PROFILE,
        tracer: "Tracer | None" = None,
    ):
        self._llm = llm
        self._models = models or load_models_config()
        self._profile = profile
        self._tracer = tracer
        self._maker = Classifier(llm, self._models, tracer=tracer)

    def __call__(self, ctx: ItemContext) -> StepResult:
        category_slug = ctx.data.get("category_slug")
        if category_slug != MARKING_CATEGORY_SLUG:
            ctx.data["rules"] = []
            ctx.data["skipped_rule_step"] = True
            return StepResult(status="ok")

        norm_fragment = ctx.data.get("norm_fragment")
        if norm_fragment is None:
            return StepResult(
                status="fail",
                error=(
                    "шаг 'rule': в item_ctx нет 'norm_fragment' — шаг 'norm' "
                    "ещё не отработал"
                ),
            )

        try:
            return self._run(ctx, norm_fragment)
        except (AgentLLMError, ValueError) as exc:
            return StepResult(status="fail", error=f"шаг 'rule': {exc}")

    def _run(self, ctx: ItemContext, norm_fragment: NormFragment) -> StepResult:
        rules = self._make_rules(norm_fragment.content, self._profile)
        if rules is None:
            retry_profile = self._profile_with_error(
                "Предыдущий ответ был невалиден: верни СТРОГО непустой "
                "JSON-массив правил по ключу 'rules'."
            )
            rules = self._make_rules(norm_fragment.content, retry_profile)
        if rules is None:
            return StepResult(
                status="fail",
                error=(
                    "шаг 'rule': Rule-maker дважды вернул невалидный вывод "
                    "(не JSON-массив непустых правил-объектов)"
                ),
            )

        producer_model = self._models.tiers[self._profile.tier]
        verifier_model = verifier_model_for(producer_model, self._models)
        verifier = Verifier(llm=self._llm, model=verifier_model, tracer=self._tracer)

        verdicts: list[Verdict] = []
        verified_rules: list[dict] = []
        any_rejected = False

        for index, rule in enumerate(rules, start=1):
            try:
                verdict = verifier.run(
                    question="Правило точно соответствует норме (не искажает и не додумывает)?",
                    fragment=json.dumps(rule, ensure_ascii=False, sort_keys=True),
                    source=norm_fragment.content,
                    profile=self._profile,
                )
            except (AgentLLMError, ValueError) as exc:
                # Исключение здесь НЕ должно долетать до внешнего
                # try/except в __call__ — тот вернул бы fail с ПУСТЫМИ
                # verdicts, стерев уже собранные к этому моменту вердикты
                # предыдущих правил (докстринг обещает «все вердикты
                # попадают в StepResult.verdicts независимо от статуса» —
                # это обязано быть правдой и при обрыве цикла на середине,
                # не только при штатном fail).
                return StepResult(
                    status="fail",
                    verdicts=verdicts,
                    error=f"шаг 'rule': verifier error on rule {index}: {exc}",
                )
            verdicts.append(verdict)
            if verdict.passed:
                verified_rules.append({"rule": rule, "verified": True})
            else:
                any_rejected = True

        if any_rejected:
            # Консервативная политика «критической точки» (ADR-0003 решение
            # 5, докстринг модуля): исключение ХОТЯ БЫ одного правила
            # бракует весь набор — не публикуем частично проверенный
            # чек-лист.
            return StepResult(
                status="fail",
                verdicts=verdicts,
                error=(
                    "шаг 'rule': верификатор отклонил хотя бы одно из "
                    f"{len(rules)} правил — весь набор бракуется"
                ),
            )

        return self._write_candidates(ctx, norm_fragment, verified_rules, verdicts)

    def _write_candidates(
        self,
        ctx: ItemContext,
        norm_fragment: NormFragment,
        verified_rules: list[dict],
        verdicts: list[Verdict],
    ) -> StepResult:
        candidates_dir = Path(os.environ.get("IXV_CANDIDATES_DIR", DEFAULT_CANDIDATES_DIR))
        candidates_dir.mkdir(parents=True, exist_ok=True)
        paths: list[str] = []
        for index, entry in enumerate(verified_rules, start=1):
            check = dict(entry["rule"])
            problems = validate_candidate(check)
            if problems:
                # Та же консервативная политика, что и у отклонения
                # Verifier'ом: дефект в ОДНОМ кандидате бракует весь набор,
                # а не только его — уже записанные на диск файлы этого же
                # набора здесь ещё не создавались (линтер идёт до write),
                # так что мусор кандидатом не становится.
                return StepResult(
                    status="fail", verdicts=verdicts,
                    error="шаг 'rule': кандидат не прошёл линтер: " + "; ".join(problems),
                )
            check.setdefault("id", f"candidate.{ctx.item.id}.{index}")
            check.setdefault("group", "candidate")
            check.setdefault("level", "consumer")
            doc = {
                "candidate": True,
                "generated_by": "build-pipeline/rule-step",
                "item_id": str(ctx.item.id),
                "requirement_title_ru": ctx.item.expected_item,
                "source": {"quote_ru": norm_fragment.content[:800]},
                "check": check,
                "review": "НЕ мёржить автоматически: ревью человеком, сценарная фикстура "
                          "(tests/scenarios/) — до переноса в пакет",
            }
            path = candidates_dir / f"{ctx.item.id}-{index}.yaml"
            path.write_text(
                yaml.safe_dump(doc, allow_unicode=True, sort_keys=False), encoding="utf-8"
            )
            fixture_path = candidates_dir / f"{ctx.item.id}-{index}-scenario.yaml"
            fixture_path.write_text(
                yaml.safe_dump(
                    self._scenario_fixture(ctx, check), allow_unicode=True, sort_keys=False
                ),
                encoding="utf-8",
            )
            paths.append(str(path))

        ctx.data["rules"] = []  # в requirement_rules по-прежнему НИЧЕГО не едет
        ctx.data["rule_candidates"] = paths
        self._maybe_open_pr(candidates_dir, ctx)
        return StepResult(status="ok", verdicts=verdicts)

    @staticmethod
    def _scenario_fixture(ctx: ItemContext, check: dict) -> dict:
        """Сценарная фикстура — ВМЕСТЕ с кандидатом (валидация «до
        предложения»): pass-набор фактов (искомая формулировка есть) и
        fail-набор (грань прочитана, формулировки нет). Ключи `cases/check/
        level/question/pass/fail/facts/text/reader` — как в
        `tests/scenarios/*.yaml` vision (Волна 1), кейсы исполняет
        `tests/scenario_runner.py`. `product`/`pack` этому шагу неизвестны
        (нет привязки item -> vision-профиль) — заполняются человеком при
        переносе кандидата в пакет."""
        hints = check.get("params", {}).get("pattern_hints") or ["<формулировка>"]
        return {
            "product": "TODO-заполнить-при-переносе-в-пакет",
            "pack": "TODO-заполнить-при-переносе-в-пакет",
            "candidate_check_id": check["id"],
            "item_id": str(ctx.item.id),
            "cases": [
                {
                    "check": check["id"],
                    "level": check.get("level", "consumer"),
                    "question": check.get("question_ru", ""),
                    "pass": {
                        "expect": "pass",
                        "facts": {
                            "text": {"verbatim": hints[0]},
                            "reader": {"faces": 1, "words": [hints[0]]},
                        },
                    },
                    "fail": {
                        "expect": "fail",
                        "facts": {
                            "text": {"found": "no"},
                            "reader": {"faces": 1, "words": ["нейтральный-текст"]},
                        },
                    },
                }
            ],
        }

    @staticmethod
    def _maybe_open_pr(candidates_dir: Path, ctx: ItemContext) -> None:
        """`RULE_CANDIDATE_PR=1` — открыть PR кандидата через `gh` (только
        создание, без мёржа). Кандидат-файл уже на диске к моменту вызова,
        поэтому ЛЮБАЯ ошибка здесь — только предупреждение в `ctx.data`, не
        провал шага (см. докстринг модуля)."""
        if os.environ.get("RULE_CANDIDATE_PR") != "1":
            return
        if shutil.which("gh") is None:
            ctx.data["rule_pr_warning"] = "шаг 'rule': RULE_CANDIDATE_PR=1, но 'gh' не найден в PATH"
            return
        vision_repo = candidates_dir.parents[2] if len(candidates_dir.parents) >= 2 else candidates_dir
        branch = f"rule-candidate-{ctx.item.id}"
        title = f"rule-candidate: {ctx.item.expected_item}"
        try:
            subprocess.run(
                ["git", "-C", str(vision_repo), "checkout", "-b", branch],
                check=True, capture_output=True, text=True,
            )
            subprocess.run(
                ["git", "-C", str(vision_repo), "add", "config/requirements/candidates"],
                check=True, capture_output=True, text=True,
            )
            subprocess.run(
                ["git", "-C", str(vision_repo), "commit", "-m", title],
                check=True, capture_output=True, text=True,
            )
            subprocess.run(
                ["gh", "pr", "create", "--title", title,
                 "--body", "машина предлагает — человек утверждает"],
                cwd=str(vision_repo), check=True, capture_output=True, text=True,
            )
        except (subprocess.SubprocessError, OSError) as exc:
            ctx.data["rule_pr_warning"] = f"шаг 'rule': не удалось открыть PR кандидата: {exc}"

    def _make_rules(self, text: str, profile: Profile) -> list[dict] | None:
        try:
            result = self._maker.run(text, profile)
        except AgentLLMError:
            return None
        return _rules_from_maker_output(result)

    def _profile_with_error(self, error_message: str) -> Profile:
        return Profile(
            name=self._profile.name,
            system_prompt=f"{self._profile.system_prompt}\n\n{error_message}",
            response_schema=self._profile.response_schema,
            tier=self._profile.tier,
        )


def _default_llm_runner(prompt: str, model: str) -> str:
    """Заглушка runner'а для регистрации по умолчанию (см. докстринг
    модуля) — падает только при РЕАЛЬНОМ вызове модели, не при
    импорте/регистрации шага."""
    raise NotImplementedError(
        "Живой LLM-runner для шага 'rule' ещё не подключён — заработает "
        "после пилотного прогона Задачи 27 (см. "
        "importer/build/llm_client.py:RunnerAgentLLM)"
    )


_default_llm = RunnerAgentLLM(_default_llm_runner)
register_step("rule", RuleStep(_default_llm))
