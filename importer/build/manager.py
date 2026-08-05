"""LLM-менеджер исключений (Задача 27, ADR-0003 «Блок 2», финал).

Заменяет прежний прямой вызов `escalate()` внутри `Orchestrator._run_from`
(`orchestrator.py`) решением expensive-модели: получив айтем, который
провалил один и тот же шаг `MAX_STEP_RETRIES` раз подряд, и историю причин
провала, менеджер решает — «стоит ОДНА дополнительная попытка с
переформулировкой» (`retry_reformulated`, с `note` — краткой подсказкой,
которая ложится в `ItemContext.data['manager_note']` перед доп. попыткой) —
или «дальше сам, разбор владельцем» (`escalate_owner`, ровно то же самое,
что и старый `escalate()`).

Менеджер вызывается РОВНО в двух точках (решение контроллера задачи, «ТОЛЬКО
при N подряд фейлов… и в coverage при пробелах»):
1. `Orchestrator._run_from` — после `MAX_STEP_RETRIES` подряд провалов шага
   (единственная точка, где решение менеджера реально МЕНЯЕТ поведение
   прогона — доп. rerun шага или эскалация);
2. `coverage.coverage_report` — для каждого `needs_attention`-пробела,
   найденного ПОСЛЕ прогона; здесь решение менеджера только ИНФОРМАТИВНОЕ
   (`CoverageGap.manager_suggestion` в отчёте) — coverage НИЧЕГО не
   перезапускает и не публикует сама.

Менеджер НЕ публикует требования и не пишет `pipeline.items`/`requirements`
напрямую — это делает `publish_ready` (`coverage.py`) отдельно, по вердиктам
Verifier'ов, а не по мнению менеджера.

Тот же паттерн отсрочки live-подключения, что и везде в Build
(`steps_norm.py` и соседи): конструирование `ExceptionManager` по умолчанию
сеть не трогает, `NotImplementedError` — только при РЕАЛЬНОМ вызове
`.review(...)` без инжектированного runner'а (см. `default_exception_manager`
ниже). `NullExceptionManager` — дефолт `Orchestrator` БЕЗ явного `manager=`:
не трогает LLM вовсе, всегда `escalate_owner` — ровно старое поведение до
Задачи 27, чтобы существующие тесты/вызовы, не передающие `manager=`, не
заметили разницы.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Protocol

from importer.build.agents import ModelsConfig, load_models_config
from importer.build.llm_client import AgentLLMClient, AgentLLMError, RunnerAgentLLM
from importer.build.profiles import Profile
from importer.build.steps import ItemRecord

_VALID_ACTIONS = ("retry_reformulated", "escalate_owner")

MANAGER_PROFILE = Profile(
    name="manager",  # вне ProfileName Literal в profiles.py — тот же прецедент,
    # что и 'scope'/'rule'/'lawyer'/'assemble' в соседних шаговых модулях.
    system_prompt=(
        "Ты — менеджер исключений Build-конвейера комплаенс-чеклиста. Тебе "
        "показывают требование, которое несколько раз подряд провалило один "
        "и тот же шаг конвейера, и историю причин провала. Реши: имеет ли "
        "смысл ОДНА дополнительная попытка с переформулировкой "
        "(retry_reformulated — укажи note: краткую конкретную подсказку для "
        "повторной попытки), или проблема требует ручного разбора владельцем "
        "(escalate_owner — note необязателен). Ответь СТРОГО JSON "
        '{"action": "retry_reformulated"|"escalate_owner", "note": "..."|null}.'
    ),
    response_schema={
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": list(_VALID_ACTIONS)},
            "note": {"type": ["string", "null"]},
        },
        "required": ["action", "note"],
    },
    tier="expensive",
)


@dataclass(frozen=True)
class ManagerDecision:
    """Типизированное решение менеджера — для удобства вызывающего кода;
    `.review(...)` тем не менее возвращает обычный `dict` (тот же контракт,
    что и `{"action": ..., "note": ...}` из брифа задачи), не этот dataclass —
    `ManagerDecision` пригождается только тем, кто явно хочет типизацию."""

    action: str
    note: str | None = None


class ExceptionManagerLike(Protocol):
    """Структурный контракт менеджера исключений для `Orchestrator`/
    `coverage.coverage_report` — единственный метод `review`. `Orchestrator`
    и `coverage_report` читают решение через `.get(...)` (обычный dict), не
    требуя наследования от этого Protocol."""

    def review(self, item: ItemRecord, history: list[str]) -> dict: ...


class NullExceptionManager:
    """Дефолт `Orchestrator` без явного `manager=` (см. докстринг модуля) —
    НЕ трогает LLM вовсе, решение всегда `escalate_owner`."""

    def review(self, item: ItemRecord, history: list[str]) -> dict:
        return {"action": "escalate_owner", "note": None}


class ExceptionManager:
    """Живой LLM-менеджер исключений (expensive-тир, ADR-0003 «Блок 2»).
    Runner инжектируется — тот же паттерн, что и у остальных generic-агентов
    (`agents.py`: Retriever/Verifier/Classifier/Summarizer)."""

    def __init__(
        self,
        llm: AgentLLMClient,
        *,
        models: ModelsConfig | None = None,
        profile: Profile = MANAGER_PROFILE,
    ):
        self._llm = llm
        self._models = models or load_models_config()
        self._profile = profile

    def review(self, item: ItemRecord, history: list[str]) -> dict:
        model = self._models.tiers[self._profile.tier]
        prompt = self._build_prompt(item, history)
        try:
            answer = self._llm.complete(prompt, model)
            data = json.loads(answer)
        except (AgentLLMError, json.JSONDecodeError) as exc:
            # Мусорный ответ менеджера — консервативный дефолт: не ретраим
            # вслепую, отдаём владельцу (тот же принцип, что и у остальных
            # producer-шагов без ретрая: невалидный вывод — не повод
            # рисковать лишней попыткой).
            return {
                "action": "escalate_owner",
                "note": f"менеджер вернул невалидный ответ: {exc}",
            }
        action = data.get("action") if isinstance(data, dict) else None
        if action not in _VALID_ACTIONS:
            return {
                "action": "escalate_owner",
                "note": "менеджер вернул неизвестное/отсутствующее действие",
            }
        return {"action": action, "note": data.get("note")}

    @staticmethod
    def _build_prompt(item: ItemRecord, history: list[str]) -> str:
        history_text = "\n".join(f"- {h}" for h in history) or "(история пуста)"
        return (
            f"{MANAGER_PROFILE.system_prompt}\n\n"
            f"Требование: {item.expected_item}\n"
            f"История провалов:\n{history_text}"
        )


def _default_llm_runner(prompt: str, model: str) -> str:
    """Заглушка runner'а по умолчанию (тот же паттерн, что и во всех
    шаговых модулях) — падает только при РЕАЛЬНОМ вызове `.review(...)`, не
    при конструировании менеджера."""
    raise NotImplementedError(
        "Живой LLM-runner для менеджера исключений ещё не подключён — "
        "заработает после пилотного прогона Задачи 27 (см. "
        "importer/build/llm_client.py:RunnerAgentLLM)"
    )


def default_exception_manager() -> ExceptionManager:
    """«Боевой» менеджер для CLI/`registry.py` — падает `NotImplementedError`
    только при реальном вызове `.review`, не при импорте/конструировании
    (тот же принцип отсрочки, что и `_default_llm` в шаговых модулях)."""
    return ExceptionManager(RunnerAgentLLM(_default_llm_runner))
