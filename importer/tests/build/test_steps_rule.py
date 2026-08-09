"""Шаг 'rule': Rule-maker (Classifier в роли producer'а) + Verifier —
«критическая точка» ADR-0003 решение 5 (реактивация — Задача 10, Волна 2
фотоконтроля, поправка 5 к ADR-0003).

Сценарии:
- happy-path: Rule-maker выдаёт ≥1 правило в формате vision-проверки
  (kind/severity/subject/params/question_ru/hint_ru), Verifier подтверждает
  КАЖДОЕ отдельным вызовом, локальный линтер `validate_candidate` пропускает
  -> StepResult(ok), `ctx.data['rules'] == []` (в базу НИЧЕГО не едет),
  `ctx.data['rule_candidates']` — пути к файлам-кандидатам в
  `IXV_CANDIDATES_DIR`, рядом с каждым — файл `*-scenario.yaml`;
- Rule-maker/producer — тир `mid`, Verifier каждого правила — `expensive`
  (`verifier_model_for('mid') == 'expensive'`, ADR-0003 решение 9);
- невалидный вывод Rule-maker'а (не JSON / не массив / пустой массив) ->
  ретрай с указанием ошибки -> валидный вывод -> успех;
- дважды невалидный вывод -> StepResult(fail), Verifier вообще не вызывается,
  на диск ничего не пишется;
- Verifier отклонил хотя бы одно правило из набора -> StepResult(fail) со
  ВСЕМИ вердиктами (и pass, и fail) в результате, `ctx.data` не наполняется
  ключом 'rules', на диск ничего не пишется;
- мутационный пин-тест: смешанный набор (не все правила отклонены) должен
  давать fail — отличает `any(rejected)` от `all(rejected)`;
- фикс-раунд ревью (наследие Задачи 19): Verifier бросает исключение не на
  первом, а на одном из СРЕДНИХ правил -> уже собранные к этому моменту
  вердикты предыдущих правил не теряются, попадают в `StepResult(fail).verdicts`;
- локальный линтер `validate_candidate`: кандидат, прошедший Verifier, но
  нарушающий словарь kind/severity/params/question_ru — бракует весь набор
  ДО записи файла, мусор кандидатом не становится;
- шаг применяется не ко всем категориям: `category_slug != 'marking'`
  (включая отсутствие ключа вовсе) -> StepResult(ok), пустой список правил,
  `ctx.data['skipped_rule_step'] = True`, ноль обращений к LLM;
- 'marking' без предварительного 'norm' (нет `norm_fragment` в контексте) ->
  StepResult(fail), не AttributeError, LLM вообще не вызывается;
- verifier-фейл x3 (MAX_STEP_RETRIES) -> needs_attention всего айтема через
  обычный путь Orchestrator'а (тот же паттерн, что not_found у 'norm');
- опциональный PR (`RULE_CANDIDATE_PR=1`): по умолчанию `gh`/`git` вообще не
  зовутся; при флаге — ошибка subprocess не валит шаг, попадает
  предупреждением в `ctx.data['rule_pr_warning']`;
- регистрация в реестре steps.py.

LLM — только инжектируемый скрипт ответов (тот же паттерн, что и
test_steps_norm.py/test_steps_classify.py: ScriptedLLM, никакой сети).
`IXV_CANDIDATES_DIR` в каждом тесте, который доходит до записи кандидата,
переопределён на `tmp_path` — ни один тест не должен коснуться реального
`inspectorx-vision` на диске.
"""
from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import pytest
import yaml

from importer.build.agents import load_models_config, verifier_model_for
from importer.build.legalx import NormFragment
from importer.build.orchestrator import MapRecord, Orchestrator
from importer.build.steps import STEP_ORDER, ItemContext, ItemRecord, StepResult
from importer.build.steps_rule import RuleStep, validate_candidate
from importer.tests.build.stores import InMemoryStore


# ── тестовые дублёры ────────────────────────────────────────────────────


