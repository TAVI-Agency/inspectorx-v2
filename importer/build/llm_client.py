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
    ответов вместо сетевого вызова (см. `importer/tests/build/test_agents.py`).

    Задача 29 (трейсинг, `trace.py`): `runner` МОЖЕТ вернуть либо просто
    `str` (старое поведение — ВСЕ существующие scripted-раннеры тестов, без
    изменений), либо `tuple[str, dict]` — `(text, usage)`, где `usage`
    несёт РЕАЛЬНЫЕ счётчики токенов бэкенда (`{"input_tokens": int,
    "output_tokens": int}`). `complete()` в обоих случаях возвращает только
    `text` — контракт `AgentLLMClient.complete -> str` не меняется, это
    ОПЦИОНАЛЬНОЕ расширение раннера, не Protocol. Посчитанное/оценённое
    использование кладётся в `self.last_usage`
    (`{"input_tokens", "output_tokens", "estimated"}`) — побочный канал,
    который трейсящие агенты (`agents.py`) читают ПОСЛЕ вызова `complete()`
    через `getattr(llm, "last_usage", None)`; клиенты без такого атрибута
    (например, `ScriptedLLM` тестов) агент трактует как «оценить самому»
    той же эвристикой (см. `agents.py: _trace_llm_call`).

    Если `runner` вернул только `str` — реальных токенов бэкенд не отдал,
    `last_usage` — ОЦЕНКА (`estimated=True`): `len(prompt)//4` на вход,
    `len(text)//4` на выход (грубая эвристика «4 символа на токен», не
    привязанная к конкретному токенизатору — годится только для прикидки
    стоимости, не для точного биллинга, см. докстринг `trace.py`)."""

    def __init__(self, runner: Callable[[str, str], "str | tuple[str, dict]"]):
        self._runner = runner
        self.last_usage: dict | None = None

    def complete(self, prompt: str, model: str) -> str:
        result = self._runner(prompt, model)
        if isinstance(result, tuple):
            text, usage = result
            self.last_usage = {
                "input_tokens": usage.get("input_tokens", 0),
                "output_tokens": usage.get("output_tokens", 0),
                "estimated": False,
            }
            return text
        text = result
        self.last_usage = {
            "input_tokens": len(prompt) // 4,
            "output_tokens": len(text) // 4,
            "estimated": True,
        }
        return text
