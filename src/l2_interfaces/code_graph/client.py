"""
Клиент для подключения к интерфейсу Кодовой базы.

Кодовые графы хранят зависимости, описания и помогают разбираться в сложных кодовых базах,
благодаря векторному поиску по связям в детерминированном графе.
"""

from typing import Any
from src.l2_interfaces.code_graph.state import CodeGraphState
from src.l2_interfaces.host.os.client import HostOSClient

class CodeGraphClient:
    """Менеджер интерфейса Code Graph."""

    def __init__(self, state: CodeGraphState, host_os: HostOSClient):
        self.state = state
        self.host_os = host_os
        self.state.is_online = True

    async def get_context_block(self, **kwargs: Any) -> str:
        """Блок для системного промпта агента."""
        if not self.state.is_online:
            return "### CODE GRAPH [OFF]\nИнтерфейс отключен."

        if not self.state.active_indexes:
            return "### CODE GRAPH [ON]\nАктивных графов нет."

        lines = ["Активные графы проектов:"]
        for pid, path in self.state.active_indexes.items():
            lines.append(f"- [ID: `{pid}`] Путь: {path}")

        return "### CODE GRAPH [ON]\n" + "\n".join(lines) + "\nДля навигации необходимо указывать ID проекта в навыках."