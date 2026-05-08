"""
Универсальная Pydantic схема для вызова инструментов агентом.

Определяет JSON Schema, которую ожидает OpenAI API (или совместимые).
Включает эвристический парсер (Dirty JSON Repair) для извлечения данных,
если LLM нарушает форматирование или экранирование.
"""

import re
import json
from typing import Any, Dict, List, Tuple, Optional
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
                        "description": "Ваш внутренний монолог. Строго текстовый формат (без вложенного JSON кода).",
                    },
                    "actions": {
                        "type": "array",
                        "description": "Список действий (инструментов) для выполнения.",
                        "items": {
                            "type": "object",
                            "properties": {
                                "tool_name": {
                                    "type": "string",
                                    "description": "Точное имя функции.",
                                },
                                "parameters": {
                                    "type": "object",
                                    "description": "Словарь с аргументами. Ключи должны точно совпадать с описанием функции.",
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


def _extract_json_array(text: str) -> Optional[str]:
    """
    Умный поиск массива `actions` с учетом вложенности скобок и строковых литералов.
    Способен извлечь массив, даже если модель засунула его внутрь строки 'thoughts'.
    """
    # Ищем начало массива, внутри которого есть tool_name
    match = re.search(r'\[\s*\{\s*["\']tool_name["\']', text)
    if not match:
        return None

    start = match.start()
    depth = 0
    in_string = False
    escape = False

    for i in range(start, len(text)):
        char = text[i]
        if escape:
            escape = False
            continue
        if char == "\\":
            escape = True
            continue

        if char == '"':
            in_string = not in_string
            continue

        if not in_string:
            if char == "[":
                depth += 1
            elif char == "]":
                depth -= 1
                if depth == 0:
                    return text[start : i + 1]
    return None


def parse_llm_json(
    raw_answer: str, _depth: int = 0
) -> Tuple[Optional[AgentResponse], Optional[str]]:
    """
    Универсальный парсер ответов LLM с многоуровневым Fallback механизмом.
    Ищет валидный JSON, игнорируя markdown и словесный мусор.
    Включает защиту Anti-Inception от двойной вложенности действий.
    """
    clean_answer = raw_answer.strip()
    json_str = ""

    # Попытка 1: Строгий парсинг (Ищем Markdown-блок)
    json_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", clean_answer, re.DOTALL)
    if json_match:
        json_str = json_match.group(1)
    else:
        # Попытка 2: Ищем внешние границы JSON объекта
        start_idx = clean_answer.find('{"thoughts"')
        if start_idx == -1:
            start_idx = clean_answer.find("{")

        end_idx = clean_answer.rfind("}")
        if start_idx != -1 and end_idx > start_idx:
            json_str = clean_answer[start_idx : end_idx + 1]

    parsed_response = None
    error_msg = None

    if json_str:
        try:
            data = json.loads(json_str, strict=False)
            parsed_response = AgentResponse(**data)
        except Exception as e:
            error_msg = str(e)

    # Попытка 3: Эвристический Fallback
    if parsed_response is None or (
        not parsed_response.actions and '"tool_name"' in raw_answer
    ):
        try:
            actions_raw = _extract_json_array(clean_answer)
            if actions_raw:
                clean_actions = (
                    actions_raw.replace('\\"', '"').replace("\\'", "'").replace("\\n", "\n")
                )
                actions_list = json.loads(clean_actions, strict=False)

                thoughts_text = "Извлечено эвристическим парсером (Форматирование ответа LLM было повреждено)."
                thoughts_match = re.search(
                    r'["\']thoughts["\']\s*:\s*["\'](.*?)["\']\s*,', clean_answer, re.DOTALL
                )
                if thoughts_match:
                    thoughts_text = thoughts_match.group(1).strip()

                parsed_response = AgentResponse(thoughts=thoughts_text, actions=actions_list)
                error_msg = None
        except Exception as e:
            error_msg = f"Heuristic parse failed: {e}"

    # Если вообще не найдено следов JSON
    if (
        parsed_response is None
        and "System Error" in (error_msg or "")
        and "{" not in raw_answer
    ):
        return AgentResponse(thoughts=raw_answer.strip(), actions=[]), None

    # =========================================================================
    # ANTI-INCEPTION (Защита от JSON внутри Thoughts)
    # =========================================================================
    
    if parsed_response is not None:
        thoughts_str = parsed_response.thoughts.strip()

        # Если внутри "thoughts" лежит строка с ключами "thoughts" и "actions"
        if (
            _depth < 3
            and ('"actions"' in thoughts_str or "'actions'" in thoughts_str)
            and ('"thoughts"' in thoughts_str or "'thoughts'" in thoughts_str)
            and (thoughts_str.startswith("{") or "```json" in thoughts_str)
        ):

            # Пытаемся распарсить вложенную матрешку
            inner_parsed, _ = parse_llm_json(thoughts_str, _depth=_depth + 1)

            # Если внутри оказался валидный объект, и либо внешний массив действий пуст,
            # либо у внутреннего есть реальные действия - доверяем внутреннему (разворачиваем матрешку).
            if inner_parsed is not None and (
                inner_parsed.actions or not parsed_response.actions
            ):
                parsed_response = inner_parsed

        return parsed_response, None

    return None, f"System Error: Invalid JSON format. Details: {error_msg}"
