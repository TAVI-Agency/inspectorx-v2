import json
import pytest
from importer.llm import LLM, LLMError


def test_convert_to_schema_plain_json():
    payload = {"product": {"name": "x"}, "requirements": []}
    llm = LLM(runner=lambda prompt: json.dumps(payload))
    assert llm.convert_to_schema("# отчёт", "product") == payload


def test_convert_to_schema_json_in_prose():
    payload = {"a": 1}
    llm = LLM(runner=lambda prompt: f"Вот JSON:\n```json\n{json.dumps(payload)}\n```\nготово")
    assert llm.convert_to_schema("md", "product") == payload


def test_convert_to_schema_garbage_raises():
    llm = LLM(runner=lambda prompt: "не могу")
    with pytest.raises(LLMError):
        llm.convert_to_schema("md", "product")


def test_same_meaning():
    assert LLM(runner=lambda p: "Да, смысл совпадает").same_meaning("a", "b") is True
    assert LLM(runner=lambda p: "Нет").same_meaning("a", "b") is False
