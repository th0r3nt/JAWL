from src.l0_state.interfaces.state import HostTerminalState
from src.l2_interfaces.host.terminal.client import HostTerminalClient

from src.l3_agent.skills.registry import SkillResult, skill
from src.utils.logger import system_logger


class HostTerminalMessages:
    """
    Навыки агента для отправки сообщений в локальный терминал фреймворка.
    """

    def __init__(self, client: HostTerminalClient, state: HostTerminalState, agent_name: str):
        self.client = client
        self.state = state
        self.agent_name = agent_name

    def _update_state(self, message: str):
        """Записывает ответ агента в стейт, чтобы он видел контекст диалога."""

        lines = self.state.messages.split("\n") if self.state.messages else []
        lines.append(f"{self.agent_name}: {message}")

        if len(lines) > self.state.number_of_last_messages:
            lines = lines[-self.state.number_of_last_messages :]

        self.state.messages = "\n".join(lines)

    @skill()
    async def send_to_terminal(self, text: str) -> SkillResult:
        """
        Печатает текст напрямую в графическое окно терминала (чат с админом).
        """

        success = await self.client.send_message(text)

        if success:
            self._update_state(text)
            system_logger.info("Сообщение отправлено в терминал.")
            return SkillResult.ok("Сообщение успешно выведено на экран терминала.")
        else:
            # Даем агенту понять, что окно сейчас в пиве
            return SkillResult.fail(
                "Ошибка: UI-окно терминала сейчас не подключено."
            )
