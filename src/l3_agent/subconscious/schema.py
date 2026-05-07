"""
Схемы и структуры данных для подсознательных моделей (Subconscious Patterns).
"""

from enum import Enum


class Pattern(str, Enum):
    """Доступные паттерны поведения подсознания."""

    CONSOLIDATION = "consolidation"
    REFLECTION = "reflection"
    FORGETTING = "forgetting"