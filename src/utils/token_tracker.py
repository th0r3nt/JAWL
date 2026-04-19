import tiktoken
from collections import deque
from typing import Any, Dict, List

from src.utils.logger import system_logger


class TokenTracker:
    """
    Отслеживает статистику использования токенов.
    Использует tiktoken для точного подсчета.
    """

    def __init__(self, maxlen: int = 100):

        self.input_history: deque[Dict[str, Any]] = deque(maxlen=maxlen)
        self.output_history: deque[Dict[str, Any]] = deque(maxlen=maxlen)
        try:
            self.encoding = tiktoken.get_encoding("o200k_base")
        except Exception:
            self.encoding = tiktoken.get_encoding("cl100k_base")

    def _approximate_tokens(self, text: str) -> int:
        """Точный подсчет токенов для строки."""

        if not text:
            return 0
        try:
            return len(self.encoding.encode(text, disallowed_special=()))
        except Exception:
            return max(1, len(text) // 4)

    def count_messages_tokens(self, messages: List[Dict[str, Any]]) -> int:
        """
        Подсчитывает токены для всего списка сообщений (chat history).
        Учитывает накладные расходы на структуру (роли, имена).
        """

        num_tokens = 0
        for message in messages:
            num_tokens += 3  # Каждое сообщение обрамляется метаданными
            for key, value in message.items():
                if isinstance(value, str):
                    num_tokens += self._approximate_tokens(value)
                elif isinstance(value, list):  # Для сложных структур tool_calls
                    num_tokens += self._approximate_tokens(str(value))
        num_tokens += 3  # Ответ ассистента начинается с метаданных
        return num_tokens

    def add_input_record(self, messages: List[Dict[str, Any]]) -> None:
        """Записывает реальное количество входных токенов всего запроса."""

        total_tokens = self.count_messages_tokens(messages)

        self.input_history.append({"total": total_tokens})

        system_logger.info(f"[LLM] Input tokens (total window): {total_tokens}.")

    def add_output_record(self, output_text: str) -> None:
        """Записывает исходящие токены."""

        output_tokens = self._approximate_tokens(output_text)
        self.output_history.append({"total": output_tokens})
        system_logger.info(f"[LLM] Output tokens: {output_tokens}.")

    def get_token_statistics(self) -> str:
        """Возвращает статистику использования."""

        stats_lines = []
        if self.input_history:
            total_in = sum(item["total"] for item in self.input_history)
            avg_in = total_in // len(self.input_history)
            stats_lines.append(
                f"Input: за последние {len(self.input_history)} API вызовов: {total_in} токенов (среднее {avg_in}/вызов)."
            )
        if self.output_history:
            total_out = sum(item["total"] for item in self.output_history)
            avg_out = total_out // len(self.output_history)
            stats_lines.append(
                f"Output: за последние {len(self.output_history)} API вызовов: {total_out} токенов (среднее {avg_out}/вызов)."
            )
        return "\n".join(stats_lines)
