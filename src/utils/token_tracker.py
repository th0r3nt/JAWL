from collections import deque
from typing import Any, Dict

from src.utils.logger import system_logger


class TokenTracker:
    """
    Отслеживает статистику использования токенов.
    """

    def __init__(self, maxlen: int = 100):
        self.input_history: deque[Dict[str, Any]] = deque(maxlen=maxlen)
        self.output_history: deque[Dict[str, Any]] = deque(maxlen=maxlen)

    @staticmethod
    def _approximate_tokens(text: str) -> int:
        """
        Приблизительный подсчет токенов без тяжелых зависимостей.
        1 токен ~= 4 символа (стандартная эвристика).
        """
        if not text:
            return 0
        return max(1, len(text) // 4)

    def add_input_record(self, prompt: str, context: str) -> str:
        """Записывает входящие токены текущего цикла."""
        prompt_tokens = self._approximate_tokens(prompt)
        context_tokens = self._approximate_tokens(context)

        total_tokens = prompt_tokens + context_tokens

        self.input_history.append(
            {"prompt": prompt_tokens, "context": context_tokens, "total": total_tokens}
        )

        msg = f"Input tokens: {total_tokens} (prompt: {prompt_tokens}, context: {context_tokens})."
        system_logger.info(msg)
        return msg

    def add_output_record(self, output_text: str) -> str:
        """Записывает исходящие (сгенерированные) токены текущего цикла."""
        output_tokens = self._approximate_tokens(output_text)

        self.output_history.append({"total": output_tokens})

        msg = f"Output tokens: {output_tokens}."
        system_logger.info(msg)
        return msg

    def get_token_statistics(self) -> str:
        """Возвращает статистику входящих и исходящих токенов."""
        stats_lines = []

        # Подсчет Input токенов
        if self.input_history:
            total_in = sum(item["total"] for item in self.input_history)
            avg_in = total_in // len(self.input_history)
            stats_lines.append(
                f"Input: за последние {len(self.input_history)} API вызовов: {total_in} входных токенов (в среднем {avg_in}/вызов)."
            )
        else:
            stats_lines.append("Input: No data yet.")

        # Подсчет Output токенов
        if self.output_history:
            total_out = sum(item["total"] for item in self.output_history)
            avg_out = total_out // len(self.output_history)
            stats_lines.append(
                f"Output: за последние {len(self.output_history)} API вызовов: {total_out} выходных токенов (в среднем {avg_out}/вызов)."
            )
        else:
            stats_lines.append("Output: No data yet.")

        return "\n".join(stats_lines)
