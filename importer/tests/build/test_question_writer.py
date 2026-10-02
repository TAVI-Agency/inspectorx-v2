"""Question writer (Задача 16): генерация уточняющих вопросов для поиска норм.

Сценарии из брифа Задачи 16:
- валидный ответ LLM (JSON-массив ≥2 вопросов) → список Question с text и expected_schema;
- ответ не-JSON / не-массив / пустой массив → повторный запрос (1 ретрай);
- 2-й попыткой тоже ошибка → ValueError.
- Валидация JSON Schema: минимальная (dict с "type" или "properties").
"""
from __future__ import annotations

import json

import pytest

from importer.build.llm_client import AgentLLMError
from importer.build.question_writer import MapItem, Question, write_questions


# ── тестовые дублёры ────────────────────────────────────────────────────


class ScriptedLLM:
    """Мок AgentLLMClient: отдаёт ответы по очереди, фиксирует все (prompt, model)."""

    def __init__(self, responses: list[str]):
        self._responses = list(responses)
        self.calls: list[tuple[str, str]] = []

    def complete(self, prompt: str, model: str) -> str:
        self.calls.append((prompt, model))
        if not self._responses:
            raise AssertionError("ScriptedLLM: запросили ответ сверх скрипта — лишний вызов LLM")
        return self._responses.pop(0)


def map_item(**over) -> MapItem:
    """Вспомогательная фабрика для создания тестовых айтемов карты."""
    base = dict(
        expected_item="акцизная марка на пачке сигарет",
        category_slug="marking",
        rationale="во всех бенчмарк-странах маркировка табака обязательна",
        benchmark_countries=["KZ", "AE", "DE"],
    )
    return MapItem(**{**base, **over})


def valid_questions(*questions: dict) -> str:
    """Формирует валидный JSON-ответ с вопросами."""
    if not questions:
        questions = (
            {
                "text": "Каковы требования к акцизной марке на пачке сигарет?",
                "expected_schema": {
                    "type": "object",
                    "properties": {
                        "requirement": {"type": "string"},
                        "source": {"type": "string"},
                    },
                },
            },
            {
                "text": "Какие страны требуют обязательную маркировку?",
                "expected_schema": {
                    "type": "object",
                    "properties": {
                        "countries": {"type": "array", "items": {"type": "string"}},
                    },
                },
            },
        )
    return json.dumps(list(questions), ensure_ascii=False)


# ── write_questions: валидный ответ LLM ─────────────────────────────────


def test_write_questions_returns_list_of_questions():
    llm = ScriptedLLM([valid_questions()])
    questions = write_questions(map_item(), llm=llm)

    assert isinstance(questions, list)
    assert len(questions) >= 2
    for q in questions:
        assert isinstance(q, Question)
        assert isinstance(q.text, str)
        assert isinstance(q.expected_schema, dict)


def test_write_questions_for_marking_category():
    """Сценарий из брифа: категория 'marking' — акцизная марка."""
    llm = ScriptedLLM([valid_questions()])
    item = map_item(category_slug="marking", expected_item="акцизная марка на пачке сигарет")
    questions = write_questions(item, llm=llm)

    assert len(questions) == 2
    assert all(q.text and q.expected_schema for q in questions)
    # Проверка, что schema содержит необходимые ключи
    for q in questions:
        assert isinstance(q.expected_schema, dict)


def test_write_questions_uses_cheap_tier_model():
    """Question writer должен использовать cheap-тир модели."""
    from importer.build.agents import load_models_config

    llm = ScriptedLLM([valid_questions()])
    write_questions(map_item(), llm=llm)

    config = load_models_config()
    assert len(llm.calls) == 1
    # Проверяем, что использована именно cheap-модель
    assert llm.calls[0][1] == config.tiers["cheap"]


def test_write_questions_prompt_includes_item_details():
    """Промпт должен включать информацию об айтеме карты."""
    llm = ScriptedLLM([valid_questions()])
    item = map_item(
        expected_item="специальное требование",
        category_slug="special",
        rationale="это важно",
    )
    write_questions(item, llm=llm)

    prompt = llm.calls[0][0]
    assert "специальное требование" in prompt or "special" in prompt
    assert len(prompt) > 50  # Достаточно детальный промпт


# ── JSON Schema валидация ────────────────────────────────────────────────


def test_write_questions_validates_schema_structure():
    """expected_schema должна быть валидной JSON Schema (dict с type или properties)."""
    # Валидные схемы
    valid_schemas = [
        {"type": "string"},
        {"type": "object", "properties": {"key": {"type": "string"}}},
        {"properties": {"field": {"type": "number"}}},
    ]
    for schema in valid_schemas:
        questions = [
            {
                "text": "вопрос 1",
                "expected_schema": schema,
            },
            {
                "text": "вопрос 2",
                "expected_schema": {"type": "string"},
            }
        ]
        llm = ScriptedLLM([valid_questions(*questions)])
        result = write_questions(map_item(), llm=llm)
        assert len(result) == 2


def test_write_questions_rejects_invalid_schema_structure():
    """Невалидная схема (не dict или без type/properties) вызывает ретрай."""
    invalid_then_valid = [
        json.dumps([{"text": "q", "expected_schema": "строка, а не dict"}]),
        valid_questions(),
    ]
    llm = ScriptedLLM(invalid_then_valid)
    questions = write_questions(map_item(), llm=llm)

    # Должен было произойти ретрай
    assert len(llm.calls) == 2
    assert len(questions) >= 2


# ── деградация LLM-ответа с ретраем ──────────────────────────────────────


