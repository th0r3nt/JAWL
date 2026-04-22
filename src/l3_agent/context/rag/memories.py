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
        self.auto_rag_top_k = auto_rag_top_k

    async def get_context_block(
        self,
        payload: Dict[str, Any],
        missed_events: List[Dict[str, Any]],
        **kwargs,
    ) -> str:

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

            for event in missed_events:
                evt_payload = event.get("payload", {})

                match_sender = evt_payload.get("sender_name")
                if match_sender and match_sender.lower() != "unknown":
                    queries.add(match_sender.strip())

                match_chat = evt_payload.get("chat_name")
                if match_chat and match_chat.lower() != "unknown":
                    queries.add(match_chat.strip())

                match_msg = evt_payload.get("message", "")
                if len(match_msg) > 15 or len(match_msg.split()) > 3:
                    queries.add(match_msg.strip())

            # Из названий чатов с непрочитанными сообщениями
            for line in self.telethon_state.last_chats.split("\n"):
                if "непр.]" in line:
                    # Извлекаем имя между типом чата и ID: "[User] Name (ID: 123)"
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

            if self.agent_state.last_action_error:
                queries.add(self.agent_state.last_action_error)

            if missed_events:
                last_evt = missed_events[-1]
                match_msg = last_evt.get("payload", {}).get("message", "")
                if match_msg:
                    queries.add(match_msg.strip())

        if not queries:
            return ""

        queries = list(queries)[:20]

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

                # Изящно обрезаем длинный ключ, как ты и просил
                short_q = q[:100] + "..." if len(q) > 100 else q

                source = "Knowledge" if i % 2 == 0 else "Thoughts"
                memory_blocks.append(
                    f"### Найдено по ключу '{short_q}' ({source}):\n{res.message}"
                )

        if not memory_blocks:
            return ""

        return (
            "## RELEVANT INFORMATION (автоматический поиск по базам данных)\n"
            + "\n\n".join(memory_blocks)
        )
