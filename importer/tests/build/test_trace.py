"""Трейсинг LLM-вызовов и стоимость по ролям (Задача 29, `trace.py`).

Сценарии брифа + фикс-раунд ревью (Important: старый дизайн `Tracer` с
`run_id`, фиксированным в конструкторе, физически не мог доехать до живых
LLM-вызовов внутри шагов — `build_step_registry` строит шаги/агентов ДО
того, как `Orchestrator.run_group` создаёт `run_id`). Теперь:

- `Tracer.record` считает `cost_usd` по прайсу `models.yaml` (вход+выход) и
  пишет строку через `store.save_llm_call`;
- `Tracer` — LATE-BOUND и MUTABLE: `bind_run(run_id)`/`bind_item(item_id)`,
  `record()` до `bind_run` — no-op;
- токены оцениваются `len(...)//4`, когда клиент не отдаёт реальный usage
  (скриптованный LLM тестов, `RunnerAgentLLM` со str-раннером);
- реальный `usage`-словарь берётся, когда `RunnerAgentLLM`-раннер вернул
  `(text, usage)`;
- generic-агент (Retriever/Verifier/Classifier/Summarizer) с `tracer=`
  пишет вызов под своей ролью; без `tracer=` — ничего не пишет;
- `trace.cost_report` агрегирует `pipeline.llm_calls` по роли — вход CLI
  `build cost --run <id>`;
- ОБЯЗАТЕЛЬНЫЙ интеграционный тест: `build_step_registry(tracer=...)` +
  `Orchestrator(steps=registry, tracer=tracer).run_group(...)` на
  `InMemoryStore` реально доезжают до `pipeline.llm_calls` — не только
  прямое конструирование агентов, а весь путь фабрика->шаг->агент->Tracer.

Фикстуры (`ScriptedLLM`/`FakeLegalX`/`fragment`/`norm_profile`) — импортом
из `test_agents.py` (Minor фикс-раунда ревью: не дублировать)."""
from __future__ import annotations

import json

import pytest

from importer.build.agents import (
    Classifier,
    ModelsConfig,
    Retriever,
    Summarizer,
    Verifier,
)
from importer.build.embeddings import FakeEmbedder
from importer.build.legalx import NormFragment
from importer.build.llm_client import RunnerAgentLLM
from importer.build.orchestrator import MapRecord, Orchestrator
from importer.build.profiles import Profile
from importer.build.registry import build_step_registry
from importer.build.trace import Tracer, cost_report
from importer.tests.build.stores import InMemoryStore
from importer.tests.build.test_agents import FakeLegalX, ScriptedLLM, norm_profile

RUN_ID = "run-1"

TEST_MODELS = ModelsConfig(
    tiers={"cheap": "model-cheap", "mid": "model-mid", "expensive": "model-expensive"},
    pricing={
        "model-cheap": {"input_per_1m_usd": 1.0, "output_per_1m_usd": 2.0},
        "model-mid": {"input_per_1m_usd": 4.0, "output_per_1m_usd": 8.0},
        "model-expensive": {"input_per_1m_usd": 10.0, "output_per_1m_usd": 20.0},
    },
)


# ── Tracer.record: cost по прайсу, late-bound/mutable ────────────────────

def test_tracer_record_computes_cost_from_pricing_and_saves_to_store():
    store = InMemoryStore()
    tracer = Tracer(store, RUN_ID, models=TEST_MODELS)

    # model-cheap: input 1.0$/1M, output 2.0$/1M -> 1_000_000 in + 500_000 out
    # = 1.0 + 1.0 = 2.0$
    tracer.record("retriever", "model-cheap", input_tokens=1_000_000, output_tokens=500_000)

    calls = store.list_llm_calls(RUN_ID)
    assert len(calls) == 1
    call = calls[0]
    assert call["role"] == "retriever"
    assert call["model"] == "model-cheap"
    assert call["input_tokens"] == 1_000_000
    assert call["output_tokens"] == 500_000
    assert call["cost_usd"] == pytest.approx(2.0)
    assert call["item_id"] is None


def test_tracer_record_passes_item_id_through():
    store = InMemoryStore()
    Tracer(store, RUN_ID, models=TEST_MODELS).record(
        "verifier", "model-mid", 100, 50, item_id="item-7"
    )
    assert store.list_llm_calls(RUN_ID)[0]["item_id"] == "item-7"


def test_tracer_record_unknown_model_raises():
    store = InMemoryStore()
    tracer = Tracer(store, RUN_ID, models=TEST_MODELS)
    with pytest.raises(ValueError):
        tracer.record("retriever", "совершенно неизвестная модель", 10, 10)