@dataclass
class ScriptedLLM:
    """Мок AgentLLMClient: отдаёт ответы по очереди, фиксирует все (prompt, model)."""

    responses: list[str]
    calls: list[tuple[str, str]] = field(default_factory=list)

    def complete(self, prompt: str, model: str) -> str:
        self.calls.append((prompt, model))
        if not self.responses:
            raise AssertionError("ScriptedLLM: запросили ответ сверх скрипта — лишний вызов LLM")
        return self.responses.pop(0)


def vision_check(**over) -> dict:
    """Черновик проверки в формате vision-пакета (kind/severity/subject/
    params/question_ru/hint_ru) — то, что реально должен вернуть Rule-maker
    теперь (не старый плоский `{"field": ..., "lang": ...}`)."""
    base = dict(
        kind="text_semantic",
        severity="major",
        subject="other:check",
        params={"expect": "any_mention", "pattern_hints": ["состав"], "language": ["uz"]},
        question_ru="Указан ли состав на узбекском?",
        hint_ru="Оборотная сторона, мелкий кегль",
    )
    return {**base, **over}


def rule_maker_response(*rules: dict) -> str:
    return json.dumps({"rules": list(rules)}, ensure_ascii=False)


def verdict_json(passed: bool, reason: str = "") -> str:
    return json.dumps({"passed": passed, "reason": reason}, ensure_ascii=False)


def fragment(**over) -> NormFragment:
    base = dict(
        fragment_id="frag-1", act_id="act-1", act_title="ПКМ-290",
        article_ref="п. 5", anchor="#p5",
        content="на потребительской упаковке обязательны состав на узбекском и штрих-код EAN-13",
        act_status="active", valid_from=date(2020, 1, 1), valid_to=None, score=1.0,
    )
    return NormFragment(**{**base, **over})


def item_ctx(*, category_slug: str | None = "marking", with_norm_fragment: bool = True) -> ItemContext:
    item = ItemRecord(
        id="item-1", run_id="run-1",
        expected_item="акцизная марка на пачке сигарет", category_slug=None,
    )
    ctx = ItemContext(item=item)
    if with_norm_fragment:
        ctx.data["norm_fragment"] = fragment()
    if category_slug is not None:
        ctx.data["category_slug"] = category_slug
    return ctx


# Алиас для соответствия имени хелпера из брифа задачи — тот же контракт,
# что и `item_ctx()` по умолчанию: category_slug='marking' + norm_fragment.
def make_marking_ctx() -> ItemContext:
    return item_ctx()


def approved_map(**over) -> MapRecord:
    base = dict(
        id="map-1", group_ref="2203", jurisdiction="UZ", status="approved",
        payload=[{"expected_item": "акцизная марка на пачке сигарет", "category_slug": "marking"}],
    )
    return MapRecord(**{**base, **over})


# ── шаг 'rule': не-marking категория -> ok + пусто + skip, без LLM ─────


def test_rule_step_non_marking_category_skips_with_empty_rules_and_flag():
    llm = ScriptedLLM(responses=[])
    step = RuleStep(llm)
    ctx = item_ctx(category_slug="sps")

    result = step(ctx)

    assert result.status == "ok"
    assert ctx.data["rules"] == []
    assert ctx.data["skipped_rule_step"] is True
    assert llm.calls == []


def test_rule_step_missing_category_slug_in_ctx_also_skips():
    """category_slug ещё не положен шагом 'category' (например, партиальный
    rerun не с начала) — трактуется так же, как «не marking», не как fail."""
    llm = ScriptedLLM(responses=[])
    step = RuleStep(llm)
    ctx = item_ctx(category_slug=None)
    assert "category_slug" not in ctx.data

    result = step(ctx)

    assert result.status == "ok"
    assert ctx.data["rules"] == []
    assert ctx.data["skipped_rule_step"] is True
    assert llm.calls == []


# ── шаг 'rule': marking, но нет norm_fragment -> fail, не raise ────────


def test_rule_step_marking_without_norm_fragment_returns_fail_not_raise():
    llm = ScriptedLLM(responses=[])
    step = RuleStep(llm)
    ctx = item_ctx(with_norm_fragment=False)

    result = step(ctx)

    assert result.status == "fail"
    assert "norm_fragment" in result.error.lower() or "norm" in result.error.lower()
    assert llm.calls == []


