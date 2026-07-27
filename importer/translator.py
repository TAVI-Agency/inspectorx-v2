"""Стадия перевода витринных полей UZ→RU (фаза 2 UZ-first, спека 2026-07-16 §2).

Инвариант: юридические цитаты (legal_quote_*) моделью НЕ переводятся никогда —
они в промпт не попадают. Переводится только закрытый whitelist витринных полей.
Ошибка LLM не блокирует публикацию: None → карточка публикуется UZ-only (честно),
задача перевода остаётся на следующий прогон.
"""
import json
import re
from pathlib import Path

from importer.llm import LLM, LLMError

GLOSSARY_PATH = Path(__file__).resolve().parent.parent / "research-loop" / "glossary-uz-ru.md"


def load_glossary() -> str:
    if GLOSSARY_PATH.exists():
        return GLOSSARY_PATH.read_text(encoding="utf-8")
    return ""


def _payload(req) -> dict:
    """Whitelist витринных полей — юрцитаты сюда не попадают по построению."""
    return {
        "title": req.title,
        "summary": req.summary,
        "how_to_steps": [h.step for h in req.how_to],
        "documents": [{"name": d.name, "where": d.where} for d in req.documents],
        "sanction_extra": req.sanction.extra if req.sanction else None,
    }


def translate_card_fields(req, llm: LLM | None) -> dict | None:
    """UZ→RU перевод витринных полей. None = перевода нет (публикуем UZ-only)."""
    if llm is None:
        return None
    payload = _payload(req)
    prompt = (
        "Переведи витринные поля карточки юридического требования с узбекского на "
        "русский. Это НЕ юридическая цитата — только заголовок, описание, шаги и "
        "названия документов. Термины переводи по глоссарию ниже. Сохрани структуру "
        "JSON в точности (те же ключи, та же длина списков); null оставляй null. "
        "Ответ — ТОЛЬКО JSON, без пояснений.\n\n"
        f"=== ГЛОССАРИЙ ===\n{load_glossary()}\n\n"
        f"=== ПОЛЯ (JSON) ===\n{json.dumps(payload, ensure_ascii=False)}"
    )
    try:
        answer = llm.complete(prompt)
    except LLMError:
        return None
    for candidate in (answer, *re.findall(r"\{.*\}", answer, re.DOTALL)):
        try:
            data = json.loads(candidate.strip())
        except json.JSONDecodeError:
            continue
        if not isinstance(data, dict) or not data.get("title"):
            continue
        steps = data.get("how_to_steps") or []
        docs = data.get("documents") or []
        if len(steps) != len(payload["how_to_steps"]) or len(docs) != len(payload["documents"]):
            return None  # структура поехала — честнее UZ-only, чем кривой перевод
        return data
    return None
