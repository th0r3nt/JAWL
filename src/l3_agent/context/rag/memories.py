"""
Система автоматического семантического поиска воспоминаний (Auto-RAG).

Анализирует входящие сообщения, системные триггеры и текущие мысли агента,
извлекает из них ключевые векторы и "на лету" делает поиск по Векторной БД.
Найденные факты и выводы инжектятся прямо в системный промпт (блок RELEVANT INFORMATION).
"""

import re
import asyncio
from typing import Dict, Any, List, TYPE_CHECKING

if TYPE_CHECKING:
    from src.l1_databases.vector.management.knowledge import VectorKnowledge
    from src.l1_databases.vector.management.thoughts import VectorThoughts
    from src.l0_state.interfaces.telegram.telethon_state import TelethonState
    from src.l0_state.agent.state import AgentState


class RAGMemories:
    """
    Провайдер контекста, отвечающий за автоматический семантический поиск (RAG).
    Анализирует входящие события и подтягивает релевантные факты и мысли.
    """

    def __init__(
        self,
        vector_knowledge: "VectorKnowledge",
        vector_thoughts: "VectorThoughts",
        telethon_state: "TelethonState",
        agent_state: "AgentState",
        auto_rag_top_k: int = 5,
        auto_rag_max_query_chars: int = 200,
    ) -> None:
        """
        Инициализирует Auto-RAG провайдер.

        Args:
            vector_knowledge: Контроллер базы знаний (факты).
            vector_thoughts: Контроллер базы мыслей (логика).
            telethon_state: Стейт Telegram (для извлечения имен собеседников).
            agent_state: Состояние агента (для получения текущих мыслей).
            auto_rag_top_k: Сколько лучших совпадений брать на один запрос.
            auto_rag_max_query_chars: Лимит символов для одного куска запроса (защита от размытия эмбеддинга).
        """

        self.vector_knowledge = vector_knowledge
        self.vector_thoughts = vector_thoughts
        self.telethon_state = telethon_state
        self.agent_state = agent_state

        self.auto_rag_top_k = auto_rag_top_k
        self.auto_rag_max_query_chars = auto_rag_max_query_chars

        # Глобальный лимит: сколько МАКСИМУМ воспоминаний суммарно отдать в контекст
        self.global_limit = 10

    def _split_into_queries(self, raw_text: str) -> List[str]:
        """
        Дробит длинный текст на короткие запросы (ориентируясь на предложения),
        чтобы избежать семантического размытия вектора.

        Args:
            raw_text: Входящий текст для поиска.

        Returns:
            Список строковых чанков, оптимизированных для Embedding-модели.
        """
        
        text = raw_text.strip()
        if not text:
            return []

        if len(text) <= self.auto_rag_max_query_chars:
            return [text]

        # Бьем по знакам препинания конца предложения
        sentences = re.split(r"(?<=[.!?])\s+", text)
        chunks = []
        current_chunk = ""

        for s in sentences:
            # Если одно гигантское предложение без точек больше лимита - жестко режем его
            if len(s) > self.auto_rag_max_query_chars:
                if current_chunk:
                    chunks.append(current_chunk.strip())
                    current_chunk = ""
                chunks.append(s[: self.auto_rag_max_query_chars])
                continue

            # Собираем кусок до достижения лимита
            if len(current_chunk) + len(s) <= self.auto_rag_max_query_chars:
                current_chunk += s + " "
            else:
                chunks.append(current_chunk.strip())
                current_chunk = s + " "

        if current_chunk:
            chunks.append(current_chunk.strip())

        return chunks

    async def get_context_block(
        self,
        payload: Dict[str, Any],
        missed_events: List[Dict[str, Any]],
        **kwargs: Any,
    ) -> str:
        """
        Мощный RAG поиск по текущим мыслям, действиям и результатам действий агента.

        Args:
            payload: Данные текущего события (сообщения).
            missed_events: Лог фоновых событий.

        Returns:
            Отформатированный блок 'RELEVANT INFORMATION' или пустая строка, если ничего не найдено.
        """

        raw_queries = set()

        # ==================================================================
        # RAG поиск для первого шага ReAct-цикла
        # ==================================================================

        if self.agent_state.current_step == 1:

            sender = payload.get("sender_name")
            if sender and sender.lower() != "unknown":
                raw_queries.add(sender.strip())

            chat_name = payload.get("chat_name")
            if chat_name and chat_name.lower() != "unknown":
                raw_queries.add(chat_name.strip())

            # Ищем сырой текст без визуальных маркеров (для чистоты эмбеддинг-пространства)
            msg = payload.get("raw_text") or payload.get("message", "")
            if len(msg) > 10 or len(msg.split()) > 2:
                raw_queries.add(msg.strip())

            # Берем только ПОСЛЕДНИЙ пропущенный ивент
            if missed_events:
                last_evt = missed_events[-1].get("payload", {})
                match_msg = last_evt.get("raw_text") or last_evt.get("message", "")
                if len(match_msg) > 15 or len(match_msg.split()) > 3:
                    raw_queries.add(match_msg.strip())

            for line in self.telethon_state.last_chats.split("\n"):
                if "UNREAD:" in line:
                    match_name = re.search(r"\]\s+(.+?)\s*\(ID:", line)
                    if match_name:
                        raw_queries.add(match_name.group(1).strip())

        # ==================================================================
        # Промежуточный RAG поиск между шагами ReAct цикла
        # ==================================================================

        else:
            if self.agent_state.last_thoughts:
                raw_queries.add(self.agent_state.last_thoughts)

            for arg in self.agent_state.last_action_args:
                raw_queries.add(arg)

        if not raw_queries:
            return ""

        # Формируем финальный список коротких запросов
        processed_queries = []
        for raw_q in raw_queries:
            processed_queries.extend(self._split_into_queries(raw_q))

        # Сохраняем порядок, но удаляем дубликаты
        unique_processed = list(dict.fromkeys(processed_queries))

        # Лимит запросов
        final_queries = unique_processed[:5]

        tasks = []
        for q in final_queries:
            tasks.append(
                self.vector_knowledge.search_knowledge(query=q, limit=self.auto_rag_top_k)
            )
            tasks.append(
                self.vector_thoughts.search_thoughts(query=q, limit=self.auto_rag_top_k)
            )

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # ==================================================================
        # ОЧИСТКА ОТ ДУБЛЕЙ И ФОРМАТИРОВАНИЕ
        # ==================================================================

        unique_memories = {}

        for res in results:
            if isinstance(res, Exception) or not res.is_success:
                continue

            if "не дал результатов" in res.message or "пуста" in res.message:
                continue

            blocks = res.message.split("\n\n")

            for block in blocks:
                block = block.strip()
                if not block:
                    continue

                match = re.search(r"\[ID: `([^`]+)`\]", block)
                if match:
                    point_id = match.group(1)
                    if point_id not in unique_memories:
                        unique_memories[point_id] = block

        final_blocks = list(unique_memories.values())[: self.global_limit]

        if not final_blocks:
            return ""

        return (
            "## RELEVANT INFORMATION (автоматический RAG-поиск: информация из векторной базы данных) \n"
            + "\n\n".join(final_blocks)
        )