# ── шаг 'rule': happy-path — кандидат на диске, не в базе ──────────────


def test_rule_step_writes_candidate_yaml_not_db(tmp_path, monkeypatch):
    """Формат «машина предлагает — человек утверждает»: файл-кандидат, rules=[]."""
    monkeypatch.setenv("IXV_CANDIDATES_DIR", str(tmp_path))
    llm = ScriptedLLM([
        rule_maker_response(vision_check()),
        verdict_json(True, "правило следует из нормы"),
    ])
    ctx = make_marking_ctx()

    result = RuleStep(llm)(ctx)

    assert result.status == "ok"
    assert ctx.data["rules"] == []  # в requirement_rules НЕ едет
    paths = ctx.data["rule_candidates"]
    assert len(paths) == 1
    doc = yaml.safe_load(Path(paths[0]).read_text(encoding="utf-8"))
    assert doc["candidate"] is True
    assert doc["check"]["kind"] == "text_semantic"
    assert doc["check"]["id"] == "candidate.item-1.1"
    assert doc["check"]["group"] == "candidate"
    assert doc["check"]["level"] == "consumer"
    assert "quote_ru" in doc["source"]  # цитата нормы обязательна
    assert "состав" in doc["source"]["quote_ru"]
    scenario = Path(paths[0].replace(".yaml", "-scenario.yaml"))
    assert scenario.exists()
    fixture = yaml.safe_load(scenario.read_text(encoding="utf-8"))
    assert fixture["candidate_check_id"] == "candidate.item-1.1"
    assert fixture["cases"][0]["check"] == "candidate.item-1.1"
    assert fixture["cases"][0]["pass"]["expect"] == "pass"
    assert fixture["cases"][0]["fail"]["expect"] == "fail"


def test_rule_step_two_rules_write_two_candidate_and_scenario_pairs(tmp_path, monkeypatch):
    monkeypatch.setenv("IXV_CANDIDATES_DIR", str(tmp_path))
    llm = ScriptedLLM([
        rule_maker_response(
            vision_check(),
            vision_check(
                kind="presence", severity="critical", subject="barcode",
                params={"expect": "presence", "pattern_hints": ["EAN-13"]},
                question_ru="Присутствует ли штрих-код EAN-13?",
                hint_ru="Нижняя грань пачки",
            ),
        ),
        verdict_json(True, "первое ок"),
        verdict_json(True, "второе ок"),
    ])
    ctx = make_marking_ctx()

    result = RuleStep(llm)(ctx)

    assert result.status == "ok"
    assert ctx.data["rules"] == []
    assert len(ctx.data["rule_candidates"]) == 2
    yaml_files = sorted(tmp_path.glob("item-1-*.yaml"))
    # 2 кандидата + 2 сценарные фикстуры
    assert len(yaml_files) == 4


def test_rule_step_uses_mid_tier_and_verifier_gets_expensive_tier(tmp_path, monkeypatch):
    monkeypatch.setenv("IXV_CANDIDATES_DIR", str(tmp_path))
    llm = ScriptedLLM([
        rule_maker_response(vision_check()),
        verdict_json(True),
    ])
    step = RuleStep(llm)

    step(make_marking_ctx())

    config = load_models_config()
    assert llm.calls[0][1] == config.tiers["mid"]
    verifier_call_model = llm.calls[1][1]
    assert verifier_call_model == config.tiers["expensive"]
    assert verifier_call_model == verifier_model_for(config.tiers["mid"])


# ── шаг 'rule': невалидный вывод Rule-maker'а -> ретрай -> успех ────────


def test_rule_step_invalid_maker_output_retries_with_error_message_then_succeeds(tmp_path, monkeypatch):
    monkeypatch.setenv("IXV_CANDIDATES_DIR", str(tmp_path))
    llm = ScriptedLLM([
        "это вообще не JSON",
        rule_maker_response(vision_check()),
        verdict_json(True),
    ])
    ctx = make_marking_ctx()

    result = RuleStep(llm)(ctx)

    assert result.status == "ok"
    assert ctx.data["rules"] == []
    assert len(ctx.data["rule_candidates"]) == 1
    assert len(llm.calls) == 3
    retry_prompt = llm.calls[1][0]
    assert "невалид" in retry_prompt.lower()


