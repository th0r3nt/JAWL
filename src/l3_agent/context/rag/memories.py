import re
import asyncio
from typing import Dict, Any, List, TYPE_CHECKING

if TYPE_CHECKING:
    from src.l1_databases.vector.management.knowledge import VectorKnowledge
    from src.l1_databases.vector.management.thoughts import VectorThoughts
    from src.l0_state.interfaces.state import TelethonState
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
    ):
        self.vector_knowledge = vector_knowledge
        self.vector_thoughts = vector_thoughts
        self.telethon_state = telethon_state
        self.agent_state = agent_state

        # Лимит для БД (сколько искать по 1 ключу)
        self.auto_rag_top_k = auto_rag_top_k

        # Глобальный лимит: сколько МАКСИМУМ воспоминаний суммарно отдать в контекст
        self.global_limit = 10

    async def get_context_block(
        self,
        payload: Dict[str, Any],
        missed_events: List[Dict[str, Any]],
        **kwargs,
    ) -> str:
        """
        Мощный RAG поиск по текущим мыслям, действиям и результатам действий агента.
        Возвращает отформатированный блок RELEVANT INFORMATION, если нашел связанные данные.
        """

        queries = set()

        # ==================================================================
        # RAG поиск для первого шага ReAct-цикла
        # ==================================================================

        if self.agent_state.current_step == 1:

            sender = payload.get("sender_name")
            if sender and sender.lower() != "unknown":
                queries.add(sender.strip())

            chat_name = payload.get("chat_name")
            if chat_name and chat_name.lower() != "unknown":
                queries.add(chat_name.strip())

            msg = payload.get("message", "")
            if len(msg) > 10 or len(msg.split()) > 2:
                queries.add(msg.strip())

            # Берем только ПОСЛЕДНИЙ пропущенный ивент, чтобы не собирать мусор со всех логов
            if missed_events:
                last_evt = missed_events[-1].get("payload", {})
                match_msg = last_evt.get("message", "")
                if len(match_msg) > 15 or len(match_msg.split()) > 3:
                    queries.add(match_msg.strip())

            # Из названий чатов с непрочитанными сообщениями
            for line in self.telethon_state.last_chats.split("\n"):
                if "непр.]" in line:
                    match_name = re.search(r"\]\s+(.+?)\s*\(ID:", line)
                    if match_name:
                        queries.add(match_name.group(1).strip())

        # ==================================================================
        # Промежуточный RAG поиск между шагами ReAct цикла
        # ==================================================================

        else:
            if self.agent_state.last_thoughts:
                queries.add(self.agent_state.last_thoughts)

            for arg in self.agent_state.last_action_args:
                queries.add(arg)

        if not queries:
            return ""

        # ЖЕСТКИЙ ЛИМИТ ЗАПРОСОВ
        queries = list(queries)[:3]

        tasks = []
        for q in queries:
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

            # Разбиваем ответ скилла на отдельные блоки памяти (каждая память отделена \n\n)
            blocks = res.message.split("\n\n")

            for block in blocks:
                block = block.strip()
                if not block:
                    continue

                # Вытаскиваем ID для дедупликации
                match = re.search(r"\[ID: `([^`]+)`\]", block)
                if match:
                    point_id = match.group(1)
                    # Если такой ID еще не добавляли - сохраняем
                    if point_id not in unique_memories:
                        unique_memories[point_id] = block

        # Обрезаем суммарное количество воспоминаний под глобальный лимит
        final_blocks = list(unique_memories.values())[: self.global_limit]

        if not final_blocks:
            return ""

        return "## RELEVANT INFORMATION (Семантическая память)\n" + "\n\n".join(final_blocks)
