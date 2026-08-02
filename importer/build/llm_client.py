"""Тонкий адаптер над паттерном `importer.llm` для мультимодельных
generic-агентов Build (ADR-0003, Задача 13).

Почему не переиспользовать `importer.llm.LLM` напрямую: этот клиент заточен
под один бэкенд (`claude -p`, локальная подписка) и рантайм-инъекцию
`Callable[[str], str]` БЕЗ параметра модели — годится для разовых LLM-шагов
импортёра (перевод карточки, конвертация отчёта в схему), где модель одна и
фиксирована в рантайме. Generic-агентам Build это не подходит: тир модели —
атрибут `Profile.tier` (см. `profiles.py`), а значит модель выбирается на
каждый вызов из `models.yaml`, и Verifier обязан получать модель ДРУГОГО
тира, чем producer-шаг (преамбула «Блок 2» мастер-плана, `agents.py:
verifier_model_for`). Втиснуть это в `LLM.complete(prompt) -> str` можно
только через глобальный костыль (пересоздавать `LLM` на каждый вызов) —
хуже, чем явный параметр `model` в сигнатуре.

`importer/llm.py` — общий модуль вне этой задачи, трогать его не будем.
Здесь — тот же паттерн («инжектируемый runner, никакого сетевого мокинга в
тестах», см. `importer/tests/test_llm.py`), но:
- `model` — явный параметр вызова, а не свойство клиента;
- runner ничего не знает про бэкенд (`claude -p` и т.п.) — какой API дергать
  за `model`, решает сам runner, который передаёт вызывающий код.

Живой GPT-клиент (OpenAI API) в эту задачу не входит — подключение контура
Build с mock на live LLM делают следующие задачи блока (переключение
происходит по тому же принципу, что и `importer.build.legalx.get_client`:
явная инъекция клиента, никакого неявного сетевого вызова по умолчанию). В
тестах и текущем контуре `AgentLLMClient` инжектируется напрямую.
"""
from __future__ import annotations

from typing import Callable, Protocol, runtime_checkable


class AgentLLMError(Exception):
    """Ответ LLM не распарсился или не прошёл контракт вызвавшего агента."""


@runtime_checkable
class AgentLLMClient(Protocol):
    """Контракт LLM-клиента для Retriever/Verifier/Classifier/Summarizer."""

    def complete(self, prompt: str, model: str) -> str:
        """Синхронный вызов модели `model` (значение из `models.yaml: tiers`)."""
        ...


class RunnerAgentLLM:
    """Обёртка над инжектируемым runner'ом — тот же паттерн, что и
    `importer.llm.LLM(runner=...)`, но runner принимает ещё и модель:
    `runner(prompt, model) -> str`. В тестах runner подменяется скриптом
    ответов вместо сетевого вызова (см. `importer/tests/build/test_agents.py`)."""

    def __init__(self, runner: Callable[[str, str], str]):
        self._runner = runner

    def complete(self, prompt: str, model: str) -> str:
        return self._runner(prompt, model)
