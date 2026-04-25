import openai
import asyncio
from typing import Dict, Any
from pydantic import ValidationError

import base64
import re
import copy
from pathlib import Path

from src.utils.logger import system_logger
from src.utils.token_tracker import TokenTracker

from src.l0_state.agent.state import AgentState, AgentStatus

from src.l1_databases.sql.management.ticks import SQLTicks
from src.l1_databases.vector.manager import VectorManager

from src.l3_agent.llm.client import LLMClient
from src.l3_agent.prompt.builder import PromptBuilder
from src.l3_agent.context.builder import ContextBuilder

from src.l3_agent.skills.registry import execute_skill
from src.l3_agent.skills.schema import AgentResponse, ActionCall


class ReactLoop:
    """
    Ядро автономного агента.
    Реализует паттерн ReAct (Reasoning and Acting) в Stateless режиме.
    """

    def __init__(
        self,
        llm_client: LLMClient,
        prompt_builder: PromptBuilder,
        context_builder: ContextBuilder,
        agent_state: AgentState,
        sql_ticks: SQLTicks,
        vector_manager: VectorManager,
        token_tracker: TokenTracker,
        tools: list,
        cooldown_sec: int = 30,
    ):
        self.llm = llm_client
        self.prompt_builder = prompt_builder
        self.context_builder = context_builder
        self.agent_state = agent_state
        self.sql_ticks = sql_ticks
        self.vector_manager = vector_manager
        self.tracker = token_tracker
        self.tools = tools
        self.cooldown_sec = cooldown_sec

        # Хранилище Event Log: входящие события с интерфейсов, которые приходят между шагами раздумий агента
        self.current_events: list[Dict[str, Any]] = []

    async def run(
        self, event_name: str, payload: Dict[str, Any], missed_events: list[Dict[str, Any]]
    ) -> None:
        """Запускает ReAct цикл вызова к LLM (Оркестратор)."""

        self.current_events = missed_events.copy()

        try:
            self.agent_state.reset_step()
            system_logger.info(
                f"[ReAct] Цикл инициирован. Причина: {event_name} (LLM Model: {self.agent_state.llm_model})."
            )

            prompt = self.prompt_builder.build()

            # ======================================================================
            # ГЛАВНЫЙ ЦИКЛ
            # ======================================================================

            while self.agent_state.current_step <= self.agent_state.max_react_steps:
                self.agent_state.update_state(AgentStatus.THINKING)

                # =======================================================
                # Сборка контекста и промпта
                messages = await self._prepare_messages(prompt, event_name, payload)

                # =======================================================
                # Вызов LLM
                raw_answer = await self._call_llm_with_retries(messages)
                if raw_answer is None:
                    break  # Критическая ошибка или таймауты

                # =======================================================
                # Парсинг ответа
                parsed_response = await self._parse_response(raw_answer)
                if parsed_response is None:
                    self.agent_state.next_step()
                    continue  # Ошибка парсинга (агент исправится на следующем шаге)

                thoughts = parsed_response.thoughts.strip()
                actions = parsed_response.actions

                if thoughts:
                    system_logger.info(f"[Thoughts]:\n{thoughts}\n")

                # =======================================================
                # Проверка на завершение цикла
                if not actions:
                    await self._handle_completion(thoughts)
                    break

                # =======================================================
                # Выполнение действий
                await self._execute_actions(thoughts, actions)

                self.agent_state.next_step()

        finally:
            self.agent_state.update_state(AgentStatus.IDLE)

    # ==================================================================================
    # ПРИВАТНЫЕ МЕТОДЫ
    # ==================================================================================

    async def _prepare_messages(
        self, prompt: str, event_name: str, payload: Dict[str, Any]
    ) -> list[Dict[str, Any]]:
        """
        Собирает контекст,
        формирует сообщения для LLM
        и инжектит мультимодальность.
        """

        context = await self.context_builder.build(event_name, payload, self.current_events)

        # Очищаем события, чтобы на следующих шагах цикла LLM не видела их повторно
        if self.agent_state.current_step >= 4:
            self.current_events.clear()

        messages = [
            {"role": "system", "content": prompt},
            {"role": "user", "content": context},
        ]

        self.tracker.add_input_record(messages=messages)

        messages = copy.deepcopy(messages)
        messages = self._inject_images_to_payload(messages)
        self._dump_context_to_file(messages)

        system_logger.info(
            f"[ReAct] Шаг {self.agent_state.current_step}/{self.agent_state.max_react_steps}."
        )

        return messages

    async def _execute_actions(self, thoughts: str, actions: list[ActionCall]) -> None:
        """
        Выполняет запрошенные инструменты,
        обновляет стейт и сохраняет результат в БД.
        """

        self.agent_state.update_state(AgentStatus.ACTING)
        results_str = await execute_skill(actions=actions)

        # Обновляем стейт для RAG
        self.agent_state.last_thoughts = thoughts
        self.agent_state.last_actions_result = results_str

        args_to_rag = []
        for act in actions:
            for val in act.parameters.values():
                if isinstance(val, str) and len(val) > 3:
                    args_to_rag.append(val)
        self.agent_state.last_action_args = args_to_rag

        # Сохраняем логи (Tick) в БД
        await self.sql_ticks.save_tick(
            thoughts=thoughts,
            actions=[a.model_dump() for a in actions],
            results={"execution_report": results_str},
        )

    async def _handle_completion(self, thoughts: str) -> None:
        """
        Логика корректного завершения (отсутствие actions=).
        """

        system_logger.info("[ReAct] Передан пустой массив действий. Завершение.")
        await self.sql_ticks.save_tick(
            thoughts=thoughts, actions=[], results={"status": "completed"}
        )

    async def _call_llm_with_retries(self, messages: list) -> str | None:
        """
        Обрабатывает запросы к LLM,
        ротацию ключей и Rate Limits.
        """

        timeout_retries = 0
        max_timeout_retries = 3

        while True:
            try:
                session = self.llm.get_session()
                response = await session.chat.completions.create(
                    model=self.agent_state.llm_model,
                    messages=messages,
                    tools=self.tools,
                    tool_choice={
                        "type": "function",
                        "function": {"name": "execute_skill"},
                    },
                    temperature=self.agent_state.temperature,
                    max_tokens=4096,
                    timeout=240.0,
                )

                message_obj = response.choices[0].message
                
                if message_obj.tool_calls:
                    # Если модель вызвала функцию, берем СТРОГО её JSON-аргументы
                    raw_answer = str(message_obj.tool_calls[0].function.arguments)
                else:
                    # Иначе это просто текстовый ответ (или галлюцинация)
                    raw_answer = message_obj.content or ""

                self.tracker.add_output_record(raw_answer)
                return raw_answer

            except (openai.APITimeoutError, asyncio.TimeoutError):
                timeout_retries += 1
                if timeout_retries >= max_timeout_retries:
                    system_logger.error(
                        f"[LLM] API недоступно после {max_timeout_retries} таймаутов. Прерывание цикла."
                    )
                    self.agent_state.update_state(AgentStatus.ERROR)
                    return None
                system_logger.warning(
                    f"[LLM] Таймаут ответа API. Повтор ({timeout_retries}/{max_timeout_retries})."
                )
                continue

            except openai.RateLimitError as e:
                err_code = getattr(e.body, "get", lambda x: None)("code")
                if err_code == "insufficient_quota" or "billing" in str(e).lower():
                    system_logger.error(
                        f"[LLM] Квота исчерпана. Бан ключа {session.api_key[:8]} на 24ч"
                    )
                    self.llm.rotator.cooldown_key(session.api_key, 86400)
                else:
                    system_logger.info(
                        f"[LLM] Рейт-лимит. Пауза 60с для {session.api_key[:8]}"
                    )
                    self.llm.rotator.cooldown_key(session.api_key, 60)

                await asyncio.sleep(self.cooldown_sec)
                continue

            except openai.AuthenticationError:
                system_logger.warning("[LLM] Ключ невалиден (401). Удаляем из пула.")
                self.llm.rotator.ban_key(session.api_key)
                continue

            except Exception as e:
                system_logger.error(f"[LLM] Ошибка API: {e}")
                self.agent_state.update_state(AgentStatus.ERROR)
                return None

    async def _parse_response(self, raw_answer: str) -> AgentResponse | None:
        """
        Парсит JSON-ответ агента.
        В случае ошибки возвращает None
        и записывает ошибку в БД.
        """
        
        clean_answer = raw_answer.strip()

        # Срезаем Markdown-обертку, если LLM всё-таки решила прислать json как текст
        if clean_answer.startswith("```"):
            match = re.search(r"\{.*\}", clean_answer, re.DOTALL)
            if match:
                clean_answer = match.group(0)

        if not clean_answer.startswith("{"):
            # Имитация пустого действия
            return AgentResponse(thoughts=clean_answer, actions=[])

        try:
            parsed_response = AgentResponse.model_validate_json(clean_answer)
            return parsed_response
        except ValidationError as e:
            system_logger.warning("[ReAct] Ошибка структуры JSON.")
            err_msg = f"Format Error: {e}"

            await self.sql_ticks.save_tick(
                thoughts="[System: LLM provided invalid JSON format]",
                actions=[{"tool_name": "unknown", "parameters": {"raw": clean_answer}}],
                results={"execution_report": err_msg},
            )
            self.agent_state.last_actions_result = err_msg
            return None

    def add_realtime_event(self, event_data: Dict[str, Any]) -> None:
        """
        Добавляет входящее событие в контекст агента
        (вызывается извне).
        """

        self.current_events.append(event_data)

    def _dump_context_to_file(self, messages: list) -> None:
        """
        Создает дамп контекста в .md файл для отладки.
        """

        try:
            with open("logs/last_prompt.md", "w", encoding="utf-8") as f:
                for m in messages:
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

    def _encode_image(self, image_path: str) -> str:
        with open(image_path, "rb") as image_file:
            return base64.b64encode(image_file.read()).decode("utf-8")

    def _inject_images_to_payload(self, messages: list) -> list:
        """
        Инжектит Base64 изображения в User-промпт,
        если находит маркер.
        """

        last_result = self.agent_state.last_actions_result
        if not last_result:
            return messages

        image_paths = re.findall(r"\[SYSTEM_MARKER_IMAGE_ATTACHED:\s*(.+?)\]", last_result)

        if not image_paths:
            return messages

        user_msg = messages[1]

        if isinstance(user_msg, dict) and user_msg.get("role") == "user":
            original_text = user_msg["content"]
            new_content = [{"type": "text", "text": original_text}]

            for img_path in set(image_paths):
                try:
                    path_obj = Path(img_path)
                    if path_obj.exists():
                        base64_data = self._encode_image(str(path_obj))
                        ext = path_obj.suffix.lower()
                        mime = "image/jpeg" if ext in [".jpg", ".jpeg"] else f"image/{ext[1:]}"

                        new_content.append(
                            {
                                "type": "image_url",
                                "image_url": {"url": f"data:{mime};base64,{base64_data}"},
                            }
                        )
                        system_logger.info(
                            f"[ReAct] Изображение {path_obj.name} успешно инжектировано."
                        )
                except Exception as e:
                    system_logger.error(f"[ReAct] Ошибка инжектирования Base64: {e}")

            user_msg["content"] = new_content

        return messages
