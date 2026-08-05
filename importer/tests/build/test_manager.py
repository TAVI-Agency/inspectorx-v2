"""LLM-менеджер исключений (Задача 27, ADR-0003 «Блок 2», финал).

Сценарии из брифа задачи (юнит-уровень `manager.py`, БЕЗ Orchestrator —
интеграционные сценарии «менеджер меняет поведение прогона» см. в
`test_orchestrator.py`: `test_manager_retry_reformulated_*`/
`test_manager_escalate_owner_*`):

- `ExceptionManager.review` — валидный `retry_reformulated`/`escalate_owner`
  ответ LLM разбирается в `{"action", "note"}`;
- мусорный/невалидный ответ (не JSON, неизвестное действие, отсутствует
  `action`) -> консервативный дефолт `escalate_owner`, БЕЗ исключения наружу
  (менеджер обязан вернуть решение, а не уронить `_run_from`);
- `expensive`-тир модели — тот же принцип, что и у Cartographer (Задача 15):
  дорогое решение, редкий вызов;
- `NullExceptionManager` — дефолт `Orchestrator`, не трогает LLM вовсе,
  решение всегда `escalate_owner`.
"""
from __future__ import annotations

import json

from importer.build.agents import load_models_config
from importer.build.manager import ExceptionManager, NullExceptionManager
from importer.build.steps import ItemRecord


class ScriptedLLM:
    """Мок `AgentLLMClient`: отдаёт ответы по очереди, фиксирует все `(prompt, model)`."""

    def __init__(self, responses: list[str]):
        self._responses = list(responses)
        self.calls: list[tuple[str, str]] = []

    def complete(self, prompt: str, model: str) -> str:
        self.calls.append((prompt, model))
        return self._responses.pop(0)


def _item(expected_item: str = "маркировка акцизной маркой") -> ItemRecord:
    return ItemRecord(id="item-1", run_id="run-1", expected_item=expected_item)


# ── валидные ответы ───────────────────────────────────────────────────────


def test_review_parses_retry_reformulated_with_note():
    llm = ScriptedLLM([json.dumps({"action": "retry_reformulated", "note": "уточни запрос"})])
    manager = ExceptionManager(llm)

    decision = manager.review(_item(), ["первый провал", "второй провал"])

    assert decision == {"action": "retry_reformulated", "note": "уточни запрос"}


def test_review_parses_escalate_owner():
    llm = ScriptedLLM([json.dumps({"action": "escalate_owner", "note": None})])
    manager = ExceptionManager(llm)

    decision = manager.review(_item(), ["провал"])

    assert decision == {"action": "escalate_owner", "note": None}


def test_review_uses_expensive_tier_model():
    llm = ScriptedLLM([json.dumps({"action": "escalate_owner", "note": None})])
    manager = ExceptionManager(llm)

    manager.review(_item(), ["провал"])

    config = load_models_config()
    assert len(llm.calls) == 1
    assert llm.calls[0][1] == config.tiers["expensive"]


def test_review_prompt_includes_item_text_and_history():
    llm = ScriptedLLM([json.dumps({"action": "escalate_owner", "note": None})])
    manager = ExceptionManager(llm)

    manager.review(_item("акцизная марка на пачке сигарет"), ["первая ошибка", "вторая ошибка"])

    prompt = llm.calls[0][0]
    assert "акцизная марка на пачке сигарет" in prompt
    assert "первая ошибка" in prompt
    assert "вторая ошибка" in prompt


# ── деградация ответа -> консервативный дефолт escalate_owner ────────────


def test_review_garbage_answer_falls_back_to_escalate_owner():
    llm = ScriptedLLM(["это не JSON"])
    manager = ExceptionManager(llm)

    decision = manager.review(_item(), ["провал"])

    assert decision["action"] == "escalate_owner"
    assert "невалидный ответ" in decision["note"]


def test_review_unknown_action_falls_back_to_escalate_owner():
    llm = ScriptedLLM([json.dumps({"action": "do_something_else", "note": None})])
    manager = ExceptionManager(llm)

    decision = manager.review(_item(), ["провал"])

    assert decision["action"] == "escalate_owner"


def test_review_missing_action_falls_back_to_escalate_owner():
    llm = ScriptedLLM([json.dumps({"note": "no action field"})])
    manager = ExceptionManager(llm)

    decision = manager.review(_item(), ["провал"])

    assert decision["action"] == "escalate_owner"


def test_review_non_dict_json_falls_back_to_escalate_owner():
    llm = ScriptedLLM([json.dumps(["retry_reformulated"])])
    manager = ExceptionManager(llm)

    decision = manager.review(_item(), ["провал"])

    assert decision["action"] == "escalate_owner"


# ── NullExceptionManager: дефолт Orchestrator, LLM не трогает ────────────


def test_null_exception_manager_always_escalates_without_touching_llm():
    manager = NullExceptionManager()

    decision = manager.review(_item(), ["провал 1", "провал 2"])

    assert decision == {"action": "escalate_owner", "note": None}
