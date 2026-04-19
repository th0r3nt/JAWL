import re
import asyncio
from typing import Dict, Any, List, TYPE_CHECKING

if TYPE_CHECKING:
    from src.l1_databases.vector.management.knowledge import VectorKnowledge
    from src.l1_databases.vector.management.thoughts import VectorThoughts
    from src.l0_state.interfaces.state import TelethonState


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
        auto_rag_top_k: int = 5,
    ):
        self.vector_knowledge = vector_knowledge
        self.vector_thoughts = vector_thoughts
        self.telethon_state = telethon_state
        self.auto_rag_top_k = auto_rag_top_k

    async def get_context_block(
        self, payload: Dict[str, Any], missed_events: List[str], **kwargs
    ) -> str:
        """
        Метод-провайдер для ContextRegistry.
        Отдает отформатированный блок для контекста агента.
        """

        queries = set()

        # 1. Из Payload (Имя отправителя и суть сообщения)
        sender = payload.get("sender_name")
        if sender and sender.lower() != "unknown":
            queries.add(sender.strip())

        msg = payload.get("message", "")
        if len(msg) > 10 or len(msg.split()) > 2:
            queries.add(msg.strip())

        # 2. Из логов пропущенных событий
        for event in missed_events:
            match_sender = re.search(r"sender_name=([^,]+)", event)
            if match_sender and match_sender.group(1).lower() != "unknown":
                queries.add(match_sender.group(1).strip())

            match_msg = re.search(r"message=([^,]+)", event)
            if match_msg:
                text = match_msg.group(1).strip()
                if len(text) > 15 or len(text.split()) > 3:
                    queries.add(text)

        # 3. Из названий чатов с непрочитанными сообщениями
        for line in self.telethon_state.last_chats.split("\n"):
            if "[Непрочитанных:" in line:
                match_name = re.search(r"Название:\s*(.+?)\s*\[", line)
                if match_name:
                    queries.add(match_name.group(1).strip())

        if not queries:
            return ""

        # Берем максимум 10 запросов, чтобы не DdoS'ить локальную БД
        queries = list(queries)[:10]

        tasks = []
        for q in queries:
            tasks.append(
                self.vector_knowledge.search_knowledge(query=q, limit=self.auto_rag_top_k)
            )
            tasks.append(
                self.vector_thoughts.search_thoughts(query=q, limit=self.auto_rag_top_k)
            )

        results = await asyncio.gather(*tasks, return_exceptions=True)

        memory_blocks = []
        for i, res in enumerate(results):
            if isinstance(res, Exception):
                continue

            if (
                res.is_success
                and "не дал результатов" not in res.message
                and "пуста" not in res.message
            ):
                q = queries[i // 2]
                source = "Knowledge" if i % 2 == 0 else "Thoughts"
                memory_blocks.append(f"### Найдено по ключу '{q}' ({source}):\n{res.message}")

        if not memory_blocks:
            return ""

        return "## RELEVANT INFORMATION (Автоматический RAG)\n" + "\n\n".join(memory_blocks)
