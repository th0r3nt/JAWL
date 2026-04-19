import tiktoken
from collections import deque
from typing import Any, Dict

from src.utils.logger import system_logger


class TokenTracker:
    """
    Отслеживает статистику использования токенов.
    Использует tiktoken (энкодер от OpenAI) для точного подсчета.
    """

    def __init__(self, maxlen: int = 100):
        self.input_history: deque[Dict[str, Any]] = deque(maxlen=maxlen)
        self.output_history: deque[Dict[str, Any]] = deque(maxlen=maxlen)
        try:
            # o200k_base - актуальный энкодер
            self.encoding = tiktoken.get_encoding("o200k_base")
        except Exception:
            # Fallback на старый, если что-то пойдет не так
            self.encoding = tiktoken.get_encoding("cl100k_base")

    def _approximate_tokens(self, text: str) -> int:
        """Точный подсчет токенов через tiktoken."""
        if not text:
            return 0
        try:
            # disallowed_special=() разрешает энкодеру глотать спец-токены, если они попадутся
            return len(self.encoding.encode(text, disallowed_special=()))
        except Exception:
            # Fallback на случай непредвиденных крашей кодировщика
            return max(1, len(text) // 4)

    def add_input_record(self, prompt: str, context: str) -> None:
        """Записывает входящие токены текущего цикла."""
        prompt_tokens = self._approximate_tokens(prompt)
        context_tokens = self._approximate_tokens(context)

        total_tokens = prompt_tokens + context_tokens

        self.input_history.append(
            {"prompt": prompt_tokens, "context": context_tokens, "total": total_tokens}
        )

        system_logger.info(
            f"[LLM] Input tokens: {total_tokens} (prompt: {prompt_tokens}, context: {context_tokens})."
        )

    def add_output_record(self, output_text: str) -> None:
        """Записывает исходящие (сгенерированные) токены текущего цикла."""

        output_tokens = self._approximate_tokens(output_text)

        self.output_history.append({"total": output_tokens})

        system_logger.info(f"[LLM] Output tokens: {output_tokens}.")

    def get_token_statistics(self) -> str:
        """Возвращает статистику входящих и исходящих токенов."""

        stats_lines = []

        if self.input_history:
            total_in = sum(item["total"] for item in self.input_history)
            avg_in = total_in // len(self.input_history)
            stats_lines.append(
                f"Input: за последние {len(self.input_history)} API вызовов: {total_in} входных токенов (в среднем {avg_in}/вызов)."
            )
        else:
            stats_lines.append("Input: No data yet.")

        if self.output_history:
            total_out = sum(item["total"] for item in self.output_history)
            avg_out = total_out // len(self.output_history)
            stats_lines.append(
                f"Output: за последние {len(self.output_history)} API вызовов: {total_out} выходных токенов (в среднем {avg_out}/вызов)."
            )
        else:
            stats_lines.append("Output: No data yet.")

        return "\n".join(stats_lines)