def test_tracer_only_writes_to_its_own_run():
    store = InMemoryStore()
    Tracer(store, "run-a", models=TEST_MODELS).record("classifier", "model-cheap", 10, 10)
    Tracer(store, "run-b", models=TEST_MODELS).record("classifier", "model-cheap", 10, 10)
    assert len(store.list_llm_calls("run-a")) == 1
    assert len(store.list_llm_calls("run-b")) == 1


def test_tracer_record_is_noop_when_unbound():
    """Late-bound: `Tracer(store)` без `bind_run` (run_id=None) — `record`
    молча ничего не пишет (не ошибка) — см. докстринг `trace.py:Tracer`."""
    store = InMemoryStore()
    tracer = Tracer(store, models=TEST_MODELS)

    tracer.record("retriever", "model-cheap", 100, 50)

    assert store.llm_calls == []


def test_tracer_bind_run_then_record_writes_under_that_run():
    store = InMemoryStore()
    tracer = Tracer(store, models=TEST_MODELS)
    tracer.record("retriever", "model-cheap", 100, 50)  # до bind_run — no-op

    tracer.bind_run(RUN_ID)
    tracer.record("retriever", "model-cheap", 100, 50)

    assert len(store.list_llm_calls(RUN_ID)) == 1


def test_tracer_bind_item_supplies_item_id_when_not_overridden():
    store = InMemoryStore()
    tracer = Tracer(store, RUN_ID, models=TEST_MODELS)
    tracer.bind_item("item-42")

    tracer.record("classifier", "model-cheap", 10, 10)

    assert store.list_llm_calls(RUN_ID)[0]["item_id"] == "item-42"


def test_tracer_bind_run_resets_bound_item():
    store = InMemoryStore()
    tracer = Tracer(store, RUN_ID, models=TEST_MODELS)
    tracer.bind_item("item-old")

    tracer.bind_run("run-new")
    tracer.record("classifier", "model-cheap", 10, 10)

    assert store.list_llm_calls("run-new")[0]["item_id"] is None


# ── RunnerAgentLLM.last_usage: реальные токены vs оценка ─────────────────

def test_runner_agent_llm_last_usage_estimated_for_str_runner():
    llm = RunnerAgentLLM(lambda prompt, model: "0123456789ABCDEF")  # 16 chars -> 4 tokens
    text = llm.complete("промпт из 20 символов", "model-cheap")

    assert text == "0123456789ABCDEF"
    assert llm.last_usage == {
        "input_tokens": len("промпт из 20 символов") // 4,
        "output_tokens": len("0123456789ABCDEF") // 4,
        "estimated": True,
    }


def test_runner_agent_llm_last_usage_real_when_runner_returns_tuple():
    llm = RunnerAgentLLM(
        lambda prompt, model: ("ответ", {"input_tokens": 123, "output_tokens": 45})
    )
    text = llm.complete("промпт", "model-cheap")

    assert text == "ответ"
    assert llm.last_usage == {"input_tokens": 123, "output_tokens": 45, "estimated": False}


# ── агенты + tracer: роль, оценка/реальные токены, «без tracer — ничего» ──

def test_retriever_with_tracer_records_call_under_retriever_role_estimated_tokens():
    store = InMemoryStore()
    tracer = Tracer(store, RUN_ID, models=TEST_MODELS)
    legalx = FakeLegalX(responses=[[], []])
    answer = json.dumps({"no_norm": True})
    llm = ScriptedLLM([answer])

    Retriever(legalx, llm, TEST_MODELS, tracer=tracer).run("q", "UZ", norm_profile(tier="cheap"))

    calls = store.list_llm_calls(RUN_ID)
    assert len(calls) == 1
    assert calls[0]["role"] == "retriever"
    assert calls[0]["model"] == "model-cheap"
    prompt, _ = llm.calls[0]
    assert calls[0]["input_tokens"] == len(prompt) // 4
    assert calls[0]["output_tokens"] == len(answer) // 4
    assert calls[0]["cost_usd"] > 0


def test_retriever_without_tracer_records_nothing():
    store = InMemoryStore()
    legalx = FakeLegalX(responses=[[], []])
    llm = ScriptedLLM([json.dumps({"no_norm": True})])

    Retriever(legalx, llm, TEST_MODELS).run("q", "UZ", norm_profile(tier="cheap"))

    assert store.list_llm_calls(RUN_ID) == []