def test_rule_step_empty_rules_array_is_treated_as_invalid_and_retries(tmp_path, monkeypatch):
    """Пустой массив формально валидный JSON, но брифом требуется ≥1
    правило — пустой список так же уходит в ретрай, как невалидный JSON."""
    monkeypatch.setenv("IXV_CANDIDATES_DIR", str(tmp_path))
    llm = ScriptedLLM([
        json.dumps({"rules": []}),
        rule_maker_response(vision_check()),
        verdict_json(True),
    ])
    ctx = make_marking_ctx()

    result = RuleStep(llm)(ctx)

    assert result.status == "ok"
    assert len(ctx.data["rule_candidates"]) == 1


# ── шаг 'rule': дважды невалидный вывод -> fail, ничего не пишется ─────


def test_rule_step_twice_invalid_maker_output_returns_fail(tmp_path, monkeypatch):
    monkeypatch.setenv("IXV_CANDIDATES_DIR", str(tmp_path))
    llm = ScriptedLLM([
        "мусор",
        "снова не JSON",
    ])
    ctx = make_marking_ctx()

    result = RuleStep(llm)(ctx)

    assert result.status == "fail"
    assert result.error is not None
    assert result.verdicts == []
    assert "rules" not in ctx.data
    assert list(tmp_path.glob("*.yaml")) == []


# ── шаг 'rule': Verifier отклонил хотя бы одно правило -> fail ──────────


def test_rule_step_one_of_two_rules_rejected_by_verifier_returns_fail(tmp_path, monkeypatch):
    monkeypatch.setenv("IXV_CANDIDATES_DIR", str(tmp_path))
    llm = ScriptedLLM([
        rule_maker_response(
            vision_check(),
            vision_check(subject="barcode", question_ru="Есть ли штрих-код?"),
        ),
        verdict_json(True, "первое ок"),
        verdict_json(False, "второе не упомянуто в норме"),
    ])
    ctx = make_marking_ctx()

    result = RuleStep(llm)(ctx)

    assert result.status == "fail"
    assert len(result.verdicts) == 2
    assert result.verdicts[0].passed is True
    assert result.verdicts[1].passed is False
    assert "rules" not in ctx.data
    assert list(tmp_path.glob("*.yaml")) == []


def test_rule_step_any_rejected_not_all_rejected_causes_fail_mutation_pin(tmp_path, monkeypatch):
    """Пин-тест политики «исключено ХОТЯ БЫ одно -> fail всего набора», не
    «отклонены ВСЕ -> fail»: 3 правила, отклонено только одно из трёх. Если
    бы реализация ошибочно проверяла `all(rejected)` вместо `any(rejected)`,
    этот тест поймал бы регрессию — на однородном наборе (все pass или все
    fail) `any`/`all` дают одинаковый результат, различает их только
    смешанный набор."""
    monkeypatch.setenv("IXV_CANDIDATES_DIR", str(tmp_path))
    llm = ScriptedLLM([
        rule_maker_response(
            vision_check(),
            vision_check(subject="barcode", question_ru="Есть ли штрих-код?"),
            vision_check(subject="expiry", question_ru="Указан ли срок годности?"),
        ),
        verdict_json(True),
        verdict_json(False, "штрих-код не упомянут в норме"),
        verdict_json(True),
    ])
    ctx = make_marking_ctx()

    result = RuleStep(llm)(ctx)

    assert result.status == "fail"
    assert len(result.verdicts) == 3
    assert [v.passed for v in result.verdicts] == [True, False, True]
    assert "rules" not in ctx.data


# ── шаг 'rule': исключение Verifier'а посреди цикла — вердикты не теряются ─


