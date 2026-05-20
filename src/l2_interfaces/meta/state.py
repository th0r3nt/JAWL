"""
L0 State для кастомных компонентов (Meta).
"""

from typing import Optional


class CustomDashboardState:
    """
    Хранит кастомные блоки контекста (Markdown) для агента.
    Обновляется по событиям из песочницы или через навыки.
    """

    def __init__(self):
        self.blocks: dict[str, str] = {}

    def update_block(self, name: str, content: Optional[str]) -> None:
        """
        Обновляет или удаляет Markdown-блок на приборной панели.
        """

        if content:
            self.blocks[name] = content
        else:
            self.blocks.pop(name, None)

    async def get_context_block(self, **kwargs) -> str:
        """
        Провайдер контекста для сборщика промптов.
        """
        
        if not self.blocks:
            return ""

        lines = []
        for name, content in self.blocks.items():
            lines.append(f"### CUSTOM: {name}\n{content}")

        return "\n\n".join(lines)
