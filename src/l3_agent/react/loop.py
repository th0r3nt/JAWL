import openai
import asyncio
from typing import Dict, Any
from pydantic import ValidationError

# Для анализа медиа
import base64
import re
import copy
from pathlib import Path

from src.utils.logger import system_logger
from src.utils.token_tracker import TokenTracker

from src.l0_state.agent.state import AgentState, AgentStatus
from src.l1_databases.sql.management.ticks import SQLTicks

from src.l3_agent.llm.client import LLMClient
from src.l3_agent.prompt.builder import PromptBuilder
from src.l3_agent.context.builder import ContextBuilder

# Импортируем готовый роутер скиллов
from src.l3_agent.skills.registry import execute_skill
from src.l3_agent.skills.schema import AgentResponse


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
        tools: list,
        cooldown_sec: int = 30,
    ):
        self.llm = llm_client
        self.prompt_builder = prompt_builder
        self.context_builder = context_builder
        self.agent_state = agent_state
        self.sql_ticks = sql_ticks
        self.tracker = token_tracker
        self.tools = tools
        self.cooldown_sec = cooldown_sec

        self.current_events: list[str] = []  # Хранилище событий для текущего цикла

    def add_realtime_event(self, event_str: str):
        """
        Добавляет входящее событие в контекст в том случае, если агент уже думает.
        """
        self.current_events.append(event_str)

    async def run(self, event_name: str, payload: Dict[str, Any], missed_events: list[str]):
        """
        Запускает ReAct цикл вызова к LLM.
        """

        # Переносим пропущенные события в память текущего цикла
        self.current_events = missed_events.copy()

        # Очищаем кэш тиков перед стартом
        self.sql_ticks.clear_session_cache()

        try:
            self.agent_state.reset_step()
            system_logger.info(
                f"[ReAct] Цикл инициирован. Причина: {event_name} (LLM Model: {self.agent_state.llm_model})."
            )

            # Системный промпт статический, собираем один раз
            prompt = self.prompt_builder.build()

            messages = [
                {"role": "system", "content": prompt},  # Статичный промпт
                {"role": "user", "content": ""},  # Будет перезаписываться на каждом шаге
            ]

            step = 1
            while step <= self.agent_state.max_react_steps:
                self.agent_state.current_step = step
                self.agent_state.update_state(AgentStatus.THINKING)

                # Передаем обновляемый список self.current_events
                context = await self.context_builder.build(
                    event_name, payload, self.current_events
                )

                # Обновляем блок контекста в истории сообщений
                messages[1]["content"] = context

                # Трекаем токены на каждом из шагов, которые реально улетают в API (включая историю шагов)
                self.tracker.add_input_record(messages=messages)

                # Делаем глубокое копирование, чтобы Base64 не попал в БД тиков и логи
                api_messages = copy.deepcopy(messages)
                api_messages = self._inject_images_to_payload(api_messages)

                self._dump_context_to_file(api_messages)

                system_logger.info(f"[ReAct] Шаг {step}/{self.agent_state.max_react_steps}.")
                try:
                    session = self.llm.get_session()
                    response = await session.chat.completions.create(
                        model=self.agent_state.llm_model,
                        messages=api_messages,
                        tools=self.tools,
                        tool_choice={
                            "type": "function",
                            "function": {"name": "execute_skill"},
                        },
                        temperature=self.agent_state.temperature,
                        max_tokens=4096,
                    )

                    message_obj = response.choices[0].message
                    raw_answer = message_obj.content or ""

                    if message_obj.tool_calls:
                        raw_answer += str(message_obj.tool_calls[0].function.arguments)

                    self.tracker.add_output_record(raw_answer)

                except openai.RateLimitError as e:
                    err_code = getattr(e.body, "get", lambda x: None)("code")
                    err_msg = str(e).lower()

                    if (
                        err_code == "insufficient_quota"
                        or "billing" in err_msg
                        or "check your plan" in err_msg
                    ):
                        system_logger.error(
                            f"[LLM] Квота исчерпана или нет денег. Бан ключа {session.api_key[:8]} на 24ч"
                        )
                        self.llm.rotator.cooldown_key(session.api_key, 86400)
                    else:
                        system_logger.info(
                            f"[LLM] Рейт-лимит (RPM/TPM). Пауза 60с для {session.api_key[:8]}"
                        )
                        self.llm.rotator.cooldown_key(session.api_key, 60)

                    await asyncio.sleep(self.cooldown_sec)
                    system_logger.info(
                        f"[LLM] Пауза на {self.cooldown_sec} сек. перед следующим API вызовом."
                    )
                    continue

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

                if not response_message.tool_calls:
                    system_logger.info(
                        "[ReAct] Остановка цикла: модель не вызвала ни одного инструмента."
                    )
                    break

                tool_call = response_message.tool_calls[0]
                args_str = tool_call.function.arguments

                # Валидация ответа LLM через Pydantic
                try:
                    parsed_response = AgentResponse.model_validate_json(args_str)

                except ValidationError as e:
                    system_logger.warning(
                        f"[ReAct] Ошибка структуры от LLM. Запрашиваем исправление. Детали: {e}"
                    )
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "name": tool_call.function.name,
                            "content": f"Format Error: {e}",
                        }
                    )
                    step += 1
                    continue

                thoughts = " ".join(parsed_response.thoughts.split())
                actions = parsed_response.actions

                if thoughts:
                    system_logger.info(f"[Thoughts]: {thoughts}")

                if not actions:
                    system_logger.info(
                        "[ReAct] Агент передал пустой массив действий. ReAct-цикл завершен."
                    )
                    await self.sql_ticks.save_tick(
                        thoughts=thoughts, actions=[], results={"status": "completed"}
                    )
                    break

                self.agent_state.update_state(AgentStatus.ACTING)
                results_str = await execute_skill(actions=actions)

                # Сохраняем данные для RAG на следующем шаге
                self.agent_state.last_thoughts = thoughts

                # Вытаскиваем только строковые аргументы из функций (длиннее 3 символов)
                args_to_rag = []
                for act in actions:
                    for val in act.parameters.values():
                        if isinstance(val, str) and len(val) > 3:
                            args_to_rag.append(val)
                self.agent_state.last_action_args = args_to_rag

                # Если в ответе есть слово "Ошибка" или "Error" и ответ короткий - сохраняем
                self.agent_state.last_action_error = ""
                if len(results_str) < 500 and (
                    "ошибка" in results_str.lower()
                    or "error" in results_str.lower()
                    or "fail" in results_str.lower()
                ):
                    self.agent_state.last_action_error = results_str

                await self.sql_ticks.save_tick(
                    thoughts=thoughts,
                    actions=[a.model_dump() for a in actions],
                    results={"execution_report": results_str},
                )

                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "name": tool_call.function.name,
                        "content": results_str,
                    }
                )

                step += 1

        finally:
            # Обязательно сбрасываем кэш при любом исходе
            self.sql_ticks.clear_session_cache()
            self.agent_state.update_state(AgentStatus.IDLE)

    # ============================================================================
    # СЛУЖЕБНЫЕ МЕТОДЫ
    # ============================================================================

    def _dump_context_to_file(self, messages: list):
        """
        Сохраняет финальный промпт в Markdown-файл для отладки.
        Безопасно парсит как обычные dict, так и объекты OpenAI.
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
        Сканирует историю сообщений на наличие маркера [IMAGE_REQUEST: /path/...].
        Если находит, добавляет Base64 картинку в текущий user-контекст.
        """
        image_paths = []

        # Ищем маркеры ТОЛЬКО в ответах инструментов (role == "tool")
        # внутри текущего ReAct-цикла. Строго игнорируем role == "user",
        # чтобы не вытянуть старый маркер из контекста прошлых тиков (баг залипания картинок)
        for msg in messages:
            if isinstance(msg, dict):
                role = msg.get("role")
                content = msg.get("content", "")
            else:
                role = getattr(msg, "role", "")
                content = getattr(msg, "content", "")

            if role == "tool" and content and isinstance(content, str):
                matches = re.findall(r"\[IMAGE_REQUEST:\s*(.+?)\]", content)
                image_paths.extend(matches)

        if not image_paths:
            return messages

        # Инжектим картинку строго в messages[1] (блок контекста пользователя)
        user_msg = messages[1]

        if isinstance(user_msg, dict) and user_msg.get("role") == "user":
            original_text = user_msg["content"]
            new_content = [{"type": "text", "text": original_text}]

            for img_path in set(image_paths):  # set, чтобы не дублировать
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
                            f"[ReAct] Изображение {path_obj.name} успешно инжектировано в промпт."
                        )
                except Exception as e:
                    system_logger.error(f"[ReAct] Ошибка инжектирования Base64: {e}")

            user_msg["content"] = new_content

        return messages
