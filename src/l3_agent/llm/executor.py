"""
Isolated LLM Request Executor.

Encapsulates the logic of communicating with OpenAI-compatible APIs:
- Retries management
- Handling Rate Limits and extracting cooldown time from response headers
- Banning dead or invalid keys (HTTP 401)
- Counting and tracking token usage
- Enforcing minimum call intervals (throttling)

Adheres strictly to Single Responsibility Principle (SRP): agent reasoning loops
(ReAct, Swarm) remain completely unaware of raw HTTP errors.
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
    Unified entry point for invoking language models.
    Hides all complexity of handling network and API errors.
    """

    def __init__(
        self,
        llm_client: LLMClient,
        token_tracker: TokenTracker,
        min_call_interval_sec: float = 0.0,
    ) -> None:
        """
        Args:
            llm_client: Client for retrieving HTTP sessions (AsyncOpenAI).
            token_tracker: Tool for tracking input and output tokens.
            min_call_interval_sec: Minimum delay in seconds required between API calls.
        """

        self.llm = llm_client
        self.tracker = token_tracker
        self.min_call_interval_sec = min_call_interval_sec
        self._last_call_time: float = 0.0

    async def _enforce_min_call_interval(
        self, logger: logging.Logger, log_prefix: str
    ) -> None:
        """
        Enforces a minimum time delay between consecutive LLM requests.
        """
        if self.min_call_interval_sec <= 0.0:
            return

        now = time.time()
        elapsed = now - self._last_call_time
        if self._last_call_time > 0.0 and elapsed < self.min_call_interval_sec:
            delay = self.min_call_interval_sec - elapsed
            logger.info(
                f"{log_prefix} Throttling request: waiting {delay:.2f}s to respect min_call_interval_sec ({self.min_call_interval_sec})."
            )
            await asyncio.sleep(delay)

        self._last_call_time = time.time()

    async def execute(
        self,
        model_name: str,
        messages: List[Dict[str, Any]],
        temperature: float,
        logger: logging.Logger,
        log_prefix: str,
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_choice: Optional[str] = None,
        max_retries: int = 5,
        max_timeout_retries: int = 3,
    ) -> Optional[str]:
        """
        Executes a request to the LLM with a robust retry system and call throttling.

        Args:
            model_name: Name of the target model (e.g., 'gemini-3.1-flash-lite').
            messages: Formatted message context list.
            temperature: Creativity parameter (0.0 to 2.0).
            logger: Target subsystem logger (ReAct, Swarm, ToT).
            log_prefix: Logging prefix (e.g., '[ReAct LLM]').
            tools: Optional JSON Schema list of available tools.
            tool_choice: Optional string to force a specific tool call.
            max_retries: Total retry attempts limit for any exceptions.
            max_timeout_retries: Specific retry attempts limit for timeouts.

        Returns:
            Optional[str]: Raw assistant response text or tool call JSON arguments.
                          Returns None if all retries failed or a fatal error occurred.
        """

        self.tracker.add_input_record(messages, log_prefix=log_prefix, logger=logger)
        timeout_count = 0

        for attempt in range(max_retries):
            try:
                # Respect minimum interval between calls before obtaining a session
                await self._enforce_min_call_interval(logger, log_prefix)

                # Retrieve an active authenticated session
                session = self.llm.get_session()

                # Execute request
                kwargs = {
                    "model": model_name,
                    "messages": messages,
                    "temperature": temperature,
                    "timeout": 60.0,
                }
                if tools:
                    kwargs["tools"] = tools
                if tool_choice is not None:
                    kwargs["tool_choice"] = tool_choice
                
                kwargs["response_format"] = {"type": "json_object"}
                
                response = await session.chat.completions.create(**kwargs)
                
                # --- ПЕРЕХВАТ СЫРОГО ОТВЕТА ---
                #logger.error(f"{log_prefix} RAW API DUMP: {response.model_dump_json() if hasattr(response, 'model_dump_json') else response}")

                # Extract content and count tokens
                raw_answer = self._extract_response_text(response)

                self.tracker.add_output_record(
                    raw_answer, log_prefix=log_prefix, logger=logger
                )

                return raw_answer

            except AllKeysExhaustedError as e:
                logger.warning(
                    f"{log_prefix} All keys in cooldown. Waiting {e.wait_time} sec."
                )
                await asyncio.sleep(e.wait_time + 1)
                continue

            except openai.RateLimitError as e:
                wait_time = self._calculate_rate_limit_cooldown(e)
                logger.warning(
                    f"{log_prefix} Rate Limit (429). Key {session.api_key[:8]} cooled down for {wait_time}s."
                )

                self.llm.rotator.cooldown_key(session.api_key, wait_time)

                if self.llm.rotator.total_keys() == 1:
                    await asyncio.sleep(wait_time + 1)
                else:
                    await asyncio.sleep(1)  # Fast transition to the next key
                continue

            except openai.AuthenticationError:
                logger.warning(
                    f"{log_prefix} Invalid API key (401). Removing from pool ({session.api_key[:10]})."
                )
                self.llm.rotator.ban_key(session.api_key)
                continue

            except (openai.APITimeoutError, asyncio.TimeoutError):
                timeout_count += 1
                if timeout_count >= max_timeout_retries:
                    logger.error(
                        f"{log_prefix} API unavailable after {max_timeout_retries} timeouts. Aborting."
                    )
                    return None

                logger.warning(
                    f"{log_prefix} API request timed out. Retrying ({timeout_count}/{max_timeout_retries})."
                )
                continue

            except Exception as e:
                # Если это была последняя из разрешенных попыток — падаем с концами
                if attempt == max_retries - 1:
                    logger.error(f"{log_prefix} Fatal API error after {max_retries} attempts: {e}")
                    return None

                # Экспоненциальный бэкофф: 2, 4, 8, 16... секунд
                backoff_time = 2 ** (attempt + 1)
                
                logger.warning(
                    f"{log_prefix} Internal API error: {e}. Retrying ({attempt + 1}/{max_retries}) in {backoff_time}s..."
                )
                await asyncio.sleep(backoff_time)
                continue

        return None

    # -------------------------------------------------------------------------
    # Private Helpers
    # -------------------------------------------------------------------------

    def _extract_response_text(self, response: Any) -> str:
        """
        Extracts raw text content or tool JSON arguments from the OpenAI response.
        """
        # 1. Ловим вложенные ошибки провайдера (когда API не упало по HTTP, но прислало мусор)
        api_error = getattr(response, "error", None)
        if api_error:
            raise ValueError(f"Upstream Provider Error: {api_error}")

        # 2. Защита от пустого массива (наш изначальный предохранитель)
        if not getattr(response, "choices", None):
            raise ValueError("Provider API shit the bed: 'choices' array is missing or None.")

        message_obj = response.choices[0].message

        if getattr(message_obj, "tool_calls", None):
            return str(message_obj.tool_calls[0].function.arguments)

        return message_obj.content or ""

    def _calculate_rate_limit_cooldown(self, error: openai.RateLimitError) -> int:
        """
        Calculates key freeze time based on the provider's response headers.
        """

        # If the provider explicitly reports insufficient funds
        err_code = getattr(error.body, "get", lambda x: None)("code")
        if err_code == "insufficient_quota" or "billing" in str(error).lower():
            return 86400  # Freeze for 24 hours

        wait_time = 30  # Default fallback

        if error.response is not None:
            headers = error.response.headers
            # Attempt to extract common rate limit reset headers
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

                    # If the timestamp represents a future epoch (e.g. OpenAI)
                    if wait_time > time.time():
                        wait_time = int(wait_time - time.time())
                except ValueError:
                    pass

        # Clamp boundaries: no less than 2s (avoid spam) and no more than 5 minutes
        return max(2, min(wait_time, 300))
