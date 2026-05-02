"""
Фасад для системы гибридного поиска (Vector-Graph RAG).

Анализирует входящие сообщения, системные триггеры и текущие мысли агента,
передает их Оркестратору, который на лету делает кросс-поиск по Векторной
и Графовой БД. Найденные факты и связи инжектятся прямо в системный промпт.
"""

import re
from typing import Dict, Any, List, TYPE_CHECKING, Optional

from src.utils.settings import RAGConfig

from src.l3_agent.context.rag.entity_extractor import EntityExtractor
from src.l3_agent.context.rag.search.vector import VectorSearchWrapper
from src.l3_agent.context.rag.search.graph import GraphSearchWrapper
from src.l3_agent.context.rag.orchestrator import GraphRAGOrchestrator

if TYPE_CHECKING:
    from src.l1_databases.vector.management.knowledge import VectorKnowledge
    from src.l1_databases.vector.management.thoughts import VectorThoughts
    from src.l1_databases.vector.embedding import EmbeddingModel
    from src.l1_databases.graph.manager import GraphManager
    from src.l2_interfaces.telegram.telethon.state import TelethonState
    from src.l0_state.agent.state import AgentState


class RAGMemories:
    """
    Провайдер контекста, отвечающий за автоматический гибридный поиск (Vector-Graph RAG).
    """

    def __init__(
        self,
        vector_knowledge: "VectorKnowledge",
        vector_thoughts: "VectorThoughts",
        graph_manager: Optional["GraphManager"],
        embedding_model: "EmbeddingModel",
        telethon_state: "TelethonState",
        agent_state: "AgentState",
        rag_config: RAGConfig,
    ) -> None:

        self.telethon_state = telethon_state
        self.agent_state = agent_state
        self.config = rag_config

        # Инициализация строительных блоков (Передаем выбранный движок)
        self.extractor = EntityExtractor(
            max_query_chars=rag_config.max_query_chars, engine=rag_config.extraction_engine
        )

        self.vector_search = VectorSearchWrapper(
            vector_knowledge=vector_knowledge,
            vector_thoughts=vector_thoughts,
            # top_k для внутренних запросов делаем чуть больше лимита, чтобы было из чего выбирать
            top_k=rag_config.max_vector_blocks + 2,
        )

        # Если GraphDB выключена в настройках - передаем None менеджер (обертка всё равно не упадет)
        self.graph_search = GraphSearchWrapper(
            graph_manager=graph_manager, max_neighbors=10  # Лимит связей за 1 проход
        )

        # Инициализация самого Оркестратора
        self.orchestrator = GraphRAGOrchestrator(
            vector_search=self.vector_search,
            graph_search=self.graph_search,
            extractor=self.extractor,
            embedding_model=embedding_model,
            config=self.config,
        )

    async def get_context_block(
        self,
        payload: Dict[str, Any],
        missed_events: List[Dict[str, Any]],
        **kwargs: Any,
    ) -> str:
        """
        Собирает сырые тексты из текущего контекста и запускает цикл Vector-Graph RAG.

        Args:
            payload: Данные текущего события (сообщения).
            missed_events: Лог фоновых событий.

        Returns:
            Отформатированный блок 'RELEVANT INFORMATION' или пустая строка.
        """

        if not self.config.enabled:
            return ""

        input_texts = set()

        # ==================================================================
        # Сбор текстов для первого шага ReAct-цикла
        # ==================================================================

        if self.agent_state.current_step == 1:
            sender = payload.get("sender_name")
            if sender and sender.lower() != "unknown":
                input_texts.add(sender.strip())

            chat_name = payload.get("chat_name")
            if chat_name and chat_name.lower() != "unknown":
                input_texts.add(chat_name.strip())

            msg = payload.get("raw_text") or payload.get("message", "")
            if len(msg) > 10 or len(msg.split()) > 2:
                input_texts.add(msg.strip())

            # Берем ПОСЛЕДНИЙ пропущенный ивент
            if missed_events:
                last_evt = missed_events[-1].get("payload", {})
                match_msg = last_evt.get("raw_text") or last_evt.get("message", "")
                if len(match_msg) > 15 or len(match_msg.split()) > 3:
                    input_texts.add(match_msg.strip())

            # Достаем имена из активных чатов (UNREAD)
            for line in self.telethon_state.last_chats.split("\n"):
                if "UNREAD:" in line:
                    match_name = re.search(r"\]\s+(.+?)\s*\(ID:", line)
                    if match_name:
                        input_texts.add(match_name.group(1).strip())

        # ==================================================================
        # Сбор текстов между шагами ReAct цикла
        # ==================================================================

        else:
            if self.agent_state.last_thoughts:
                input_texts.add(self.agent_state.last_thoughts)

            for arg in self.agent_state.last_action_args:
                if isinstance(arg, str) and len(arg) > 3:
                    input_texts.add(arg)

        if not input_texts:
            return ""

        # Делегируем всю магию Оркестратору
        return await self.orchestrator.run(list(input_texts))
