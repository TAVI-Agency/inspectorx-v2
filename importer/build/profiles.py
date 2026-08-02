"""Профиль generic-агента (ADR-0003, решение 3).

Один и тот же движок (`importer/build/agents.py`: Retriever/Verifier/
Classifier/Summarizer) обслуживает разные шаги конвейера — поведение задаёт
не код агента, а `Profile`: системный промпт, JSON Schema ожидаемого ответа
и тир модели (`cheap`/`mid`/`expensive`, см. `models.yaml`).

Конкретные профили шагов (`norm`, `label`, `sanctions`, `cases`, `samples`,
`translation`) в этой задаче не создаются — их вводят Задачи 17+. Здесь —
только контракт `Profile` и опциональный реестр-хелпер, которым эти задачи
смогут воспользоваться, чтобы получать профиль по имени вместо того, чтобы
руками собирать `Profile(...)` в каждом месте использования.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

# Имя профиля = какой шаг конвейера он описывает (ADR-0003).
ProfileName = Literal["norm", "label", "sanctions", "cases", "samples", "translation"]
# Тир модели = ключ в `models.yaml` -> `tiers`.
ModelTier = Literal["cheap", "mid", "expensive"]


@dataclass(frozen=True)
class Profile:
    """Профиль generic-агента. Неизменяемый — один объект безопасно
    переиспользовать между вызовами разных агентов и запусков."""

    name: ProfileName
    system_prompt: str
    response_schema: dict
    tier: ModelTier


# Реестр профилей по имени — наполняется Задачами 17+ через `register_profile`.
# Пуст в этой задаче намеренно: инстансы конкретных профилей здесь не создаются.
_REGISTRY: dict[str, Profile] = {}


def register_profile(profile: Profile) -> Profile:
    """Регистрирует профиль под `profile.name`, возвращает его же (удобно
    для `FOO_PROFILE = register_profile(Profile(...))` в модуле профиля)."""
    _REGISTRY[profile.name] = profile
    return profile


def get_profile(name: str) -> Profile:
    """Возвращает зарегистрированный профиль по имени.

    Пока профили не заведены (Задачи 17+), любой вызов честно падает —
    лучше явная ошибка, чем молчаливый `None` дальше по цепочке агентов.
    """
    try:
        return _REGISTRY[name]
    except KeyError as exc:
        raise KeyError(
            f"Профиль {name!r} не зарегистрирован — конкретные профили шагов "
            "вводятся Задачами 17+ (см. docs/adr/0003-agent-flow.md)"
        ) from exc
