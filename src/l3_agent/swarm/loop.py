import json
import re
import asyncio
import openai
from pathlib import Path
from typing import Dict, List, Tuple, Optional
from pydantic import ValidationError

from src.utils.logger import system_logger
from src.utils.token_tracker import TokenTracker
from src.l3_agent.llm.client import LLMClient
from src.l3_agent.skills.schema import AgentResponse, ActionCall, ACTION_SCHEMA
from src.l3_agent.skills.registry import call_skill
from src.l3_agent.swarm.prompt.builder import SwarmPromptBuilder
from src.l3_agent.swarm.context.builder import SwarmContextBuilder
from src.l3_agent.swarm.roles import SubagentRole


class SubagentLoop:
    """
    Облегченный Stateless ReAct-цикл для субагентов.
    """

    def __init__(
        self,
        subagent_id: str,
        role: SubagentRole,
        task_description: str,
        llm_client: LLMClient,
        model_name: str,
        prompt_builder: SwarmPromptBuilder,
        context_builder: SwarmContextBuilder,
        allowed_skills: List[str],
        token_tracker: TokenTracker,
        max_steps: int = 15,
    ):
        self.subagent_id = subagent_id
        self.role = role
        self.task_description = task_description
        self.llm = llm_client
        self.model_name = model_name
        self.prompt_builder = prompt_builder
        self.context_builder = context_builder
        self.allowed_skills = allowed_skills + ["SubagentReport.submit_final_report"]
        self.tracker = token_tracker
        self.max_steps = max_steps

        self.history: List[Dict[str, str]] = []
        self.is_done = False

        # Флаг для жесткого контроля отправки отчета
        self.report_submitted = False

    async def run(self) -> None:
        """Главный оркестратор ReAct цикла субагента."""
        system_logger.info(f"[Swarm] Запуск субагента {self.role.id}_{self.subagent_id}.")
        prompt = self.prompt_builder.build(self.role)

        # Главный ReAct цикл
        step = 1
        while step <= self.max_steps and not self.is_done:
            system_logger.info(f"[Subagent ReAct] Шаг {step}/{self.max_steps}.")
            messages = self._prepare_messages(prompt)

            # Сохраняем дамп для отладки
            self._dump_context_to_file(messages, step)

            # Вызов LLM
            raw_answer = await self._call_llm_with_retries(messages)
            if raw_answer is None:
                return  # Завершаем работу при критических сбоях сети

            # Парсинг ответа
            parsed_response, error_msg = self._parse_response(raw_answer)

            if error_msg:
                fallback_thoughts = (
                    parsed_response if isinstance(parsed_response, str) else "[JSON Error]"
                )
                self.history.append(
                    {
                        "thoughts": fallback_thoughts,
                        "actions": "None",
                        "results": error_msg,
                    }
                )
                step += 1
                continue

            thoughts = parsed_response.thoughts
            actions = parsed_response.actions

            # Если нет действий
            if not actions:
                if not self.report_submitted:
                    # ЖЕСТКИЙ ГАРД: не даем субагенту умереть без отчета
                    system_logger.warning(
                        f"[Swarm] Субагент {self.subagent_id} попытался завершить работу без отчета. Принуждаем к действию."
                    )
                    self.history.append(
                        {
                            "thoughts": thoughts,
                            "actions": "[]",
                            "results": "[System Error]: Вы попытались завершить работу (вернули пустой массив действий), но не отправили финальный отчет. Это запрещено. Используйте инструмент 'SubagentReport.submit_final_report' для сдачи результатов.",
                        }
                    )
                    step += 1
                    continue
                else:
                    system_logger.info(
                        f"[Swarm] Субагент {self.role.id}_{self.subagent_id} передал пустой массив действий. Завершение."
                    )
                    self.is_done = True
                    break

            # Исполнение скиллов
            await self._execute_and_log_actions(thoughts, actions)
            step += 1

        # ===================================================================
        # Если агент не смог выполнить задачу за макс. шагов

        if not self.is_done:
            system_logger.warning(
                f"[Swarm] Субагент {self.subagent_id} достиг лимита шагов ({self.max_steps}) и был убит."
            )

    # ==================================================================================
    # ПРИВАТНЫЕ МЕТОДЫ
    # ==================================================================================

    def _prepare_messages(self, prompt: str) -> List[Dict[str, str]]:
        """
        Собирает контекст и обновляет счетчик входящих токенов.
        """

        context = self.context_builder.build(
            self.subagent_id, self.task_description, self.history
        )
        messages = [
            {"role": "system", "content": prompt},
            {"role": "user", "content": context},
        ]
        self.tracker.add_input_record(messages, log_prefix="[Subagent LLM]")
        return messages

    def _dump_context_to_file(self, messages: List[Dict[str, str]], current_step: int) -> None:
        """Создает дамп контекста в .md файл для отладки субагентов."""
        try:
            log_dir = Path("logs/subagents")
            log_dir.mkdir(parents=True, exist_ok=True)

            with open(log_dir / "last_prompt.md", "w", encoding="utf-8") as f:
                f.write("# SUBAGENT DUMP\n")
                f.write(f"* **Role**: {self.role.name.upper()}\n")
                f.write(f"* **Subagent ID**: {self.subagent_id}\n")
                f.write(f"* **Step**: {current_step} / {self.max_steps}\n\n---\n\n")

                for m in messages:
                    role = m.get("role", "unknown")
                    content = m.get("content", "")
                    f.write(f"### Role: {role}\n{content}\n\n---\n")
        except Exception as e:
            system_logger.error(f"[Swarm] Не удалось сохранить дамп промпта: {e}")

    async def _call_llm_with_retries(self, messages: List[Dict[str, str]]) -> Optional[str]:
        """
        Обрабатывает запросы к LLM, ротацию ключей и Rate Limits.
        """

        for attempt in range(3):
            try:
                session = self.llm.get_session()
                response = await session.chat.completions.create(
                    model=self.model_name,
                    messages=messages,
                    tools=ACTION_SCHEMA,
                    temperature=0.7,
                )
                msg_obj = response.choices[0].message
                raw_answer = (
                    str(msg_obj.tool_calls[0].function.arguments)
                    if msg_obj.tool_calls
                    else msg_obj.content or ""
                )
                self.tracker.add_output_record(raw_answer, log_prefix="[Subagent LLM]")
                return raw_answer

            except openai.RateLimitError:
                system_logger.warning(
                    f"[Swarm] Rate Limit у субагента {self.subagent_id}. Пауза 30с."
                )
                self.llm.rotator.cooldown_key(session.api_key, 60)
                await asyncio.sleep(30)

            except Exception as e:
                if attempt == 2:
                    system_logger.error(
                        f"[Swarm] LLM ошибка у субагента {self.subagent_id}: {e}"
                    )
                    return None
                await asyncio.sleep(5)

        return None

    def _parse_response(
        self, raw_answer: str
    ) -> Tuple[Optional[AgentResponse], Optional[str]]:
        """
        Парсит ответ от LLM.
        """

        clean_answer = raw_answer.strip()

        # Срезаем Markdown-обертку, если LLM прислала json текстом
        if clean_answer.startswith("```"):
            match = re.search(r"\{.*\}", clean_answer, re.DOTALL)
            if match:
                clean_answer = match.group(0)

        if not clean_answer.startswith("{"):
            return clean_answer, "System Error: Invalid JSON format. Use tool_calls."

        try:
            parsed = AgentResponse.model_validate_json(clean_answer)
            return parsed, None

        except ValidationError as e:
            return None, f"Format Error: {e}"

    async def _execute_and_log_actions(self, thoughts: str, actions: List[ActionCall]) -> None:
        """
        Выполняет запрошенные инструменты и сохраняет результаты в историю субагента.
        """

        results = []
        actions_log = []

        for act in actions:
            actions_log.append(
                f"{act.tool_name}({json.dumps(act.parameters, ensure_ascii=False)})"
            )

            if act.tool_name not in self.allowed_skills:
                results.append(
                    f"* Action [{act.tool_name}]: Отказано в доступе. Этот инструмент не разрешен для вашей роли."
                )
                continue

            try:
                res = await call_skill(act.tool_name, act.parameters)
                results.append(f"* Action [{act.tool_name}]: {res.message}")

                # Фиксируем успешную отправку отчета
                if act.tool_name == "SubagentReport.submit_final_report" and res.is_success:
                    self.report_submitted = True

            except Exception as e:
                results.append(f"* Action [{act.tool_name}]: Внутренняя ошибка навыка - {e}")

        self.history.append(
            {
                "thoughts": thoughts,
                "actions": "\n".join(actions_log),
                "results": "\n".join(results),
            }
        )