def test_verifier_with_tracer_records_call_under_verifier_role():
    store = InMemoryStore()
    tracer = Tracer(store, RUN_ID, models=TEST_MODELS)
    llm = ScriptedLLM([json.dumps({"passed": True, "reason": "ok"})])

    Verifier(llm=llm, model="model-expensive", tracer=tracer).run(
        question="вопрос", fragment="фрагмент", source="источник", profile=norm_profile(),
    )

    calls = store.list_llm_calls(RUN_ID)
    assert len(calls) == 1
    assert calls[0]["role"] == "verifier"
    assert calls[0]["model"] == "model-expensive"


def test_classifier_with_tracer_records_call_under_classifier_role():
    store = InMemoryStore()
    tracer = Tracer(store, RUN_ID, models=TEST_MODELS)
    llm = ScriptedLLM([json.dumps({"category": "sanctions"})])
    p = Profile(name="label", system_prompt="классифицируй", response_schema={}, tier="mid")

    Classifier(llm, TEST_MODELS, tracer=tracer).run("текст требования", p)

    calls = store.list_llm_calls(RUN_ID)
    assert len(calls) == 1
    assert calls[0]["role"] == "classifier"
    assert calls[0]["model"] == "model-mid"


def test_summarizer_with_tracer_records_call_under_summarizer_role():
    store = InMemoryStore()
    tracer = Tracer(store, RUN_ID, models=TEST_MODELS)
    llm = ScriptedLLM(["  краткое резюме  "])
    p = Profile(name="samples", system_prompt="сожми", response_schema={}, tier="expensive")

    result = Summarizer(llm, TEST_MODELS, tracer=tracer).run("длинный фрагмент", p)

    assert result == "краткое резюме"
    calls = store.list_llm_calls(RUN_ID)
    assert len(calls) == 1
    assert calls[0]["role"] == "summarizer"
    assert calls[0]["model"] == "model-expensive"


def test_classifier_without_tracer_records_nothing():
    store = InMemoryStore()
    llm = ScriptedLLM([json.dumps({"category": "sanctions"})])
    p = Profile(name="label", system_prompt="p", response_schema={}, tier="mid")

    Classifier(llm, TEST_MODELS).run("текст", p)

    assert store.list_llm_calls(RUN_ID) == []


def test_agent_with_tracer_uses_real_usage_from_runner_agent_llm():
    """Через `RunnerAgentLLM`, чей раннер отдаёт `(text, usage)` — реальные
    токены бэкенда должны попасть в `pipeline.llm_calls` НЕ оценкой
    `len(...)//4`, а как есть."""
    store = InMemoryStore()
    tracer = Tracer(store, RUN_ID, models=TEST_MODELS)
    runner_llm = RunnerAgentLLM(
        lambda prompt, model: (
            json.dumps({"category": "sanctions"}),
            {"input_tokens": 777, "output_tokens": 33},
        )
    )
    p = Profile(name="label", system_prompt="классифицируй", response_schema={}, tier="cheap")

    Classifier(runner_llm, TEST_MODELS, tracer=tracer).run("текст", p)

    calls = store.list_llm_calls(RUN_ID)
    assert len(calls) == 1
    assert calls[0]["input_tokens"] == 777
    assert calls[0]["output_tokens"] == 33


def test_agent_custom_role_overrides_default():
    store = InMemoryStore()
    tracer = Tracer(store, RUN_ID, models=TEST_MODELS)
    llm = ScriptedLLM([json.dumps({"category": "sanctions"})])
    p = Profile(name="label", system_prompt="p", response_schema={}, tier="cheap")

    Classifier(llm, TEST_MODELS, tracer=tracer, role="lifecycle-classifier").run("текст", p)

    assert store.list_llm_calls(RUN_ID)[0]["role"] == "lifecycle-classifier"


# ── cost_report: агрегация по роли для CLI `build cost --run <id>` ───────

def test_cost_report_aggregates_calls_by_role_with_totals():
    store = InMemoryStore()
    tracer = Tracer(store, RUN_ID, models=TEST_MODELS)
    tracer.record("retriever", "model-cheap", 1_000_000, 0)  # 1.0$
    tracer.record("retriever", "model-cheap", 1_000_000, 0)  # 1.0$
    tracer.record("verifier", "model-expensive", 1_000_000, 1_000_000)  # 30.0$

    report = cost_report(store, RUN_ID)

    assert report.run_id == RUN_ID
    by_role = {row.role: row for row in report.rows}
    assert by_role["retriever"].calls == 2
    assert by_role["retriever"].input_tokens == 2_000_000
    assert by_role["retriever"].cost_usd == pytest.approx(2.0)
    assert by_role["verifier"].calls == 1
    assert by_role["verifier"].cost_usd == pytest.approx(30.0)
    assert report.total_calls == 3
    assert report.total_cost_usd == pytest.approx(32.0)
    assert "retriever" in report.markdown
    assert "verifier" in report.markdown
    assert "итого" in report.markdown


