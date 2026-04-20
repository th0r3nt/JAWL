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

        # Статистика по тикам (полным ReAct-циклам)
        self.tick_history: deque[Dict[str, int]] = deque(maxlen=maxlen)

        # Накопители для текущего (активного) тика
        self._current_tick_in = 0
        self._current_tick_out = 0
        self.total_ticks = 0

        try:
            self.encoding = tiktoken.get_encoding("o200k_base")
        except Exception:
            self.encoding = tiktoken.get_encoding("cl100k_base")

    def _approximate_tokens(self, text: str) -> int:
        if not text:
            return 0
        try:
            return len(self.encoding.encode(text, disallowed_special=()))
        except Exception:
            return max(1, len(text) // 4)

    def count_messages_tokens(self, messages: List[Any]) -> int:
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

    def add_output_record(self, output_text: str) -> None:
        output_tokens = self._approximate_tokens(output_text)
        self.output_history.append({"total": output_tokens})

        # Плюсуем в счетчик текущего тика
        self._current_tick_out += output_tokens
        system_logger.info(f"[LLM] Output tokens: {output_tokens}.")

    def finalize_tick(self):
        """Завершает учет текущего тика и выводит статистику каждые 10 тиков."""
        self.total_ticks += 1

        # Сохраняем агрегированные данные тика
        self.tick_history.append({"in": self._current_tick_in, "out": self._current_tick_out})

        # Логируем статистику каждые 10 тиков
        if self.total_ticks % 10 == 0:
            self._log_periodic_stats()

        # Сбрасываем накопители для следующего тика
        self._current_tick_in = 0
        self._current_tick_out = 0

    def _log_periodic_stats(self):
        """Выводит сводный отчет за последние 10 тиков."""
        last_10 = list(self.tick_history)[-10:]
        total_in = sum(t["in"] for t in last_10)
        total_out = sum(t["out"] for t in last_10)
        avg_in = total_in // len(last_10)
        avg_out = total_out // len(last_10)

        report = (
            f"\n"
            f"╔══════════════════ TOKEN STATISTICS (Last 10 Ticks) ══════════════════╗\n"
            f"║ Total Input:  {total_in:<10}         | Avg per Tick: {avg_in:<10}    ║\n"
            f"║ Total Output: {total_out:<10}        | Avg per Tick: {avg_out:<10}   ║\n"
            f"║ Total Ticks:  {self.total_ticks:<46}                                 ║\n"
            f"╚══════════════════════════════════════════════════════════════════════╝"
        )
        system_logger.info(f"[System] {report}")

    def get_token_statistics(self) -> str:
        # Оставляем этот метод для контекста агента (если нужно)
        if not self.tick_history:
            return "Статистика пуста."
        return f"Всего пройдено тиков: {self.total_ticks}. Средний расход за тик: {self._current_tick_in} in / {self._current_tick_out} out"
