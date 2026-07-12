"""LLM-шаги импортёра. Бэкенд v1 — claude -p (подписка); runner инжектируется в тестах."""
import json
import re
import subprocess
from typing import Callable


class LLMError(Exception):
    pass


def _claude_cli(prompt: str) -> str:
    proc = subprocess.run(
        ["claude", "-p", "--output-format", "text"],
        input=prompt, capture_output=True, text=True, timeout=300,
    )
    if proc.returncode != 0:
        raise LLMError(f"claude -p завершился с кодом {proc.returncode}: {proc.stderr[:500]}")
    return proc.stdout


_SCHEMA_HINT = {
    "product": '{"product": {"name","hs_code","ikpu","domain","duty","excise","vat"}, '
               '"requirements": [{"title","nature","type","category","summary","legal_quote_ru",'
               '"act":{"name","number","date","lexuz_url"},"unit","edition_date",'
               '"scope":{"level","codes","list_row"},"addressees","agency","how_to","documents",'
               '"sanction","discovered_via","needs_review"}]}',
    "service": '{"service": {"name","okved","admission_type","licensor","related_products"}, '
               '"requirements": [{"title","nature","stage","periodicity","summary","legal_quote_ru",'
               '"act":{"name","number","date","lexuz_url"},"unit","edition_date","scope",'
               '"addressees","agency","how_to","documents","sanction","discovered_via","needs_review"}]}',
}


class LLM:
    def __init__(self, runner: Callable[[str], str] | None = None):
        self._runner = runner or _claude_cli

    def complete(self, prompt: str) -> str:
        return self._runner(prompt)

    def convert_to_schema(self, markdown: str, kind: str) -> dict:
        prompt = (
            "Ниже отчёт deep research. Извлеки из него данные СТРОГО в JSON по схеме "
            f"{_SCHEMA_HINT[kind]}. Неизвестное значение = null. Ничего не выдумывай: "
            "бери только то, что есть в отчёте. Ответ — ТОЛЬКО JSON, без пояснений.\n\n"
            f"=== ОТЧЁТ ===\n{markdown}"
        )
        answer = self.complete(prompt)
        for candidate in (answer, *re.findall(r"\{.*\}", answer, re.DOTALL)):
            try:
                return json.loads(candidate.strip())
            except json.JSONDecodeError:
                continue
        raise LLMError("LLM не вернула валидный JSON")

    def same_meaning(self, quote: str, paragraph: str) -> bool:
        prompt = (
            "Сравни цитату нормы и официальный текст пункта. Это ОДНА И ТА ЖЕ норма "
            "(допустимы редакционные отличия)? Ответь одним словом: Да или Нет.\n\n"
            f"ЦИТАТА: {quote}\n\nТЕКСТ ПУНКТА: {paragraph}"
        )
        return self.complete(prompt).strip().lower().startswith(("да", "yes"))
