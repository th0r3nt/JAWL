"""
Навыки агента для прямой коммуникации с оператором через консоль хост-машины.
"""

from src.l2_interfaces.host.terminal.client import HostTerminalClient
from src.l3_agent.skills.registry import SkillResult, skill


class HostTerminalMessages:
    def __init__(self, client: HostTerminalClient):
        self.client = client

    @skill()
    async def send_message_to_terminal(self, text: str) -> SkillResult:
        """
        Отправляет текстовое сообщение на экран локального терминала (если он открыт).
        Поддерживает Markdown-разметку.

        Args:
            text: Текст ответа или уведомления.
        """

        try:
            await self.client.broadcast_message(text)
            return SkillResult.ok("Сообщение успешно отправлено в терминал.")
        
        except Exception as e:
            return SkillResult.fail(f"Ошибка при отправке в терминал: {e}")

    @skill()
    async def read_terminal_history(self, limit: int = 15) -> SkillResult:
        """
        Возвращает историю последних сообщений из терминала.
        """

        try:
            messages = self.client.state.recent_messages
            if not messages:
                return SkillResult.ok("История терминала пуста.")

            limit = max(1, min(limit, 100))  # Защита от переполнения
            recent = messages[-limit:]

            return SkillResult.ok("История терминала:\n" + "\n".join(recent))
        except Exception as e:
            return SkillResult.fail(f"Ошибка при чтении истории терминала: {e}")
