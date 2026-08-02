"""Generic-агенты Build-конвейера (ADR-0003, решение 3): Retriever, Verifier,
Classifier, Summarizer. Один движок на все шаги конвейера — поведение
конкретного шага задаёт `Profile` (`profiles.py`), а не подкласс агента.

Модель каждого вызова выбирается по тиру (`Profile.tier`) через
`models.yaml` (`cheap`/`mid`/`expensive`). Правило блока 2 (преамбула "Блок
2" мастер-плана): **Verifier всегда получает модель ДРУГОГО тира, чем
producer-шаг**, который произвёл проверяемый результат — `verifier_model_for`
ниже вычисляет эту модель, а вызывающий код (будущий оркестратор, Задачи
14+) передаёт её в конструктор `Verifier`. Сам `Verifier.run` независимость
гарантирует на уровне сигнатуры: он принимает только `(question, fragment,
source, profile)` — рассуждения producer-шага физически некуда передать,
их нет в параметрах метода.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Literal

import yaml

from importer.build.legalx import LegalXClient, NormFragment
from importer.build.llm_client import AgentLLMClient, AgentLLMError
from importer.build.profiles import ModelTier, Profile

if TYPE_CHECKING:  # только тип — импорт по значению создал бы цикл agents<->trace
    from importer.build.trace import Tracer

_MODELS_PATH = Path(__file__).parent / "models.yaml"

_TIERS: tuple[ModelTier, ...] = ("cheap", "mid", "expensive")


@dataclass(frozen=True)
class ModelsConfig:
    """Разобранный `models.yaml`: тиры -> имя модели, имя модели -> прайс."""

    tiers: dict[str, str]
    pricing: dict[str, dict[str, float]]


def load_models_config(path: Path = _MODELS_PATH) -> ModelsConfig:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    tiers = raw["tiers"]
    missing = [t for t in _TIERS if t not in tiers]
    if missing:
        raise ValueError(f"models.yaml: не хватает тиров {missing} (ожидались {_TIERS})")
    return ModelsConfig(tiers=tiers, pricing=raw.get("pricing", {}))


def verifier_model_for(producer_model: str, config: ModelsConfig | None = None) -> str:
    """Модель Verifier'а для проверки результата, произведённого
    `producer_model` — ВСЕГДА из другого тира (правило блока 2):

    - producer из `cheap`/`mid` -> verifier из `expensive` (усиленная
      независимая проверка более слабого шага);
    - producer из `expensive` -> verifier из `mid` (тир заведомо другой —
      если бы взяли ту же `expensive`, слепые пятна модели совпали бы).
    """
    config = config or load_models_config()
    tiers_by_model = {model: tier for tier, model in config.tiers.items()}
    producer_tier = tiers_by_model.get(producer_model)
    if producer_tier is None:
        raise ValueError(
            f"Неизвестная модель producer'а {producer_model!r} — нет такой ни "
            f"в одном тире models.yaml ({config.tiers})"
        )
    verifier_tier: ModelTier = "expensive" if producer_tier in ("cheap", "mid") else "mid"
    return config.tiers[verifier_tier]


def _parse_json_answer(answer: str, *, who: str) -> dict:
    try:
        return json.loads(answer)
    except json.JSONDecodeError as exc:
        raise AgentLLMError(f"{who}: LLM вернула не-JSON: {answer!r}") from exc


def _trace_llm_call(
    tracer: "Tracer | None",
    role: str,
    llm: AgentLLMClient,
    model: str,
    prompt: str,
    answer: str,
) -> None:
    """Задача 29 (`trace.py`): если `tracer` не задан — no-op (агенты работают
    ровно как до трейсинга, никакой обязательности). Иначе пишет вызов под
    `role` — реальные токены берутся из `llm.last_usage`, если клиент их
    считает (`llm_client.py: RunnerAgentLLM`); клиенты без такого атрибута
    (например, скриптованные тестовые дублёры) заставляют оценить токены
    той же грубой эвристикой `len(...)//4`, что и `RunnerAgentLLM` для
    str-раннеров (см. докстринг `trace.py`) — оценка НЕ помечается отдельной
    колонкой/полем, только здесь и в докстринге `RunnerAgentLLM.complete`."""
    if tracer is None:
        return
    usage = getattr(llm, "last_usage", None)
    if usage:
        input_tokens = usage.get("input_tokens", 0)
        output_tokens = usage.get("output_tokens", 0)
    else:
        input_tokens = len(prompt) // 4
        output_tokens = len(answer) // 4
    tracer.record(role, model, input_tokens, output_tokens)


@dataclass
class RetrieverResult:
    outcome: Literal["found", "no_norm", "not_found"]
    fragments: list[NormFragment]
    queries_tried: list[str] = field(default_factory=list)


class Retriever:
    """Ищет нормы в LegalX по профилю. При пустом результате переформулирует
    запрос через LLM — до `MAX_REFORMULATIONS` раз — прежде чем признать
    `outcome='not_found'`. Если LLM явно сигналит структурированным ответом
    `{"no_norm": true}`, что в этой юрисдикции такой нормы в принципе нет
    (не «поиск не нашёл», а «требования нет») — это `outcome='no_norm'`,
    отдельно от `not_found`, без исчерпания оставшихся попыток."""

    MAX_REFORMULATIONS = 2

    def __init__(
        self,
        legalx: LegalXClient,
        llm: AgentLLMClient,
        models: ModelsConfig | None = None,
        *,
        tracer: "Tracer | None" = None,
        role: str = "retriever",
    ):
        self._legalx = legalx
        self._llm = llm
        self._models = models or load_models_config()
        self._tracer = tracer
        self._role = role

    def run(self, query: str, jurisdiction: str, profile: Profile) -> RetrieverResult:
        model = self._models.tiers[profile.tier]
        queries_tried: list[str] = [query]
        current_query = query

        for attempt in range(self.MAX_REFORMULATIONS + 1):
            fragments = self._legalx.search_norms(current_query, jurisdiction)
            if fragments:
                return RetrieverResult(
                    outcome="found", fragments=fragments, queries_tried=queries_tried
                )
            if attempt == self.MAX_REFORMULATIONS:
                break  # попытки исчерпаны, переформулировать больше не пробуем

            reformulated = self._reformulate_or_signal_no_norm(
                original_query=query,
                jurisdiction=jurisdiction,
                current_query=current_query,
                profile=profile,
                model=model,
            )
            if reformulated is None:
                return RetrieverResult(outcome="no_norm", fragments=[], queries_tried=queries_tried)
            current_query = reformulated
            queries_tried.append(current_query)

        return RetrieverResult(outcome="not_found", fragments=[], queries_tried=queries_tried)

    def _reformulate_or_signal_no_norm(
        self,
        *,
        original_query: str,
        jurisdiction: str,
        current_query: str,
        profile: Profile,
        model: str,
    ) -> str | None:
        """Возвращает переформулированный запрос, либо `None`, если LLM
        сигналит `no_norm` (нормы в этой юрисдикции нет)."""
        prompt = (
            f"{profile.system_prompt}\n\n"
            f"Юрисдикция: {jurisdiction}\n"
            f"Исходный запрос: {original_query}\n"
            f"Последний запрос (поиск ничего не нашёл): {current_query}\n\n"
            'Если ты уверен, что такой нормы в этой юрисдикции в принципе не '
            'существует (не "поиск не нашёл", а "требования нет") — ответь '
            'СТРОГО JSON {"no_norm": true}. Иначе предложи переформулировку '
            'запроса для повторного поиска: {"reformulated_query": "..."}.'
        )
        answer = self._llm.complete(prompt, model)
        _trace_llm_call(self._tracer, self._role, self._llm, model, prompt, answer)
        data = _parse_json_answer(answer, who="Retriever")
        if data.get("no_norm") is True:
            return None
        reformulated = data.get("reformulated_query")
        if not reformulated:
            raise AgentLLMError(
                f"Retriever: LLM не дала ни no_norm, ни reformulated_query: {answer!r}"
            )
        return reformulated


@dataclass
class Verdict:
    passed: bool
    reason: str
    model: str


class Verifier:
    """Независимая проверка producer-результата. Промпт собирается ТОЛЬКО
    из `(question, fragment, source, profile)` — сигнатура `run` физически
    не принимает рассуждения producer-шага, это гарантия независимости на
    уровне интерфейса, а не дисциплины вызывающего кода.

    Модель verifier'а — параметр конструктора, а не что-то, что Verifier
    выбирает сам: её вычисляет вызывающий код через `verifier_model_for`,
    Verifier лишь обязан её использовать и вернуть в `Verdict.model`."""

    def __init__(
        self,
        llm: AgentLLMClient,
        model: str,
        *,
        tracer: "Tracer | None" = None,
        role: str = "verifier",
    ):
        self._llm = llm
        self._model = model
        self._tracer = tracer
        self._role = role

    def run(self, question: str, fragment: str, source: str, profile: Profile) -> Verdict:
        prompt = (
            f"{profile.system_prompt}\n\n"
            f"Вопрос: {question}\n"
            f"Фрагмент: {fragment}\n"
            f"Источник: {source}\n\n"
            'Проверь независимо, действительно ли фрагмент отвечает на вопрос '
            'и не противоречит источнику. Ответь СТРОГО JSON '
            '{"passed": true|false, "reason": "..."}.'
        )
        answer = self._llm.complete(prompt, self._model)
        _trace_llm_call(self._tracer, self._role, self._llm, self._model, prompt, answer)
        data = _parse_json_answer(answer, who="Verifier")
        if "passed" not in data:
            raise AgentLLMError(f"Verifier: в ответе LLM нет поля 'passed': {answer!r}")
        return Verdict(passed=bool(data["passed"]), reason=data.get("reason", ""), model=self._model)


class Classifier:
    """Классифицирует текст по `Profile.response_schema`. Модель — по тиру профиля."""

    def __init__(
        self,
        llm: AgentLLMClient,
        models: ModelsConfig | None = None,
        *,
        tracer: "Tracer | None" = None,
        role: str = "classifier",
    ):
        self._llm = llm
        self._models = models or load_models_config()
        self._tracer = tracer
        self._role = role

    def run(self, text: str, profile: Profile) -> dict:
        model = self._models.tiers[profile.tier]
        prompt = (
            f"{profile.system_prompt}\n\n"
            f"Текст: {text}\n\n"
            "Ответь СТРОГО JSON по схеме: "
            f"{json.dumps(profile.response_schema, ensure_ascii=False)}"
        )
        answer = self._llm.complete(prompt, model)
        _trace_llm_call(self._tracer, self._role, self._llm, model, prompt, answer)
        return _parse_json_answer(answer, who="Classifier")


class Summarizer:
    """Сжимает фрагмент в краткое резюме по `Profile.system_prompt`. Модель — по тиру профиля."""

    def __init__(
        self,
        llm: AgentLLMClient,
        models: ModelsConfig | None = None,
        *,
        tracer: "Tracer | None" = None,
        role: str = "summarizer",
    ):
        self._llm = llm
        self._models = models or load_models_config()
        self._tracer = tracer
        self._role = role

    def run(self, fragment: str, profile: Profile) -> str:
        model = self._models.tiers[profile.tier]
        prompt = f"{profile.system_prompt}\n\nФрагмент: {fragment}\n\nСформулируй краткое резюме."
        answer = self._llm.complete(prompt, model)
        _trace_llm_call(self._tracer, self._role, self._llm, model, prompt, answer)
        return answer.strip()
