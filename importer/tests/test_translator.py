import json

import pytest

from importer.llm import LLM, LLMError
from importer.models import ProductRequirement
from importer.translator import translate_card_fields

QUOTE_SENTINEL = "MAXFIY-IQTIBOS-SENTINEL modda matni"

BASE = {
    "title": "Litsenziya olish", "nature": "obligation", "type": "product",
    "category": "прочее", "summary": "Faoliyat uchun litsenziya kerak",
    "legal_quote_uz": QUOTE_SENTINEL,
    "legal_quote_ru": "RU-" + QUOTE_SENTINEL,
    "act": {"name": "ЗРУ-819", "number": "819", "date": "2023-02-27",
            "lexuz_url": "https://lex.uz/docs/6392314"},
    "unit": "ст. 24", "scope": {"level": "all"}, "addressees": ["all"],
    "how_to": [{"step": "Ariza topshirish"}], "documents": [{"name": "Guvohnoma"}],
    "sanction": {"article": "ст. 46", "extra": "jarima 50%"},
    "needs_review": False, "content_lang": "uz",
}


def req(**over):
    return ProductRequirement.model_validate({**BASE, **over})


def fake_llm(response: str, seen: list):
    def runner(prompt: str) -> str:
        seen.append(prompt)
        return response
    return LLM(runner=runner)


def ok_response():
    return json.dumps({
        "title": "Получить лицензию", "summary": "Для деятельности нужна лицензия",
        "how_to_steps": ["Подать заявление"], "documents": [{"name": "Свидетельство",
                                                             "where": None}],
        "sanction_extra": "штраф 50%",
    }, ensure_ascii=False)


def test_translates_whitelisted_fields():
    seen = []
    out = translate_card_fields(req(), fake_llm(ok_response(), seen))
    assert out["title"] == "Получить лицензию"
    assert out["how_to_steps"] == ["Подать заявление"]
    assert out["documents"][0]["name"] == "Свидетельство"
    assert out["sanction_extra"] == "штраф 50%"


def test_legal_quotes_never_reach_prompt():
    # Инвариант спеки: юрцитаты не переводятся моделью НИКОГДА.
    seen = []
    translate_card_fields(req(), fake_llm(ok_response(), seen))
    assert len(seen) == 1
    assert QUOTE_SENTINEL not in seen[0]


def test_glossary_included_in_prompt():
    seen = []
    translate_card_fields(req(), fake_llm(ok_response(), seen))
    assert "ГЛОССАРИЙ" in seen[0] and "litsenziya — лицензия" in seen[0]


def test_llm_error_returns_none():
    def boom(prompt):
        raise LLMError("нет сети")
    assert translate_card_fields(req(), LLM(runner=boom)) is None


def test_no_llm_returns_none():
    assert translate_card_fields(req(), None) is None


def test_structure_drift_returns_none():
    # LLM потеряла шаг → честнее UZ-only, чем кривой перевод
    drifted = json.loads(ok_response())
    drifted["how_to_steps"] = []
    out = translate_card_fields(req(), fake_llm(json.dumps(drifted, ensure_ascii=False), []))
    assert out is None


def test_garbage_answer_returns_none():
    assert translate_card_fields(req(), fake_llm("не могу перевести", [])) is None
