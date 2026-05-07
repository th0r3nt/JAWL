"""
Ядро рассуждений агента (Reasoning and Acting).

Модуль реализует Stateless-цикл: собирает контекст, отправляет промпт в LLM,
парсит JSON-вызовы (Chain-of-Thought + Tool Calls), выполняет навыки и
сохраняет результаты (Ticks) в базу данных.
"""

import openai
import asyncio
from typing import Dict, Any, List, Optional
import time

import base64
import re
import copy
from pathlib import Path

from src.utils.logger import main_logger, agent_logger
from src.utils.settings import TreeOfThoughtsConfig
from src.utils.token_tracker import TokenTracker
from src.utils._tools import dump_prompt_to_file

from src.utils.event.bus import EventBus
from src.utils.event.registry import Events

from src.l0_state.agent.state import AgentState, AgentStatus

from src.l1_databases.sql.management.ticks import SQLTicks
from src.l1_databases.vector.manager import VectorManager

from src.l3_agent.llm.client import LLMClient
from src.l3_agent.prompt.builder import PromptBuilder
from src.l3_agent.context.builder import ContextBuilder

from src.l3_agent.tot.generator import ToTGenerator

from src.l3_agent.skills.registry import execute_skill
from src.l3_agent.skills.schema import AgentResponse, ActionCall, parse_llm_json


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
        event_bus: EventBus,
        cooldown_sec: int = 30,
        tot_config: Optional[TreeOfThoughtsConfig] = None,
        tot_generator: Optional[ToTGenerator] = None,
    ) -> None:
        """
        Инициализирует цикл ReAct.

        Args:
            llm_client: Клиент для взаимодействия с API языковой модели.
            prompt_builder: Билдер статической части системного промпта.
            context_builder: Билдер динамического контекста (состояния интерфейсов, память).
            agent_state: Объект состояния самого агента (L0).
            sql_ticks: Контроллер базы данных для записи логов действий (тиков).
            vector_manager: Менеджер векторной памяти.
            token_tracker: Утилита для подсчета потребленных токенов LLM.
            tools: Список доступных инструментов в формате JSON Schema.
            cooldown_sec: Время ожидания в секундах при получении Rate Limit (429).
        """

        self.llm = llm_client

        self.prompt_builder = prompt_builder
        self.context_builder = context_builder

        self.agent_state = agent_state

        self.sql_ticks = sql_ticks
        self.vector_manager = vector_manager

        self.tracker = token_tracker

        self.tools = tools
        self.cooldown_sec = cooldown_sec

        self.event_bus = event_bus

        self.tot_config = tot_config
        self.tot_generator = tot_generator

        # Хранилище Event Log: входящие события с интерфейсов, которые приходят между шагами раздумий агента
        self.current_events: List[Dict[str, Any]] = []

    async def run(
        self, event_name: str, payload: Dict[str, Any], missed_events: List[Dict[str, Any]]
    ) -> None:
        """
        Запускает ReAct цикл вызова к LLM (Оркестратор).

        Args:
            event_name: Главная причина пробуждения агента.
            payload: Данные главного триггера.
            missed_events: Лог событий, которые произошли, пока агент спал.
        """

        self.current_events = missed_events.copy()

        try:
            self.agent_state.reset_step()

            log = f"[ReAct] Цикл инициирован. Причина: {event_name} (LLM Model: {self.agent_state.llm_model})."
            main_logger.info(log)
            agent_logger.info(log)

            prompt = self.prompt_builder.build()

            # ======================================================================
            # ГЛАВНЫЙ ЦИКЛ
            # ======================================================================

            while self.agent_state.current_step <= self.agent_state.max_react_steps:
                self.agent_state.update_state(AgentStatus.THINKING)

                # =======================================================
                # Генерация дерева мыслей
                if (
                    self.tot_config
                    and self.tot_config.enabled
                    and self.tot_config.mode in ("auto", "hybrid")
                ):
                    # Генерируем на 1-м шаге, а затем каждые N шагов
                    if (self.agent_state.current_step == 1) or (
                        (self.agent_state.current_step - 1)
                        % self.tot_config.auto_interval_steps
                        == 0
                    ):

                        tree_md = await self.tot_generator.generate(
                            event_name,
                            payload,
                            missed_events,
                            task_description="Автоматическая генерация древа мыслей для оценки текущего вектора.",
                        )
                        if tree_md:
                            self.agent_state.current_thoughts_tree = tree_md

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
                    log = f"[Thoughts]:\n{thoughts}\n"
                    main_logger.info(log)
                    agent_logger.info(log)

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
    ) -> List[Dict[str, Any]]:
        """
        Собирает контекст, формирует сообщения для LLM и инжектит мультимодальность.

        Args:
            prompt: Статический системный промпт.
            event_name: Имя главного события-триггера.
            payload: Данные события-триггера.

        Returns:
            Список словарей в формате OpenAI Messages API.
        """

        context = await self.context_builder.build(event_name, payload, self.current_events)

        # Очищаем события, чтобы на следующих шагах цикла LLM не видела их повторно
        if self.agent_state.current_step >= 4:
            self.current_events.clear()

        messages = [
            {"role": "system", "content": prompt},
            {"role": "user", "content": context},
        ]

        input_tokens = self.tracker.add_input_record(messages=messages, logger=agent_logger)
        self.agent_state.last_input_tokens = input_tokens

        messages = copy.deepcopy(messages)

        # Асинхронно инжектим картинки
        messages = await self._inject_images_to_payload(messages)

        # Асинхронно дампим контекст, чтобы не блокировать Event Loop при записи файла
        await asyncio.to_thread(self._dump_context_to_file, messages)

        log = f"[ReAct] Шаг {self.agent_state.current_step}/{self.agent_state.max_react_steps}."
        main_logger.info(log)
        agent_logger.info (log)

        return messages

    async def _execute_actions(self, thoughts: str, actions: List[ActionCall]) -> None:
        """
        Выполняет запрошенные инструменты, обновляет стейт и сохраняет результат в БД.

        Args:
            thoughts: Внутренний монолог агента (CoT).
            actions: Список запрошенных инструментов для вызова.
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
            results={
                "execution_report": results_str,
                "step": self.agent_state.current_step,
                "max_steps": self.agent_state.max_react_steps,
            },
        )
        await self.event_bus.publish(Events.REACT_TICK_SAVED)

    async def _handle_completion(self, thoughts: str) -> None:
        """
        Логика корректного завершения (отсутствие actions).

        Args:
            thoughts: Последняя мысль агента перед уходом в сон.
        """

        log = "[ReAct] Передан пустой массив действий. Завершение."
        main_logger.info(log)
        agent_logger.info(log)

        await self.sql_ticks.save_tick(
            thoughts=thoughts,
            actions=[],
            results={
                "status": "completed",
                "step": self.agent_state.current_step,
                "max_steps": self.agent_state.max_react_steps,
            },
        )
        await self.event_bus.publish(Events.REACT_TICK_SAVED)

    async def _call_llm_with_retries(self, messages: List[Dict[str, Any]]) -> Optional[str]:
        """
        Обрабатывает запросы к LLM, ротацию ключей и Rate Limits (429).

        Args:
            messages: Сформированный массив сообщений для LLM.

        Returns:
            Сырой текст ответа от модели (аргументы функции или текст) либо None при ошибке.
        """

        timeout_retries = 0
        max_timeout_retries = 2

        while True:
            try:
                session = self.llm.get_session()
                response = await session.chat.completions.create(
                    model=self.agent_state.llm_model,
                    messages=messages,
                    tools=self.tools,
                    temperature=self.agent_state.temperature,
                    timeout=120.0,
                )

                message_obj = response.choices[0].message

                if message_obj.tool_calls:
                    raw_answer = str(message_obj.tool_calls[0].function.arguments)
                else:
                    raw_answer = message_obj.content or ""

                self.tracker.add_output_record(raw_answer, logger=agent_logger)
                return raw_answer

            except RuntimeError as e:
                # Отлавливаем ошибку ротатора (все ключи в бане)
                if "исчерпали лимиты" in str(e):
                    import re

                    match = re.search(r"подождать (\d+) сек", str(e))
                    wait_sec = int(match.group(1)) if match else 10

                    log = f"[LLM] Все ключи в кулдауне. Ждем {wait_sec} сек."
                    main_logger.warning(log)
                    agent_logger.warning(log)

                    await asyncio.sleep(wait_sec + 1)  # +1 сек для гарантии
                    continue
                else:
                    log = f"[LLM] Внутренняя ошибка API: {e}"
                    main_logger.error(log)
                    agent_logger.error(log)

                    self.agent_state.update_state(AgentStatus.ERROR)
                    return None

            except (openai.APITimeoutError, asyncio.TimeoutError):
                timeout_retries += 1
                if timeout_retries >= max_timeout_retries:
                    log = f"[LLM] API недоступно после {max_timeout_retries} таймаутов. Прерывание цикла."
                    main_logger.error(log)
                    agent_logger.error(log)

                    self.agent_state.update_state(AgentStatus.ERROR)
                    return None
                
                log = f"[LLM] Таймаут ответа API. Повтор ({timeout_retries}/{max_timeout_retries})."
                main_logger.warning(log)
                agent_logger.warning(log)
                continue

            except openai.RateLimitError as e:
                err_code = getattr(e.body, "get", lambda x: None)("code")
                if err_code == "insufficient_quota" or "billing" in str(e).lower():

                    log = f"[LLM] Квота исчерпана. Бан ключа {session.api_key[:8]} на 24ч"
                    main_logger.error(log)
                    agent_logger.error(log)

                    self.llm.rotator.cooldown_key(session.api_key, 86400)
                    await asyncio.sleep(5)
                else:
                    # Динамический расчет кулдауна на основе заголовков API провайдера
                    wait_time = 60
                    if e.response is not None:
                        headers = e.response.headers
                        # Ищем заголовки OpenRouter / OpenAI / Anthropic
                        retry_after = (
                            headers.get("retry-after")
                            or headers.get("x-ratelimit-reset")
                            or headers.get("retry-after-ms")
                        )
                        if retry_after:
                            try:
                                if headers.get("retry-after-ms"):
                                    wait_time = max(1, int(int(retry_after) / 1000))
                                else:
                                    wait_time = int(float(retry_after))
                                # Если провайдер отдал timestamp в будущем
                                if wait_time > time.time():

                                    wait_time = int(wait_time - time.time())
                            except ValueError:
                                pass

                    wait_time = max(2, min(wait_time, 300))  # Ограничиваем от 2с до 5 минут

                    log = f"[LLM] Рейт-лимит (429). Пауза {wait_time}с для ключа {session.api_key[:8]}"
                    main_logger.info(log)
                    agent_logger.info(log)

                    self.llm.rotator.cooldown_key(session.api_key, wait_time)

                    # Если у нас всего 1 ключ, логичнее сразу подождать здесь
                    if self.llm.rotator.total_keys() == 1:
                        await asyncio.sleep(wait_time + 1)
                    else:
                        await asyncio.sleep(1)  # Быстрый переход к следующему ключу в пуле

                continue

            except openai.AuthenticationError:
                log = "[LLM] Ключ невалиден (401). Удаляем из пула."
                main_logger.warning(log)
                agent_logger.warning(log)

                self.llm.rotator.ban_key(session.api_key)
                continue

            except Exception as e:
                log = f"[LLM] Ошибка API: {e}"
                main_logger.error(log)
                agent_logger.error(log)

                self.agent_state.update_state(AgentStatus.ERROR)
                return None

    async def _parse_response(self, raw_answer: str) -> Optional[AgentResponse]:
        """
        Парсит JSON-ответ агента.
        В случае ошибки возвращает None и записывает Traceback (ошибку) в БД.
        """
        parsed_response, error_msg = parse_llm_json(raw_answer)

        if parsed_response is not None:
            return parsed_response

        # Если { } не найдено вообще, значит LLM просто решила поболтать текстом
        if "System Error" in error_msg and "{" not in raw_answer:
            return AgentResponse(thoughts=raw_answer.strip(), actions=[])

        # Ошибка структуры
        log = "[ReAct] Ошибка структуры JSON."
        main_logger.warning(log)
        agent_logger.warning(log)

        await self.sql_ticks.save_tick(
            thoughts="[System: LLM provided invalid JSON format]",
            actions=[{"tool_name": "unknown", "parameters": {"raw": raw_answer[:500]}}],
            results={
                "execution_report": f"Format Error: {error_msg}",
                "step": self.agent_state.current_step,
                "max_steps": self.agent_state.max_react_steps,
            },
        )
        await self.event_bus.publish(Events.REACT_TICK_SAVED)
        self.agent_state.last_actions_result = f"Format Error: {error_msg}"
        return None

    def add_realtime_event(self, event_data: Dict[str, Any]) -> None:
        """
        Добавляет входящее событие в контекст агента (вызывается извне, когда агент бодрствует).

        Args:
            event_data: Данные о событии для инъекции в список пропущенных событий.
        """

        self.current_events.append(event_data)

    def _dump_context_to_file(self, messages: List[Dict[str, Any]]) -> None:
        """
        Создает дамп контекста (system prompt) в Markdown-файл для отладки.

        Args:
            messages: Массив сообщений (system и user) OpenAI формата.
        """

        dump_prompt_to_file(
            "logs/prompts/last_main_prompt.md", messages, meta_header="# MAIN AGENT DUMP"
        )

    def _encode_image(self, image_path: str) -> str:
        """Кодирует картинку с диска в Base64."""
        with open(image_path, "rb") as image_file:
            return base64.b64encode(image_file.read()).decode("utf-8")

    async def _inject_images_to_payload(
        self, messages: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Инжектит Base64 изображения в User-промпт, если находит системный маркер.

        Args:
            messages: Массив сообщений.

        Returns:
            Модифицированный массив сообщений с внедренным мультимодальным контекстом.
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
                        # Выполняем I/O операцию и энкодинг в отдельном потоке
                        base64_data = await asyncio.to_thread(
                            self._encode_image, str(path_obj)
                        )
                        ext = path_obj.suffix.lower()
                        mime = "image/jpeg" if ext in [".jpg", ".jpeg"] else f"image/{ext[1:]}"

                        new_content.append(
                            {
                                "type": "image_url",
                                "image_url": {"url": f"data:{mime};base64,{base64_data}"},
                            }
                        )

                        log = f"[ReAct] Изображение {path_obj.name} успешно инжектировано."
                        main_logger.info(log)
                        agent_logger.info(log)

                except Exception as e:
                    log = f"[ReAct] Ошибка инжектирования Base64: {e}"
                    main_logger.error(f"[ReAct] Ошибка инжектирования Base64: {e}")
                    agent_logger.error(log)

            user_msg["content"] = new_content

        return messages
