"""
Universal Pydantic schema for agent tool calls.

Defines the JSON Schema expected by the OpenAI API (or compatible).
Includes an heuristic parser (Dirty JSON Repair) to extract data
if the LLM violates formatting or escaping.
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
    Typed schema of the complete LLM response.
    Contains structured internal monologue (CoT) and an array of actions.
    """

    observation: str = ""
    reasoning: str = ""
    reflection: str = ""
    actions: List[ActionCall] = Field(default_factory=list)

    @property
    def thoughts(self) -> str:
        """
        Concatenates the structured CoT into a single string for logs and databases.
        """

        parts = []
        if self.observation.strip():
            parts.append(f"\n[Observation]: {self.observation.strip()}")
        if self.reasoning.strip():
            parts.append(f"\n[Reasoning]: {self.reasoning.strip()}")
        if self.reflection.strip():
            parts.append(f"\n[Reflection]: {self.reflection.strip()}")
        return "\n".join(parts)


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
    Smart search for the 'actions' array taking into account bracket nesting and string literals.
    Capable of extracting the array even if the model puts it inside the 'thoughts' string.
    """
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
    
    # --- БРОНЯ ОТ ДВОЙНЫХ СКОБОК (LLM Format Glitch) ---
    # Вырезаем анонимные внешние скобки, если нейронка выдала {{ ... }}
    clean_answer = re.sub(r"^\{\s*\{", "{", clean_answer)
    clean_answer = re.sub(r"\}\s*\}$", "}", clean_answer)
    # ---------------------------------------------------
    
    json_str = ""

    # Attempt 1: Strict parsing (looking for Markdown block)
    json_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", clean_answer, re.DOTALL)
    if json_match:
        json_str = json_match.group(1)
    else:
        # Attempt 2: Looking for outer boundaries of JSON object
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
            
            # --- ФИКС МАТРЕШКИ ---
            # Если модель завернула всё в один корневой ключ (например, {"response": {...}})
            if isinstance(data, dict) and len(data) == 1:
                inner_val = list(data.values())[0]
                if isinstance(inner_val, dict) and "actions" in inner_val:
                    data = inner_val
            # ---------------------
            
            # --- ФИКС СТРОКОВОГО МАССИВА (Double-encoding) ---
            if isinstance(data, dict):
                actions_val = data.get("actions")
                if isinstance(actions_val, str):
                    try:
                        # Вскрываем строку в нативный питоновский list
                        data["actions"] = json.loads(actions_val, strict=False)
                    except Exception:
                        pass # Если внутри невалидный мусор - оставляем строкой, Pydantic упадет и отдаст в Attempt 3
            # -------------------------------------------------
            
            parsed_response = AgentResponse(**data)
        except Exception as e:
            error_msg = str(e)

    # Attempt 3: Heuristic Fallback (JSON repair)
    if parsed_response is None or (
        not parsed_response.actions and '"tool_name"' in raw_answer
    ):
        try:
            actions_raw = _extract_json_array(clean_answer)
            if actions_raw:
                # УБРАНА ТОКСИЧНАЯ ЗАМЕНА КАВЫЧЕК
                # Отдаем в json.loads сырую строку, сохраняя оригинальное экранирование от LLM
                actions_list = json.loads(actions_raw, strict=False)

                parsed_response = AgentResponse(
                    observation="[Heuristic parse]",
                    reasoning="",
                    reflection=clean_answer,
                    actions=actions_list,
                )
                error_msg = None
        except Exception as e:
            error_msg = f"Heuristic parse failed: {e}"

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
    # ANTI-INCEPTION (JSON inside CoT)
    # =========================================================================

    if parsed_response is not None:
        thoughts_str = parsed_response.thoughts.strip()

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
