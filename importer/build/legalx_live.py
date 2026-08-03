"""Живой клиент LegalX/SudX (Задача 42, шаг 1): PostgREST RPC по контрактам
ADR-0005 (`search_norms`/`search_cases`, `docs/adr/0005-ecosystem-contracts.md`).
Реализует Protocol `LegalXClient` из `legalx.py` — сигнатуры и семантика
(«пустой результат — не ошибка», `search_cases` только УЗ) описаны там же;
здесь только транспорт: HTTP POST на `{url}/rest/v1/rpc/<rpc>` под read-only
ролью (`apikey`/`Authorization: Bearer`), маппинг JSON-ответа в dataclass'ы
контракта (`NormFragment`/`CourtCase`).

## Ретраи и ошибки

Один ретрай на сетевую ошибку/timeout или HTTP 5xx (обычно значит, что
LegalX временно недоступен/перегружен) — НЕ на 4xx (401/403/422 и т.п. —
ошибка конфигурации или самого запроса, повтор её не исправит). После
исчерпания ретрая или на первом же 4xx — `LegalXLiveError` с кодом и телом
ответа: явная диагностика важнее тихого проглатывания, а Assembler и так
уходит в needs-attention на fail шага (см. `steps_norm.py`/`steps_cases.py`)
— падение клиента здесь не рушит прогон целиком, просто помечает айтем.

Timeout настраиваемый (`timeout=`, default 30s) — конструктор `LiveLegalX`.

## Приёмка на живом LegalX (гейт D1, шаг 2 Задачи 42 — НЕ выполняется этим коммитом)

Когда LegalX почитает `search_norms` (зависимость D1 из мастер-плана):
прогнать `python -m importer build eval-golden` с `LEGALX_BACKEND=live` и
заполненными `LEGALX_SUPABASE_URL`/`LEGALX_SUPABASE_KEY` — retrieval
hit-rate живого поиска должен быть ≥ мокового baseline
(`importer/golden/baseline.json`). Если ниже — список фейлов eval-отчёта
становится готовым ТЗ для LegalX-ветки, а не поводом чинить эвристики
здесь; масштабирование Build за пределы пилотных групп не начинать
(глобальное ограничение ④, `.superpowers/sdd/.../global-constraints.md`).
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

import httpx

from importer.build.legalx import CourtCase, NormFragment

_DEFAULT_TIMEOUT = 30.0
_MAX_ATTEMPTS = 2  # первая попытка + 1 ретрай


class LegalXLiveError(Exception):
    """HTTP-вызов RPC LegalX не вернул 200 (после ретраев) или упал сетевой
    ошибкой (после ретраев) — `status_code` в этом случае `None`."""

    def __init__(self, url: str, status_code: int | None, body: str) -> None:
        self.url = url
        self.status_code = status_code
        self.body = body
        label = status_code if status_code is not None else "network-error"
        super().__init__(f"LegalX RPC {url} -> {label}: {body}")


def _parse_date(value: str | None) -> date | None:
    return date.fromisoformat(value) if value else None


class LiveLegalX:
    """Живой `LegalXClient` (Protocol из `legalx.py`) поверх PostgREST RPC LegalX."""

    def __init__(
        self,
        base_url: str,
        api_key: str,
        timeout: float = _DEFAULT_TIMEOUT,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._client = httpx.Client(timeout=timeout, transport=transport)

    def close(self) -> None:
        self._client.close()

    def _headers(self) -> dict[str, str]:
        return {
            "apikey": self._api_key,
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

    def _rpc(self, name: str, payload: dict) -> list[dict]:
        url = f"{self._base_url}/rest/v1/rpc/{name}"
        last_error: LegalXLiveError | None = None
        for _attempt in range(_MAX_ATTEMPTS):
            try:
                response = self._client.post(url, json=payload, headers=self._headers())
            except httpx.HTTPError as exc:
                # Сетевая ошибка (в т.ч. timeout — httpx.TimeoutException
                # наследует HTTPError) — ретрай, как и 5xx ниже.
                last_error = LegalXLiveError(url=url, status_code=None, body=str(exc))
                continue
            if response.status_code == 200:
                return response.json()
            if 500 <= response.status_code < 600:
                last_error = LegalXLiveError(
                    url=url, status_code=response.status_code, body=response.text,
                )
                continue
            # 4xx (и прочее не-5xx) — конфигурация/запрос сломаны, повтор не
            # поможет: падаем сразу, без ретрая.
            raise LegalXLiveError(
                url=url, status_code=response.status_code, body=response.text,
            )
        assert last_error is not None  # цикл всегда либо вернул(а), либо сюда попал
        raise last_error

    def search_norms(
        self,
        query: str,
        jurisdiction: str,
        domains: list[str] | None = None,
        limit: int = 10,
    ) -> list[NormFragment]:
        rows = self._rpc(
            "search_norms",
            {
                "p_query": query,
                "p_jurisdiction": jurisdiction,
                "p_domains": domains,
                "p_limit": limit,
            },
        )
        return [
            NormFragment(
                fragment_id=row["fragment_id"],
                act_id=row["act_id"],
                act_title=row["act_title"],
                article_ref=row["article_ref"],
                anchor=row["anchor"],
                content=row["content"],
                act_status=row["act_status"],
                valid_from=_parse_date(row.get("valid_from")),
                valid_to=_parse_date(row.get("valid_to")),
                score=float(row["score"]),
            )
            for row in rows
        ]

    def search_cases(
        self,
        article: str,
        topic: str | None = None,
        limit: int = 5,
    ) -> list[CourtCase]:
        rows = self._rpc(
            "search_cases",
            {"p_article": article, "p_topic": topic, "p_limit": limit},
        )
        return [
            CourtCase(
                case_url=row["case_url"],
                case_title=row["case_title"],
                summary=row["summary"],
                outcome=row["outcome"],
                amount=(
                    Decimal(str(row["amount"])) if row.get("amount") is not None else None
                ),
            )
            for row in rows
        ]
