"""
Клиент для подключения к интерфейсу Кодовой базы.

Кодовые графы хранят зависимости, описания и помогают разбираться в сложных кодовых базах,
благодаря векторному поиску по связям в детерминированном графе.
"""

from typing import Any
from src.l2_interfaces.code_graph.state import CodeGraphState
from src.l2_interfaces.host.os.client import HostOSClient
from src.utils.settings import CodeGraphConfig


class CodeGraphClient:
    """Менеджер интерфейса Code Graph."""

    def __init__(self, state: CodeGraphState, config: CodeGraphConfig, host_os: HostOSClient):
        self.state = state
        self.config = config
        self.host_os = host_os
        self.state.is_online = True

    async def get_context_block(self, **kwargs: Any) -> str:
        """Блок для системного промпта агента."""
        desc = "Description: Parsing Python directory AST-trees and constructing dependency/relationship graphs for semantic search."
        if not self.state.is_online:
            return f"### CODE GRAPH [OFF]\n{desc}\nThe interface is disabled."

        if not self.state.active_indexes:
            return f"### CODE GRAPH [ON]\n{desc}\nNo active code base graphs were found."

        lines = ["Загруженные архитектурные индексы проектов:"]
        for pid, path in self.state.active_indexes.items():
            # Делаем явный упор на связь ID и Директории
            lines.append(f"* Index ID: '{pid}' -> указывает на директорию: '{path}'")

        return (
            f"### CODE GRAPH [ON]\n{desc}\n"
            "For semantic search and code navigation - use Index ID.\n\n"
            + "\n".join(lines)
        )