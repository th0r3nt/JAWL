"""
Host Terminal communication skills.

Allows sending messages directly to the operator's console and reading terminal history.
"""

from src.l2_interfaces.host.terminal.client import HostTerminalClient
from src.l3_agent.skills.registry import SkillResult, skill


class HostTerminalMessages:
    def __init__(self, client: HostTerminalClient):
        self.client = client

    @skill()
    async def send_message_to_terminal(self, text: str) -> SkillResult:
        """
        Sends markdown text to local terminal display.
        """

        try:
            await self.client.broadcast_message(text)
            return SkillResult.ok("True")

        except Exception as e:
            return SkillResult.fail(f"Error sending to terminal: {e}")

    @skill()
    async def read_terminal_history(self, limit: int = 15) -> SkillResult:
        """
        Returns recent terminal message history.
        """

        try:
            messages = self.client.state.recent_messages
            if not messages:
                return SkillResult.ok("Terminal history is empty.")

            limit = max(1, min(limit, 100))  # Protection against overflow
            recent = messages[-limit:]

            return SkillResult.ok("Terminal history:\n" + "\n".join(recent))
        except Exception as e:
            return SkillResult.fail(f"Error reading terminal history: {e}")
