"""
L0 State для кастомных компонентов (Meta).
"""


class CustomDashboardState:
    """
    Хранит кастомные блоки контекста (Markdown) для агента.
    Обновляется по событиям из песочницы или через навыки.
    """

    def __init__(self):
        self.blocks: dict[str, str] = {}

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
