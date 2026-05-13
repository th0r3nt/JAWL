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
    tool_name: str
    parameters: Dict[str, Any] = Field(default_factory=dict)


class AgentResponse(BaseModel):
    """
    Типизированная схема полного ответа LLM.
    Содержит структурированный внутренний монолог и массив действий.
    """

    observation: str = ""
    reasoning: str = ""
    reflection: str = ""
    actions: List[ActionCall] = Field(default_factory=list)

    @property
    def thoughts(self) -> str:
        """
        Склеивает структурированный CoT в единую строку для базы данных и логов.
        """

        parts = []
        if self.observation.strip():
            parts.append(f"[Observation]: {self.observation.strip()}")
        if self.reasoning.strip():
            parts.append(f"[Reasoning]: {self.reasoning.strip()}")
        if self.reflection.strip():
            parts.append(f"[Reflection]: {self.reflection.strip()}")
        return "\n".join(parts)


# Константа, которая отправляется в параметр 'tools' API языковой модели

ACTION_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "execute_skill",
            "description": "Main interface for interacting with the external environment. Mandatory to call for any actions.",
            "parameters": {
                "type": "object",
                "properties": {
                    "observation": {
                        "type": "string",
                        "description": "Observation of results.",
                    },
                    "reasoning": {
                        "type": "string",
                        "description": "Description of the logic behind the next actions.",
                    },
                    "reflection": {
                        "type": "string",
                        "description": "Reflection or internal thoughts in a completely free format. Hypotheses, intermediate conclusions, or memos for the future.",
                    },
                    "actions": {
                        "type": "array",
                        "description": "List of actions to execute.",
                        "items": {
                            "type": "object",
                            "properties": {
                                "tool_name": {
                                    "type": "string",
                                    "description": "Exact name of the function.",
                                },
                                "parameters": {
                                    "type": "object",
                                    "description": "Dictionary containing the arguments.",
                                    "additionalProperties": True,
                                },
                            },
                            "required": ["tool_name", "parameters"],
                            "additionalProperties": False,
                        },
                    },
                },
                "required": ["observation", "reasoning", "reflection", "actions"],
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
    clean_answer = raw_answer.strip()
    json_str = ""

    # Попытка 1: Строгий парсинг (Ищем Markdown-блок)
    json_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", clean_answer, re.DOTALL)
    if json_match:
        json_str = json_match.group(1)
    else:
        # Попытка 2: Ищем внешние границы JSON объекта
        start_idx = clean_answer.find('{"observation"')
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

                parsed_response = AgentResponse(
                    observation="[Heuristic parse]",
                    reasoning="",
                    reflection=clean_answer,  # Сохраняем весь сломанный ответ как рефлексию
                    actions=actions_list,
                )
                error_msg = None
        except Exception as e:
            error_msg = f"Heuristic parse failed: {e}"

    # Если вообще не найдено следов JSON
    if (
        parsed_response is None
        and "System Error" in (error_msg or "")
        and "{" not in raw_answer
    ):
        return (
            AgentResponse(
                observation="[Plain Text]",
                reasoning="",
                reflection=raw_answer.strip(),
                actions=[],
            ),
            None,
        )

    # =========================================================================
    # ANTI-INCEPTION (Защита от JSON внутри CoT)
    # =========================================================================

    if parsed_response is not None:
        thoughts_str = parsed_response.thoughts.strip()

        # Если внутри строки лежат ключи действий и наблюдений (LLM обернула JSON в текст)
        if (
            _depth < 3
            and ('"actions"' in thoughts_str or "'actions'" in thoughts_str)
            and ('"observation"' in thoughts_str or "'observation'" in thoughts_str)
            and (thoughts_str.startswith("{") or "```json" in thoughts_str)
        ):
            inner_parsed, _ = parse_llm_json(thoughts_str, _depth=_depth + 1)

            if inner_parsed is not None and (
                inner_parsed.actions or not parsed_response.actions
            ):
                parsed_response = inner_parsed

        return parsed_response, None

    return None, f"System Error: Invalid JSON format. Details: {error_msg}"