def test_cost_report_empty_run_has_no_rows_but_valid_markdown():
    store = InMemoryStore()
    report = cost_report(store, "run-without-calls")

    assert report.rows == []
    assert report.total_calls == 0
    assert report.total_cost_usd == 0.0
    assert "итого" in report.markdown


def test_cost_report_only_includes_calls_of_requested_run():
    store = InMemoryStore()
    Tracer(store, "run-a", models=TEST_MODELS).record("retriever", "model-cheap", 100, 100)
    Tracer(store, "run-b", models=TEST_MODELS).record("retriever", "model-cheap", 100, 100)

    report = cost_report(store, "run-a")

    assert report.total_calls == 1


# ══════════════════════════════════════════════════════════════════════════
# ОБЯЗАТЕЛЬНЫЙ интеграционный тест (фикс-раунд ревью): сквозная проводка
# build_step_registry(tracer) -> 14 Step -> generic-агенты -> Tracer.record
# -> InMemoryStore.llm_calls, через РЕАЛЬНЫЙ Orchestrator.run_group.
# ══════════════════════════════════════════════════════════════════════════

# Тот же приём, что и `scripts/pilot_synthetic.py` (Задача 27) — единый
# скриптованный runner, диспетчеризация по УНИКАЛЬНЫМ маркерам текста
# промпта каждого профиля/агента; карта на 1 айтем, та же группа/юрисдикция
# и синтетический фрагмент нормы про маркировку вина, что и у пилота.

GROUP_REF = "2204"
JURISDICTION = "UZ"
PRODUCT_TYPE_ID = "product-type-wine-1"
ITEM_TEXT = "Указание страны происхождения на контрэтикетке импортного вина"

_WINE_FRAGMENT = NormFragment(
    fragment_id="frag-wine-1", act_id="act-wine-1",
    act_title="Технический регламент о маркировке (тест)",
    article_ref="ст. 5", anchor="p5",
    content=(
        "Импортированное вино маркируется на контрэтикетке с указанием "
        "страны происхождения на государственном и русском языках."
    ),
    act_status="active", valid_from=None, valid_to=None, score=1.0,
)


class _IntegrationLegalX:
    """Тот же приём, что `FakeLegalX` пилота (`scripts/pilot_synthetic.py`):
    находит фрагмент по ключевым словам запроса, санкции — намеренно не
    находит (упрощает сценарий — 'cases' пропускается, без лишних веток
    диспетчера runner'а)."""

    def search_norms(self, query, jurisdiction, domains=None, limit=10):
        if jurisdiction != JURISDICTION:
            return []
        if query.startswith("ответственность за нарушение"):
            return []
        lowered = query.lower()
        if "этикетк" in lowered or "происхожд" in lowered:
            return [_WINE_FRAGMENT]
        return []

    def search_cases(self, article, topic=None, limit=5):
        return []  # sanctions_not_found -> 'cases' не вызывает это вовсе


