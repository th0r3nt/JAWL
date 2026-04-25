import tiktoken
from collections import deque
from typing import Any, Dict, List

from src.utils.logger import system_logger


class TokenTracker:
    """
    Отслеживает статистику использования токенов.
    Считает токены за каждый вызов и агрегирует статистику по тикам.
    """

    def __init__(self, maxlen: int = 100):
        self.input_history: deque[Dict[str, Any]] = deque(maxlen=maxlen)
        self.output_history: deque[Dict[str, Any]] = deque(maxlen=maxlen)

        # Накопители для текущего (активного) тика
        self._current_tick_in = 0
        self._current_tick_out = 0
        self.total_ticks = 0

        try:
            self.encoding = tiktoken.get_encoding("o200k_base")
        except Exception:
            self.encoding = tiktoken.get_encoding("cl100k_base")

    def _approximate_tokens(self, text: str) -> int:
        """Фоллбек функция на случай, если тиктокен в пиве."""

        if not text:
            return 0
        try:
            return len(self.encoding.encode(text, disallowed_special=()))
        except Exception:
            return max(1, len(text) // 4)

    def count_messages_tokens(self, messages: List[Any]) -> int:
        """Считает токены."""

        num_tokens = 0
        for message in messages:
            num_tokens += 3
            if isinstance(message, dict):
                m_dict = message
            elif hasattr(message, "model_dump"):
                m_dict = message.model_dump()
            else:
                m_dict = {"content": str(message)}

            for key, value in m_dict.items():
                if value is None:
                    continue
                if isinstance(value, str):
                    num_tokens += self._approximate_tokens(value)
                elif isinstance(value, list):
                    num_tokens += self._approximate_tokens(str(value))
        num_tokens += 3
        return num_tokens

    def add_input_record(self, messages: List[Any]) -> None:
        total_tokens = self.count_messages_tokens(messages)
        self.input_history.append({"total": total_tokens})

        # Плюсуем в счетчик текущего тика
        self._current_tick_in += total_tokens
        system_logger.info(f"[LLM] Input tokens: {total_tokens}.")

        return total_tokens

    def add_output_record(self, output_text: str) -> None:
        output_tokens = self._approximate_tokens(output_text)
        self.output_history.append({"total": output_tokens})

        # Плюсуем в счетчик текущего тика
        self._current_tick_out += output_tokens
        system_logger.info(f"[LLM] Output tokens: {output_tokens}.")
