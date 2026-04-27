from src.l2_interfaces.host.terminal.client import HostTerminalClient
from src.l3_agent.skills.registry import SkillResult, skill


class HostTerminalMessages:
    def __init__(self, client: HostTerminalClient):
        self.client = client

    @skill()
    async def send_message_to_terminal(self, text: str) -> SkillResult:
        """
        Отправляет текстовое сообщение в локальный терминал на хост-машине.
        """

        try:
            await self.client.broadcast_message(text)
            return SkillResult.ok("Сообщение успешно отправлено в терминал.")

        except Exception as e:
            return SkillResult.fail(f"Ошибка при отправке в терминал: {e}")
