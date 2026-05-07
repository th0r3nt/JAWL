"""
Схема вызова инструмента для генерации дерева мыслей (Tree of Thoughts).
Использует рекурсивную структуру (фрактал) для создания вложенных веток (сценариев).
"""

from typing import List, Optional
from pydantic import BaseModel, Field


class ThoughtBranch(BaseModel):
    name: str
    description: str
    pros: List[str] = Field(default_factory=list)
    cons: List[str] = Field(default_factory=list)
    # Рекурсивная ссылка на саму себя для вложенных сценариев
    sub_branches: Optional[List["ThoughtBranch"]] = Field(default_factory=list)


# Компилируем рекурсивную схему Pydantic
ThoughtBranch.model_rebuild()


class TreeResponse(BaseModel):
    branches: List[ThoughtBranch] = Field(default_factory=list)


TOT_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "submit_tree",
            "description": "Отправляет сгенерированное рекурсивное дерево мыслей в систему.",
            "parameters": {
                "type": "object",
                "properties": {
                    "branches": {
                        "type": "array",
                        "description": "Список макро-стратегий (веток верхнего уровня).",
                        "items": {"$ref": "#/$defs/ThoughtBranch"},
                    }
                },
                "required": ["branches"],
                "additionalProperties": False,
                "$defs": {
                    "ThoughtBranch": {
                        "type": "object",
                        "properties": {
                            "name": {  # Название ветки
                                "type": "string",
                                "description": "Короткое название стратегии/пути.",
                            },
                            "description": {  # Описание ветки
                                "type": "string",
                                "description": "Подробное описание логики или тактики.",
                            },
                            "pros": {  # Плюсы ветки
                                "type": "array",
                                "description": "Список плюсов и преимуществ этого пути.",
                                "items": {"type": "string"},
                            },
                            "cons": {  # Минусы ветки
                                "type": "array",
                                "description": "Список минусов, рисков и уязвимостей этого пути.",
                                "items": {"type": "string"},
                            },
                            "sub_branches": {  # Вложенные ветки
                                "type": "array",
                                "description": "Вложенные сценарии (микро-тактики).",
                                "items": {"$ref": "#/$defs/ThoughtBranch"},
                            },
                        },
                        "required": [
                            "name",
                            "description",
                        ],  # Убрали pros и cons из обязательных
                        "additionalProperties": False,
                    }
                },
            },
        },
    }
]
