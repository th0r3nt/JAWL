"""
Изолированный исполнитель запросов к LLM.

Инкапсулирует логику общения с OpenAI-совместимым API:
- Управление ретраями
- Обработка Rate Limits и вычисление кулдауна из заголовков
- Ротация мертвых или заблокированных ключей (HTTP 401)
- Логирование токенов

Соблюдает SRP: циклы агента (ReAct, Swarm) не знают о деталях HTTP-ошибок.
"""

import time
import asyncio
import logging
from typing import Dict, Any, List, Optional

import openai

from src.l3_agent.llm.client import LLMClient
from src.l3_agent.llm.exceptions import AllKeysExhaustedError
from src.utils.token_tracker import TokenTracker


class LLMExecutor:
    """
    Единая точка входа для вызова языковых моделей.
    Скрывает всю сложность обработки сетевых ошибок.
    """

    def __init__(self, llm_client: LLMClient, token_tracker: TokenTracker) -> None:
        """
        Args:
            llm_client: Клиент для получения HTTP-сессий (AsyncOpenAI).
            token_tracker: Инструмент для учета входящих и исходящих токенов.
        """

        self.llm = llm_client
        self.tracker = token_tracker

    async def execute(
        self,
        model_name: str,
        messages: List[Dict[str, Any]],
        temperature: float,
        logger: logging.Logger,
        log_prefix: str,
        tools: Optional[List[Dict[str, Any]]] = None,
        max_retries: int = 2,
        max_timeout_retries: int = 1,
    ) -> Optional[str]:
        """
        Выполняет запрос к LLM с надежной системой повторных попыток.

        Args:
            model_name: Название модели (напр. 'gemini-3.1-flash-lite').
            messages: Сформированный контекст (список сообщений).
            temperature: Температура модели (0.0 - 2.0).
            logger: Логгер целевой подсистемы (ReAct, Swarm, ToT).
            log_prefix: Префикс для логов (напр. '[ReAct LLM]').
            tools: Опциональная JSON Schema инструментов.
            max_retries: Общий лимит попыток при любых ошибках.
            max_timeout_retries: Специфичный лимит именно для таймаутов (API не отвечает).

        Returns:
            Сырой текст ответа модели (или JSON-строка вызова инструмента).
            Вернет None, если все попытки исчерпаны или произошла фатальная ошибка.
        """

        self.tracker.add_input_record(messages, log_prefix=log_prefix, logger=logger)
        timeout_count = 0

        for attempt in range(max_retries):
            try:
                # Получаем живую сессию из ротатора
                session = self.llm.get_session()

                # Выполняем запрос
                kwargs = {
                    "model": model_name,
                    "messages": messages,
                    "temperature": temperature,
                    "timeout": 120.0,
                }
                if tools:
                    kwargs["tools"] = tools

                response = await session.chat.completions.create(**kwargs)

                # Извлекаем ответ и считаем токены
                raw_answer = self._extract_response_text(response)

                self.tracker.add_output_record(
                    raw_answer, log_prefix=log_prefix, logger=logger
                )

                # Сырой JSON-ответ: будет парситься дальше
                return raw_answer

            except AllKeysExhaustedError as e:
                logger.warning(f"{log_prefix} Все ключи в кулдауне. Ждем {e.wait_time} сек.")
                await asyncio.sleep(e.wait_time + 1)
                continue

            except openai.RateLimitError as e:
                wait_time = self._calculate_rate_limit_cooldown(e)
                logger.warning(
                    f"{log_prefix} Rate Limit (429). Кулдаун ключа {session.api_key[:8]} на {wait_time}с."
                )

                self.llm.rotator.cooldown_key(session.api_key, wait_time)

                if self.llm.rotator.total_keys() == 1:
                    await asyncio.sleep(wait_time + 1)
                else:
                    await asyncio.sleep(1)  # Быстрый переход к следующему ключу
                continue

            except openai.AuthenticationError:
                logger.warning(
                    f"{log_prefix} Ключ невалиден (401). Удаление из пула ({session.api_key[:10]})."
                )
                self.llm.rotator.ban_key(session.api_key)
                continue

            except (openai.APITimeoutError, asyncio.TimeoutError):
                timeout_count += 1
                if timeout_count >= max_timeout_retries:
                    logger.error(
                        f"{log_prefix} API недоступно после {max_timeout_retries} таймаутов. Прерывание."
                    )
                    return None

                logger.warning(
                    f"{log_prefix} Таймаут ответа API. Повтор ({timeout_count}/{max_timeout_retries})."
                )
                continue

            except Exception as e:
                # Для непредвиденных ошибок делаем паузу перед следующей попыткой
                if attempt == max_retries - 1:
                    logger.error(f"{log_prefix} Фатальная ошибка API: {e}")
                    return None

                logger.error(f"{log_prefix} Внутренняя ошибка API: {e}. Повтор запроса.")
                await asyncio.sleep(2)
                continue

        return None

    # =========================================================================
    # ПРИВАТНЫЕ ХЕЛПЕРЫ
    # =========================================================================

    def _extract_response_text(self, response: Any) -> str:
        """
        Извлекает сырой текст или JSON-аргументы инструмента из ответа OpenAI.
        """

        message_obj = response.choices[0].message

        if message_obj.tool_calls:
            return str(message_obj.tool_calls[0].function.arguments)

        return message_obj.content or ""

    def _calculate_rate_limit_cooldown(self, error: openai.RateLimitError) -> int:
        """
        Вычисляет время заморозки ключа на основе заголовков ответа провайдера.
        Возвращает количество секунд.
        """

        # Если провайдер прямо говорит, что кончились деньги/квота
        err_code = getattr(error.body, "get", lambda x: None)("code")
        if err_code == "insufficient_quota" or "billing" in str(error).lower():
            return 86400  # Бан на сутки

        wait_time = 30  # Дефолт

        if error.response is not None:
            headers = error.response.headers
            # Пытаемся найти специфичные заголовки OpenRouter/OpenAI/Anthropic
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

                    # Если провайдер (например, OpenAI) отдал timestamp в будущем
                    if wait_time > time.time():
                        wait_time = int(wait_time - time.time())
                except ValueError:
                    pass

        # Зажимаем лимиты: не меньше 2 сек (во избежание спама) и не больше 5 минут
        return max(2, min(wait_time, 300))
