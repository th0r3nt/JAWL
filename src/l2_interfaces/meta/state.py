"""
L0 State for custom components (Meta).
"""

from typing import Optional


class CustomDashboardState:
    """
    Stores custom context blocks (Markdown) for the agent.
    Updated by sandbox events or through skills.
    """

    def __init__(self):
        self.blocks: dict[str, str] = {}

    def update_block(self, name: str, content: Optional[str]) -> None:
        """
        Updates or deletes a Markdown block on the dashboard.
        """

        if content:
            self.blocks[name] = content
        else:
            self.blocks.pop(name, None)

    async def get_context_block(self, **kwargs) -> str:
        """
        Context provider for the prompt builder.
        """

        if not self.blocks:
            return ""

        lines = []
        for name, content in self.blocks.items():
            lines.append(f"### CUSTOM: {name}\n{content}")

        return "\n\n".join(lines)