def test_write_questions_retries_on_non_json():
    """Не-JSON ответ → ретрай с valid_questions на второй попытке."""
    llm = ScriptedLLM(["это не JSON", valid_questions()])
    questions = write_questions(map_item(), llm=llm)

    assert len(llm.calls) == 2
    assert len(questions) >= 2


def test_write_questions_retries_on_non_array():
    """Не-массив JSON → ретрай."""
    llm = ScriptedLLM([
        json.dumps({"text": "вопрос", "expected_schema": {}}),
        valid_questions(),
    ])
    questions = write_questions(map_item(), llm=llm)

    assert len(llm.calls) == 2
    assert len(questions) >= 2


def test_write_questions_retries_on_empty_array():
    """Пустой массив → ретрай."""
    llm = ScriptedLLM([json.dumps([]), valid_questions()])
    questions = write_questions(map_item(), llm=llm)

    assert len(llm.calls) == 2
    assert len(questions) >= 2


def test_write_questions_retries_on_missing_fields():
    """Вопрос без required полей (text или expected_schema) → ретрай."""
    llm = ScriptedLLM([
        json.dumps([{"text": "только text", "expected_schema": None}]),
        valid_questions(),
    ])
    questions = write_questions(map_item(), llm=llm)

    assert len(llm.calls) == 2
    assert len(questions) >= 2


def test_write_questions_raises_after_retry_exhausted():
    """После 1 ретрая оба вызова дали ошибку → ValueError."""
    llm = ScriptedLLM(["не JSON", "тоже не JSON"])
    with pytest.raises(ValueError) as exc_info:
        write_questions(map_item(), llm=llm)

    assert len(llm.calls) == 2
    assert "retries exhausted" in str(exc_info.value).lower() or "ошибка" in str(exc_info.value).lower()


def test_write_questions_raises_if_only_invalid_schemas_remain():
    """Если после ретрая все вопросы с невалидной схемой → ValueError."""
    bad_schemas = [
        {"text": "q1", "expected_schema": None},
        {"text": "q2", "expected_schema": "invalid"},
    ]
    llm = ScriptedLLM([
        json.dumps(bad_schemas),
        json.dumps(bad_schemas),
    ])
    with pytest.raises(ValueError):
        write_questions(map_item(), llm=llm)


# ── MapItem и Question структуры ─────────────────────────────────────────


def test_map_item_structure():
    """MapItem должна содержать все необходимые поля."""
    item = map_item(
        expected_item="тестовое требование",
        category_slug="test_cat",
        rationale="важно это",
        benchmark_countries=["US", "EU"],
    )

    assert item.expected_item == "тестовое требование"
    assert item.category_slug == "test_cat"
    assert item.rationale == "важно это"
    assert item.benchmark_countries == ["US", "EU"]


def test_question_structure():
    """Question должна содержать text и expected_schema."""
    schema = {"type": "string"}
    q = Question(text="Вопрос?", expected_schema=schema)

    assert q.text == "Вопрос?"
    assert q.expected_schema == schema
    assert isinstance(q.expected_schema, dict)


# ── MapItem.from_payload (Задача 4): карта Cartographer'а с `sources` ───


def test_map_item_from_payload_ignores_unknown_fields():
    """`sources` — поле карты (Задача 4), не поле MapItem: from_payload его
    молча отбрасывает."""
    item = MapItem.from_payload({
        "expected_item": "x", "category_slug": "c", "rationale": "r",
        "benchmark_countries": [], "sources": ["u"],
    })

    assert item == MapItem(expected_item="x", category_slug="c", rationale="r",
                            benchmark_countries=[])
    assert not hasattr(item, "sources")


def test_map_item_from_payload_defaults_missing_optional_fields():
    """`rationale`/`benchmark_countries` отсутствуют в payload (напр., в
    `discovery.py` они не всегда сохранены) -> пустая строка/пустой список."""
    item = MapItem.from_payload({"expected_item": "x", "category_slug": "c"})

    assert item.rationale == ""
    assert item.benchmark_countries == []


def test_map_item_from_payload_handles_null_benchmark_countries():
    # Когда benchmark_countries = null в payload, from_payload не должна падать
    # с TypeError, а должна установить benchmark_countries = []
    entry = {
        "expected_item": "Маркировка",
        "category_slug": "marking",
        "rationale": "обоснование",
        "benchmark_countries": None  # null вместо массива
    }
    
    item = MapItem.from_payload(entry)
    
    assert item.expected_item == "Маркировка"
    assert item.category_slug == "marking"
    assert item.rationale == "обоснование"
    assert item.benchmark_countries == []


def test_map_item_from_payload_ignores_extra_fields():
    # from_payload должна игнорировать лишние поля, такие как sources (Задача 4)
    entry = {
        "expected_item": "Требование",
        "category_slug": "cert",
        "rationale": "причина",
        "benchmark_countries": ["KZ"],
        "sources": ["https://lex.uz/1"]  # лишнее поле
    }
    
    item = MapItem.from_payload(entry)
    
    assert item.expected_item == "Требование"
    assert item.category_slug == "cert"
    assert item.rationale == "причина"
    assert item.benchmark_countries == ["KZ"]
    # sources не попала в MapItem
    assert not hasattr(item, "sources")


def test_map_item_from_payload_missing_optional_fields():
    # rationale и benchmark_countries опциональны, дефолт пустые
    entry = {
        "expected_item": "Минимальное",
        "category_slug": "mark"
    }
    
    item = MapItem.from_payload(entry)
    
    assert item.rationale == ""
    assert item.benchmark_countries == []
