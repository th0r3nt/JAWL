"""
Универсальная схема для вызова инструментов агентом.
Заставляет LLM генерировать 'thoughts' перед массивом 'actions',
обеспечивая механизм Chain-of-Thought (CoT).
"""

from typing import Any
from pydantic import BaseModel, Field


class ActionCall(BaseModel):
    """Типизированная модель вызова одного инструмента."""

    tool_name: str
    parameters: dict[str, Any] = Field(default_factory=dict)


class AgentResponse(BaseModel):
    """Типизированная схема полного ответа LLM."""

    thoughts: str
    actions: list[ActionCall] = Field(default_factory=list)


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
