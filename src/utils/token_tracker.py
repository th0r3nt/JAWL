"""
Инструмент для отслеживания расхода токенов LLM (Token Tracker).

Агрегирует статистику токенов (входящих и исходящих) за каждый ReAct-тик,
сохраняя MRU-историю вызовов. Использует `tiktoken` для точного подсчета (если доступен),
или эвристический фоллбэк для локальных/альтернативных моделей.
"""

import tiktoken
from collections import deque
from typing import Any, Dict, List

from src.utils.logger import system_logger


class TokenTracker:
    """
    Отслеживает статистику использования токенов языковой модели.
    Считает токены за каждый вызов LLM и хранит ограниченную историю.
    """

    def __init__(self, maxlen: int = 100) -> None:
        """
        Инициализирует трекер с заданным лимитом памяти истории.

        Args:
            maxlen (int): Количество последних записей о токенах для хранения в оперативной памяти.
        """
        
        self.input_history: deque[Dict[str, Any]] = deque(maxlen=maxlen)
        self.output_history: deque[Dict[str, Any]] = deque(maxlen=maxlen)

        # Накопители для текущего (активного) тика
        self._current_tick_in = 0
        self._current_tick_out = 0

        # Пытаемся загрузить современные кодировки OpenAI
        try:
            self.encoding = tiktoken.get_encoding("o200k_base")
        except Exception:
            self.encoding = tiktoken.get_encoding("cl100k_base")

    def _approximate_tokens(self, text: str) -> int:
        """
        Вычисляет количество токенов в строке. Использует `tiktoken` при наличии,
        иначе применяет простую эвристику (~4 символа на токен).

        Args:
            text (str): Оцениваемый текст.

        Returns:
            int: Приблизительное (или точное) количество токенов.
        """

        if not text:
            return 0
        try:
            return len(self.encoding.encode(text, disallowed_special=()))
        except Exception:
            return max(1, len(text) // 4)

    def count_messages_tokens(self, messages: List[Any]) -> int:
        """
        Агрегирует и подсчитывает токены в списке сообщений OpenAI формата (List of Dicts).

        Args:
            messages (List[Any]): Массив словарей (роль и контент) для LLM.

        Returns:
            int: Общее количество токенов во всем массиве сообщений.
        """

        num_tokens = 0
        for message in messages:
            num_tokens += 3  # Накладные расходы на каждое сообщение
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
        num_tokens += 3  # Накладные расходы на ответ модели
        return num_tokens

    def add_input_record(self, messages: List[Any], log_prefix: str = "[LLM]") -> int:
        """
        Добавляет запись о расходе токенов на системный и пользовательский промпт.

        Args:
            messages (List[Any]): Входящий массив сообщений.
            log_prefix (str, optional): Префикс для логера (чтобы отличать Оркестратора от Субагентов).

        Returns:
            int: Потребленное количество токенов.
        """

        total_tokens = self.count_messages_tokens(messages)
        self.input_history.append({"total": total_tokens})

        # Плюсуем в счетчик текущего тика
        self._current_tick_in += total_tokens
        system_logger.info(f"{log_prefix} Input tokens: {total_tokens}.")

        return total_tokens

    def add_output_record(self, output_text: str, log_prefix: str = "[LLM]") -> None:
        """
        Добавляет запись о токенах, сгенерированных моделью (исходящих).

        Args:
            output_text (str): Сырой текст, возвращенный LLM.
            log_prefix (str, optional): Префикс для логера.
        """

        output_tokens = self._approximate_tokens(output_text)
        self.output_history.append({"total": output_tokens})

        # Плюсуем в счетчик текущего тика
        self._current_tick_out += output_tokens
        system_logger.info(f"{log_prefix} Output tokens: {output_tokens}.")
