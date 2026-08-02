"""Question writer (Задача 16): генерация уточняющих вопросов для поиска норм.

Карта Cartographer'а (`importer/build/cartographer.py`) описывает конкретные
требования (`expected_item`) на высоком уровне. Question writer преобразует каждое
требование в серию уточняющих вопросов для Retriever'а (Задача 17): вопросы
помогут системе поиска норм в LegalX точнее сформулировать SQL/семантический
запрос.

`write_questions(item: MapItem) -> list[Question]` использует cheap-тир LLM
(`Profile.tier = 'cheap'`), генерирует ≥2 вопроса на айтем. Каждый вопрос
содержит:
- `text`: строка с вопросом естественного языка;
- `expected_schema`: JSON Schema (dict) ожидаемого ответа поиска (фрагмент нормы:
  реквизит акта, статья, текст, применимость).

LLM-ответ — JSON-массив вопросов; валидация: не-массив / пустой / невалидная
схема элемента → повторный запрос (1 ретрай), затем ValueError.

Валидация JSON Schema: минимальная структурная проверка (dict, есть "type" или
"properties") — без новой зависимости jsonschema.
"""
from __future__ import annotations

import json
from dataclasses import dataclass

from importer.build.agents import load_models_config
from importer.build.llm_client import AgentLLMClient, AgentLLMError


@dataclass(frozen=True)
class MapItem:
    """Айтем карты требований (результат Cartographer'а)."""

    expected_item: str
    category_slug: str
    rationale: str
    benchmark_countries: list[str]


@dataclass(frozen=True)
class Question:
    """Уточняющий вопрос для поиска норм."""

    text: str
    expected_schema: dict


class QuestionWriterError(AgentLLMError):
    """Ошибка при генерации вопросов LLM."""


def _is_valid_json_schema(obj: dict) -> bool:
    """Минимальная валидация JSON Schema (dict с 'type' или 'properties')."""
    if not isinstance(obj, dict):
        return False
    return "type" in obj or "properties" in obj


def _validate_questions(data: list[dict]) -> list[Question]:
    """Валидирует JSON-ответ LLM и возвращает список Question.

    Проверяет:
    - data — список (не None, не пустой);
    - каждый элемент — dict с полями text и expected_schema;
    - expected_schema — валидная JSON Schema.

    Может вызвать QuestionWriterError при валидации.
    """
    if not isinstance(data, list) or len(data) == 0:
        raise QuestionWriterError("LLM вернула не-массив или пустой массив")

    questions: list[Question] = []
    for i, item in enumerate(data):
        if not isinstance(item, dict):
            raise QuestionWriterError(f"Элемент {i}: ожидается dict, получено {type(item)}")
        if "text" not in item or "expected_schema" not in item:
            raise QuestionWriterError(
                f"Элемент {i}: не хватает полей text или expected_schema: {item!r}"
            )

        text = item["text"]
        schema = item["expected_schema"]

        if not isinstance(text, str) or not text.strip():
            raise QuestionWriterError(f"Элемент {i}: text должна быть непустой строкой")
        if not isinstance(schema, dict) or not _is_valid_json_schema(schema):
            raise QuestionWriterError(
                f"Элемент {i}: expected_schema должна быть валидной JSON Schema "
                f"(dict с type или properties), получено: {schema!r}"
            )

        questions.append(Question(text=text, expected_schema=schema))

    if len(questions) < 2:
        raise QuestionWriterError(f"LLM вернула {len(questions)} вопросов, ожидается ≥2")

    return questions


def _build_prompt(item: MapItem) -> str:
    """Формирует промпт для LLM для генерации вопросов."""
    return (
        "Ты — Question Writer, эксперт по юридическому поиску. "
        "Твоя задача — генерировать уточняющие вопросы, которые помогут системе "
        "поиска норм точнее найти релевантные требования.\n\n"
        f"Требование: {item.expected_item}\n"
        f"Категория: {item.category_slug}\n"
        f"Обоснование: {item.rationale}\n"
        f"Бенчмарк-страны: {', '.join(item.benchmark_countries)}\n\n"
        "Сгенерируй МИНИМУМ 2 уточняющих вопроса в естественном языке (на русском), "
        "которые помогут поиску норм в юридической базе точнее сформулировать "
        "запрос для этого требования.\n\n"
        "Для каждого вопроса предоставь также JSON Schema ожидаемого ответа "
        "(фрагмент норм должен содержать текст требования, источник, статью, "
        "применимость).\n\n"
        'Ответь СТРОГО JSON-массивом объектов вида '
        '{"text": "вопрос", "expected_schema": {"type": "object", "properties": {...}}}. '
        "Ничего, кроме JSON-массива, в ответе быть не должно."
    )


def write_questions(item: MapItem, *, llm: AgentLLMClient) -> list[Question]:
    """Генерирует уточняющие вопросы для поиска норм по айтему карты.

    Args:
        item: MapItem из карты Cartographer'а.
        llm: AgentLLMClient для вызова LLM (инжектируется).

    Returns:
        Список Question (≥2).

    Raises:
        ValueError: если после 1 ретрая оба вызова LLM дали ошибку.
    """
    config = load_models_config()
    cheap_model = config.tiers["cheap"]
    prompt = _build_prompt(item)

    # Первая попытка
    try:
        answer = llm.complete(prompt, cheap_model)
        data = json.loads(answer)
        return _validate_questions(data)
    except (json.JSONDecodeError, QuestionWriterError) as e:
        first_error = str(e)
    except Exception as e:
        first_error = f"{type(e).__name__}: {e}"

    # Ретрай
    try:
        answer = llm.complete(prompt, cheap_model)
        data = json.loads(answer)
        return _validate_questions(data)
    except (json.JSONDecodeError, QuestionWriterError) as e:
        second_error = str(e)
    except Exception as e:
        second_error = f"{type(e).__name__}: {e}"

    # Оба вызова дали ошибку
    raise ValueError(
        f"Question writer: retries exhausted. "
        f"First error: {first_error}. Second error: {second_error}"
    )
