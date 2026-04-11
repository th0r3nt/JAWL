import json
import openai
from typing import Dict, Any

from src.utils.logger import system_logger
from src.utils.token_tracker import TokenTracker

from src.l0_state.agent.state import AgentState, AgentStatus
from src.l1_databases.sql.management.ticks import SQLTicks

from src.l3_agent.llm.client import LLMClient
from src.l3_agent.prompt.builder import PromptBuilder
from src.l3_agent.context.builder import ContextBuilder

# Импортируем готовый роутер скиллов
from src.l3_agent.skills.registry import get_skills_library, execute_skill


class ReactLoop:
    """
    Ядро автономного агента.
    Реализует паттерн ReAct (Reasoning and Acting).
    """

    def __init__(
        self,
        llm_client: LLMClient,
        prompt_builder: PromptBuilder,
        context_builder: ContextBuilder,
        agent_state: AgentState,
        sql_ticks: SQLTicks,
        token_tracker: TokenTracker,
        tools: list,  # ACTION SCHEMA
    ):
        self.llm = llm_client
        self.prompt_builder = prompt_builder
        self.context_builder = context_builder
        self.agent_state = agent_state
        self.sql_ticks = sql_ticks
        self.tracker = token_tracker
        self.tools = tools

    def _dump_context_to_file(self, messages: list):
        """
        Сохраняет финальный промпт в Markdown-файл для отладки.
        Безопасно парсит как обычные dict, так и объекты OpenAI.
        """
        try:
            with open("logs/last_prompt.md", "w", encoding="utf-8") as f:
                for m in messages:
                    # Поддержка как словарей, так и pydantic-моделей
                    role = getattr(
                        m,
                        "role",
                        m.get("role", "unknown") if isinstance(m, dict) else "unknown",
                    )
                    content = getattr(
                        m, "content", m.get("content", "") if isinstance(m, dict) else ""
                    )
                    f.write(f"### Role: {role}\n{content}\n\n---\n")

        except Exception as e:
            system_logger.error(f"[System] Не удалось сохранить промпт: {e}")

    async def run(self, event_name: str, payload: Dict[str, Any]):

        self.agent_state.reset_step()
        system_logger.info(
            f"[Thoughts] ReAct-цикл инициирован (LLM Model: {self.agent_state.llm_model})."
        )

        # 1. Сборка промпта и контекста
        skills_docs = get_skills_library()
        prompt = self.prompt_builder.build(skills_docs)
        context = await self.context_builder.build(event_name, payload)

        self.tracker.add_input_record(prompt=prompt, context=context)

        messages = [
            {"role": "system", "content": prompt},
            {"role": "user", "content": context},
        ]

        step = 1
        while step <= self.agent_state.max_react_steps:
            self.agent_state.current_step = step
            self.agent_state.update_state(AgentStatus.THINKING)

            system_logger.info(f"[ReAct] Шаг {step}/{self.agent_state.max_react_steps}.")

            if step == 1:
                self._dump_context_to_file(messages)

            try:
                session = await self.llm.get_session()
                response = await session.chat.completions.create(
                    model=self.agent_state.llm_model,
                    messages=messages,
                    tools=self.tools,
                    tool_choice={"type": "function", "function": {"name": "execute_skill"}},
                    temperature=self.agent_state.temperature,
                )

                raw_answer = response.choices[0].message.content or ""
                self.tracker.add_output_record(raw_answer)

            except openai.RateLimitError:
                system_logger.warning("[LLM] Rate Limit (429). Ключ отправлен в кулдаун.")
                self.llm.rotator.cooldown_key(session.api_key, 60)
                continue  # Повторяем тот же шаг с новым ключом

            except openai.AuthenticationError:
                system_logger.warning("[LLM] Ключ невалиден (401). Удаляем из пула.")
                self.llm.rotator.ban_key(session.api_key)
                continue

            except Exception as e:
                system_logger.error(f"[LLM] Ошибка API: {e}")
                self.agent_state.update_state(AgentStatus.ERROR)
                break

            response_message = response.choices[0].message
            messages.append(response_message)

            # Если LLM проигнорировала tools
            if not response_message.tool_calls:
                system_logger.info(
                    "[ReAct] Остановка цикла: модель не вызвала ни одного инструмента."
                )
                break

            tool_call = response_message.tool_calls[0]
            args_str = tool_call.function.arguments

            # Парсинг ответа
            try:
                args = json.loads(args_str)
            except json.JSONDecodeError:
                system_logger.error(
                    "[ReAct] LLM сгенерировала невалидный JSON. Запрашиваем исправление."
                )
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "name": tool_call.function.name,
                        "content": "JSONDecodeError: JSON невалиден.",
                    }
                )
                step += 1
                continue

            thoughts = args.get("thoughts", "")
            actions = args.get("actions", [])

            # Выход из цикла по запросу LLM
            if not actions:
                system_logger.info(
                    "[ReAct] Агент передал пустой массив действий. ReAct-цикл завершен."
                )
                # Сохраняем финальную мысль в БД, даже если действий не было
                await self.sql_ticks.save_tick(
                    thoughts=thoughts, actions=[], results={"status": "completed"}
                )
                break

            # Исполнение скиллов
            self.agent_state.update_state(AgentStatus.ACTING)

            results_str = await execute_skill(thoughts=thoughts, actions=actions)

            # Сохранение тика в SQL для следующего контекста
            await self.sql_ticks.save_tick(
                thoughts=thoughts, actions=actions, results={"execution_report": results_str}
            )

            # Инъекция результатов обратно в диалог
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "name": tool_call.function.name,
                    "content": results_str,
                }
            )

            step += 1

        self.agent_state.update_state(AgentStatus.IDLE)
