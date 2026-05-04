"""
Схема вызова инструмента для генерации дерева мыслей (Tree of Thoughts).
Принуждает модель возвращать структурированный JSON с ветками (стратегиями).
"""

from typing import List, Optional
from pydantic import BaseModel, Field


class ThoughtBranch(BaseModel):
    name: str
    description: str
    estimated_speed: Optional[str] = None
    complexity: Optional[str] = None
    risk_assessment: Optional[str] = None


class TreeResponse(BaseModel):
    branches: List[ThoughtBranch] = Field(default_factory=list)


TOT_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "submit_tree",
            "description": "Отправляет сгенерированное дерево мыслей (стратегий) в систему.",
            "parameters": {
                "type": "object",
                "properties": {
                    "branches": {
                        "type": "array",
                        "description": "Список предложенных веток мыслей.",
                        "items": {
                            "type": "object",
                            "properties": {
                                "name": {
                                    "type": "string",
                                    "description": "Короткое название стратегии/пути.",
                                },
                                "description": {
                                    "type": "string",
                                    "description": "Подробное концептуальное описание логики: плюсы, минусы, какие действия стоит применить.",
                                },
                                "estimated_speed": {
                                    "type": "string",
                                    "description": "(опционально) Оценка скорости выполнения (например: 'Быстро (1-2 шага)', 'Медленно (много итераций)').",
                                },
                                "complexity": {
                                    "type": "string",
                                    "description": "(опционально) Оценка сложности реализации (например: 'Низкая', 'Высокая (требует написания кода)').",
                                },
                                "risk_assessment": {
                                    "type": "string",
                                    "description": "(опционально) Оценка рисков (например: 'Безопасно', 'Риск блокировки IP', 'Риск SyntaxError').",
                                },
                            },
                            "required": ["name", "description"],
                            "additionalProperties": False,
                        },
                    }
                },
                "required": ["branches"],
                "additionalProperties": False,
            },
        },
    }
]