def test_rule_step_verifier_exception_mid_loop_preserves_collected_verdicts(tmp_path, monkeypatch):
    """Фикс-раунд ревью Задачи 19: Verifier бросает исключение (здесь —
    невалидный JSON от LLM, `AgentLLMError`) на 2-м из 3 правил. Уже
    собранный вердикт 1-го правила не теряется, хотя докстринг модуля
    обещает, что все вердикты попадают в результат независимо от статуса."""
    monkeypatch.setenv("IXV_CANDIDATES_DIR", str(tmp_path))
    llm = ScriptedLLM([
        rule_maker_response(
            vision_check(),
            vision_check(subject="barcode", question_ru="Есть ли штрих-код?"),
            vision_check(subject="expiry", question_ru="Указан ли срок годности?"),
        ),
        verdict_json(True, "первое правило подтверждено"),
        "это не JSON — верификатор второго правила ломается",
    ])
    ctx = make_marking_ctx()

    result = RuleStep(llm)(ctx)

    assert result.status == "fail"
    assert len(result.verdicts) == 1
    assert result.verdicts[0].passed is True
    assert result.error is not None
    assert "2" in result.error  # указан номер правила, на котором сломался verifier
    assert "rules" not in ctx.data
    # верификатор третьего правила вообще не должен был вызываться —
    # цикл прерывается немедленно на исключении
    assert len(llm.calls) == 3


# ── линтер: `validate_candidate` и его точка входа в шаге ──────────────


def test_validate_candidate_flags_all_known_problems():
    problems = validate_candidate({"kind": "teleportation", "severity": "wtf", "params": "не объект"})
    assert any("kind" in p for p in problems)
    assert any("severity" in p for p in problems)
    assert any("params" in p for p in problems)
    assert any("question_ru" in p for p in problems)


def test_validate_candidate_clean_check_has_no_problems():
    assert validate_candidate(vision_check()) == []


def test_invalid_candidate_rejected_by_linter(tmp_path, monkeypatch):
    monkeypatch.setenv("IXV_CANDIDATES_DIR", str(tmp_path))
    llm = ScriptedLLM([
        json.dumps({"rules": [{"kind": "teleportation"}]}),
        json.dumps({"rules": [{"kind": "teleportation"}]}),
    ])
    result = RuleStep(llm)(make_marking_ctx())

    assert result.status == "fail"
    assert list(tmp_path.glob("*.yaml")) == []  # мусор кандидатом не становится


def test_rule_step_linter_rejects_invalid_kind_even_after_verifier_passes(tmp_path, monkeypatch):
    """В отличие от `test_invalid_candidate_rejected_by_linter` (там Verifier
    сам ломается на мусорном ответе) — здесь Verifier честно подтверждает
    правило, и уже ПОСЛЕ верификации кандидата ловит невалидный `kind`
    линтер: отдельная точка отказа, отдельное покрытие."""
    monkeypatch.setenv("IXV_CANDIDATES_DIR", str(tmp_path))
    llm = ScriptedLLM([
        rule_maker_response({
            "kind": "teleportation", "severity": "major", "subject": "other:check",
            "params": {"expect": "any_mention", "pattern_hints": ["x"]},
            "question_ru": "Вопрос?", "hint_ru": "подсказка",
        }),
        verdict_json(True, "формально соответствует норме"),
    ])
    result = RuleStep(llm)(make_marking_ctx())

    assert result.status == "fail"
    assert "линтер" in result.error
    assert list(tmp_path.glob("*.yaml")) == []


# ── опциональный PR (RULE_CANDIDATE_PR=1) ───────────────────────────────


def test_rule_step_does_not_touch_subprocess_when_pr_flag_unset(tmp_path, monkeypatch):
    monkeypatch.setenv("IXV_CANDIDATES_DIR", str(tmp_path))
    monkeypatch.delenv("RULE_CANDIDATE_PR", raising=False)

    def _boom(*a, **kw):
        raise AssertionError("subprocess.run не должен вызываться без RULE_CANDIDATE_PR=1")

    monkeypatch.setattr(subprocess, "run", _boom)
    llm = ScriptedLLM([
        rule_maker_response(vision_check()),
        verdict_json(True),
    ])
    ctx = make_marking_ctx()

    result = RuleStep(llm)(ctx)

    assert result.status == "ok"
    assert "rule_pr_warning" not in ctx.data


