"""Живой LLM-runner Build-конвейера и мониторинга: Claude API (Волна 2).

Контракт — `Callable[[prompt, model], tuple[str, dict]]` для `RunnerAgentLLM`
(`llm_client.py`): tuple-форма несёт РЕАЛЬНЫЕ токены бэкенда, и `Tracer`
пишет в `pipeline.llm_calls` фактический расход, а не оценку len//4.

Модель приходит параметром из `models.yaml: tiers` — раннер моделей не выбирает.
Потолок вызовов на процесс: IMPORTER_LLM_MAX_CALLS (страховка от разгона цикла;
денежный контроль — `python -m importer build cost --run <id>` по трейсингу).
Ключ: стандартный ANTHROPIC_API_KEY (SDK читает окружение сам); .env.importer
подхватывается тем же load_dotenv, что и importer/db.py.
"""
from __future__ import annotations

import os

from dotenv import load_dotenv

from importer.build.llm_client import AgentLLMError

load_dotenv(".env.importer")

DEFAULT_MAX_TOKENS = 8192
DEFAULT_MAX_CALLS = 400


class AnthropicRunner:
    """runner(prompt, model) -> (text, usage). Ленивая инициализация клиента:
    построение реестра шагов/агентов не требует ключа — падает только
    реальный вызов модели (тот же принцип, что у прежних заглушек)."""

    def __init__(self, client=None, *, max_tokens: int = DEFAULT_MAX_TOKENS,
                 max_calls: int | None = None) -> None:
        self._client = client
        self._max_tokens = max_tokens
        if max_calls is None:
            raw = os.environ.get("IMPORTER_LLM_MAX_CALLS", "")
            max_calls = int(raw) if raw.isdigit() else DEFAULT_MAX_CALLS
        self._max_calls = max_calls
        self.calls = 0

    def _ensure_client(self):
        if self._client is None:
            if not (os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")):
                raise AgentLLMError(
                    "нет ANTHROPIC_API_KEY: задать в .env.importer (см. .env.importer.example)")
            import anthropic
            self._client = anthropic.Anthropic()
        return self._client

    def __call__(self, prompt: str, model: str) -> tuple[str, dict]:
        if self.calls >= self._max_calls:
            raise AgentLLMError(
                f"потолок вызовов исчерпан: {self.calls}/{self._max_calls} "
                "(IMPORTER_LLM_MAX_CALLS)")
        self.calls += 1
        client = self._ensure_client()
        import anthropic
        try:
            resp = client.messages.create(
                model=model, max_tokens=self._max_tokens,
                messages=[{"role": "user", "content": prompt}])
        except anthropic.APIStatusError as exc:
            raise AgentLLMError(f"Claude API {exc.status_code}: {exc.message}") from exc
        except anthropic.APIConnectionError as exc:
            raise AgentLLMError(f"Claude API недоступен: {exc}") from exc
        if resp.stop_reason == "refusal":
            raise AgentLLMError("Claude API: refusal — классификатор отклонил запрос")
        text = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")
        return text, {"input_tokens": resp.usage.input_tokens,
                      "output_tokens": resp.usage.output_tokens}


def make_live_runner() -> AnthropicRunner:
    return AnthropicRunner()