def _integration_runner(prompt: str, model: str) -> str:
    """Диспетчер по маркерам — падает громко (`AssertionError`) на
    нераспознанном промпте, тот же принцип, что и у `pilot_synthetic.py`."""
    if "Question Writer, эксперт" in prompt:
        return json.dumps([
            {"text": f"Какая норма устанавливает: {ITEM_TEXT}?",
             "expected_schema": {"type": "object"}},
            {"text": f"Какой орган контролирует исполнение требования: {ITEM_TEXT}?",
             "expected_schema": {"type": "object"}},
        ], ensure_ascii=False)
    if "Исходный запрос:" in prompt:
        return json.dumps({"no_norm": True})  # запрос санкций — норм нет
    if "Проверь независимо" in prompt:
        return json.dumps({"passed": True, "reason": "integration test"})
    if "Сформулируй краткое резюме." in prompt:
        return "Импортное вино маркируется страной происхождения на контрэтикетке."
    if "Ты классифицируешь требование" in prompt:
        return json.dumps({"category_slug": "tbt"})
    if "Ты определяешь область действия" in prompt:
        return json.dumps({"kind": "product_type", "product_type_id": PRODUCT_TYPE_ID})
    if "извлекаешь из фрагмента нормы права ТОЛЬКО даты" in prompt:
        return json.dumps({
            "effective_from": None, "transition_until": None,
            "valid_to": None, "repealed_by_ref": None,
        })
    if "решаешь, нужен ли для этого требования" in prompt:
        return json.dumps({"needed": False, "document_type": None})
    if "юрист-инхаус" in prompt:
        return json.dumps({
            "verdict": "Требование применимо к импортёру.",
            "steps": ["Нанести страну происхождения на контрэтикетку"],
            "status_note": None,
        }, ensure_ascii=False)
    if "Переведи следующие ИИ-тексты" in prompt:
        return json.dumps({
            "summary": "uz-перевод саммари",
            "lawyer_instruction": {"steps": ["шаг"], "verdict": "вывод"},
            "status_note": None, "sanctions_measures": [],
        }, ensure_ascii=False)
    if "добираешь недостающие ОБЯЗАТЕЛЬНЫЕ атрибуты" in prompt:
        return json.dumps({
            "title_verb": "Указать страну происхождения на контрэтикетке",
            "deontic": "obligation", "addressee_roles": ["importer"],
            "authority_name": "Тестовое ведомство",
            "sanction_summary_line": "санкция не установлена",
        }, ensure_ascii=False)
    raise AssertionError(f"integration runner: нет сценария для промпта: {prompt[:200]!r}")


def test_integration_build_step_registry_and_orchestrator_trace_full_run():
    store = InMemoryStore(
        product_types_by_group={
            GROUP_REF: [
                {"id": PRODUCT_TYPE_ID, "hs_code": "220410", "unspsc_code": None, "name_ru": "вина игристые"}
            ]
        }
    )
    store.maps["map-1"] = MapRecord(
        id="map-1", group_ref=GROUP_REF, jurisdiction=JURISDICTION, status="approved",
        payload=[{"expected_item": ITEM_TEXT, "category_slug": "tbt"}],
    )

    tracer = Tracer(store)  # late-bound — тот же объект и в registry, и в Orchestrator
    registry = build_step_registry(
        store, _integration_runner, _IntegrationLegalX(),
        group_ref=GROUP_REF, jurisdiction=JURISDICTION, tracer=tracer,
        embedder=FakeEmbedder(),
    )
    orchestrator = Orchestrator(store, steps=registry, tracer=tracer)

    report = orchestrator.run_group("map-1")

    assert report.total_items == 1
    assert report.needs_attention == 0, "прогон не должен эскалировать — иначе трейсинг не полный"

    calls = store.list_llm_calls(report.run_id)
    assert calls, "build_step_registry(tracer)+Orchestrator(tracer) не доехали до pipeline.llm_calls"

    roles = {c["role"] for c in calls}
    assert "retriever" in roles
    assert "verifier" in roles
    assert "classifier" in roles
    assert "summarizer" in roles

    # item_id проставлен КАЖДОМУ вызову (единственный айтем прогона — bind_item
    # вызывается перед КАЖДЫМ шагом этого айтема, см. orchestrator.py:run_group).
    item = next(iter(store.items.values()))
    assert all(c["item_id"] == item.id for c in calls)

    # cost > 0 хотя бы у одного вызова (модели тестовой карты — из реального
    # models.yaml через build_step_registry, прайс там ненулевой у всех
    # тиров — см. test_load_models_config_has_three_tiers_with_pricing).
    assert any(c["cost_usd"] > 0 for c in calls)


def test_integration_without_tracer_records_nothing():
    """Без `tracer=` (ни в `build_step_registry`, ни в `Orchestrator`) —
    прогон работает ровно как до Задачи 29, `pipeline.llm_calls` пуста."""
    store = InMemoryStore(
        product_types_by_group={
            GROUP_REF: [
                {"id": PRODUCT_TYPE_ID, "hs_code": "220410", "unspsc_code": None, "name_ru": "вина игристые"}
            ]
        }
    )
    store.maps["map-1"] = MapRecord(
        id="map-1", group_ref=GROUP_REF, jurisdiction=JURISDICTION, status="approved",
        payload=[{"expected_item": ITEM_TEXT, "category_slug": "tbt"}],
    )

    registry = build_step_registry(
        store, _integration_runner, _IntegrationLegalX(),
        group_ref=GROUP_REF, jurisdiction=JURISDICTION,
        embedder=FakeEmbedder(),
    )
    orchestrator = Orchestrator(store, steps=registry)
    report = orchestrator.run_group("map-1")

    assert report.needs_attention == 0
    assert store.list_llm_calls(report.run_id) == []
