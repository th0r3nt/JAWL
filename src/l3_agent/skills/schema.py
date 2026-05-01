"""
Универсальная Pydantic схема для вызова инструментов агентом.

Определяет JSON Schema, которую ожидает OpenAI API (или совместимые).
Заставляет LLM генерировать 'thoughts' ДО массива 'actions', что обеспечивает
аппаратную реализацию механизма Chain-of-Thought (CoT). Модель сначала "думает", а потом "действует".
"""

from typing import Any, Dict, List
from pydantic import BaseModel, Field


class ActionCall(BaseModel):
    """
    Типизированная модель вызова одного инструмента.
    """

    tool_name: str
    parameters: Dict[str, Any] = Field(default_factory=dict)


class AgentResponse(BaseModel):
    """
    Типизированная схема полного ответа LLM.
    Содержит внутренний монолог и массив параллельных действий.
    """

    thoughts: str
    actions: List[ActionCall] = Field(default_factory=list)


# Константа, которая отправляется в параметр 'tools' API языковой модели
ACTION_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "execute_skill",
            "description": "Главный интерфейс взаимодействия с внешним миром и базами данных. Обязателен к вызову для любых действий.",
            "parameters": {
                "type": "object",
                "properties": {
                    "thoughts": {
                        "type": "string",
                        "description": "Цепочка рассуждений/мыслей перед действием.",
                    },
                    "actions": {
                        "type": "array",
                        "description": "Список действий для параллельного выполнения.",
                        "items": {
                            "type": "object",
                            "properties": {
                                "tool_name": {
                                    "type": "string",
                                    "description": "Точное имя функции.",
                                },
                                "parameters": {
                                    "type": "object",
                                    "description": "Словарь с аргументами той функции, которую нужно вызвать. Ключи должны точно совпадать с описанием в 'parameters'.",
                                    "additionalProperties": True,
                                },
                            },
                            "required": ["tool_name", "parameters"],
                            "additionalProperties": False,
                        },
                    },
                },
                "required": ["thoughts", "actions"],
                "additionalProperties": False,
            },
        },
    }
]
