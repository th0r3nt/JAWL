"""
Универсальная схема для вызова инструментов агентом.
Заставляет LLM генерировать 'thoughts' перед массивом 'actions',
обеспечивая механизм Chain-of-Thought (CoT).
"""

ACTION_SCHEMA =[
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
                                    "description": "Словарь с аргументами той функции, которую нужно вызвать (например, 'to_id': '12345'). Ключи должны точно совпадать с описанием в 'parameters'. Запрещено отправлять пустой словарь {}, если инструмент требует обязательные аргументы <REQUIRED>.",
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