def test_rule_step_pr_flag_set_records_warning_on_subprocess_failure_but_step_stays_ok(tmp_path, monkeypatch):
    monkeypatch.setenv("IXV_CANDIDATES_DIR", str(tmp_path))
    monkeypatch.setenv("RULE_CANDIDATE_PR", "1")
    monkeypatch.setattr("importer.build.steps_rule.shutil.which", lambda name: "/usr/bin/gh")

    def _fails(*a, **kw):
        raise subprocess.CalledProcessError(1, a[0] if a else ["git"])

    monkeypatch.setattr(subprocess, "run", _fails)
    llm = ScriptedLLM([
        rule_maker_response(vision_check()),
        verdict_json(True),
    ])
    ctx = make_marking_ctx()

    result = RuleStep(llm)(ctx)

    assert result.status == "ok"  # кандидат уже на диске — ошибка PR не валит шаг
    assert len(ctx.data["rule_candidates"]) == 1
    assert "rule_pr_warning" in ctx.data


def test_rule_step_pr_flag_set_but_gh_missing_records_warning_without_subprocess(tmp_path, monkeypatch):
    monkeypatch.setenv("IXV_CANDIDATES_DIR", str(tmp_path))
    monkeypatch.setenv("RULE_CANDIDATE_PR", "1")
    monkeypatch.setattr("importer.build.steps_rule.shutil.which", lambda name: None)

    def _boom(*a, **kw):
        raise AssertionError("subprocess.run не должен вызываться, когда 'gh' не найден")

    monkeypatch.setattr(subprocess, "run", _boom)
    llm = ScriptedLLM([
        rule_maker_response(vision_check()),
        verdict_json(True),
    ])
    ctx = make_marking_ctx()

    result = RuleStep(llm)(ctx)

    assert result.status == "ok"
    assert "gh" in ctx.data["rule_pr_warning"]


# ── интеграция: Orchestrator — verifier-фейл x3 -> needs_attention ──────


def test_rule_step_verifier_fail_x3_escalates_to_needs_attention_via_orchestrator(tmp_path, monkeypatch):
    """Консервативная политика «критической точки» (ADR-0003 р.5, «кривое
    правило = кривой фото-чек»): ретраит ЦЕЛЫЙ шаг оркестратор, не сам шаг;
    после MAX_STEP_RETRIES=3 подряд провалов — needs_attention. Verifier
    отклоняет правило на каждой из 3 попыток -> до записи файлов дело не
    доходит, но IXV_CANDIDATES_DIR всё равно переопределён — гигиена."""
    monkeypatch.setenv("IXV_CANDIDATES_DIR", str(tmp_path))
    store = InMemoryStore()
    store.maps["map-1"] = approved_map()

    one_attempt = [
        rule_maker_response(vision_check()),
        verdict_json(False, "правило не соответствует норме"),
    ]
    llm = ScriptedLLM(one_attempt * 3)
    rule_step = RuleStep(llm)

    def norm_stub(ctx: ItemContext) -> StepResult:
        ctx.data["norm_fragment"] = fragment()
        return StepResult(status="ok")

    def category_stub(ctx: ItemContext) -> StepResult:
        ctx.data["category_slug"] = "marking"
        return StepResult(status="ok")

    steps = {name: (lambda ctx: StepResult(status="ok")) for name in STEP_ORDER}
    steps["norm"] = norm_stub
    steps["category"] = category_stub
    steps["rule"] = rule_step

    report = Orchestrator(store, steps=steps).run_group("map-1")

    assert report.needs_attention == 1
    assert report.published == 0
    item = next(iter(store.items.values()))
    assert item.status == "needs_attention"


# ── регистрация в реестре steps.py ───────────────────────────────────────


def test_rule_step_is_registered_in_steps_registry():
    from importer.build.steps import get_step

    assert callable(get_step("rule"))


def test_load_default_steps_imports_steps_rule_module():
    from importer.build.steps import get_step, load_default_steps

    load_default_steps()  # идемпотентно — повторный вызов не должен падать

    assert callable(get_step("rule"))
