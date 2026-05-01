"""
Сборщик системного промпта для субагентов.

Конкатенирует базовые правила системы Swarm, инструкцию к вызову JSON-функций
и узкоспециализированное описание конкретной роли (например, CODER.md) в единый текст.
"""

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.l3_agent.swarm.roles import SubagentRole


class SwarmPromptBuilder:
    """
    Сборщик системного промпта для субагентов.
    Комбинирует специфичную роль, инструкции субагента и общие правила вызова функций.
    """

    def __init__(self, root_dir: Path) -> None:
        """
        Инициализирует пути к файлам промптов роя.

        Args:
            root_dir: Корень проекта JAWL.
        """

        self.swarm_prompt_dir = root_dir / "src" / "l3_agent" / "swarm" / "prompt"
        self.roles_dir = self.swarm_prompt_dir / "roles"

        # Убеждаемся, что директории существуют
        self.roles_dir.mkdir(parents=True, exist_ok=True)

    def build(self, role: "SubagentRole") -> str:
        """
        Собирает итоговый системный промпт для конкретной роли субагента.

        Args:
            role: Объект роли (содержит ссылку на .md файл).

        Returns:
            Конкатенированная строка Markdown с инструкциями.

        Raises:
            FileNotFoundError: Если системные файлы промптов удалены или повреждены.
        """

        # Описание конкретной роли (берем имя файла из объекта)
        role_file = self.roles_dir / role.prompt_file

        if not role_file.exists():
            raise FileNotFoundError(f"Файл роли не найден: {role_file.name}")
        role_prompt = role_file.read_text(encoding="utf-8").strip()

        # Общие системные инструкции
        instructions_file = self.swarm_prompt_dir / "INSTRUCTIONS.md"
        if not instructions_file.exists():
            raise FileNotFoundError("Файл инструкций субагентов (INSTRUCTIONS.md) не найден.")
        instructions_prompt = instructions_file.read_text(encoding="utf-8").strip()

        # Инструкции к вызову функций
        function_call_file = self.swarm_prompt_dir / "FUNCTIONS_CALL.md"
        if not function_call_file.exists():
            raise FileNotFoundError(
                "Файл инструкций к вызову функций для субагентов (FUNCTIONS_CALL.md) не найден."
            )
        function_call_prompt = function_call_file.read_text(encoding="utf-8").strip()

        parts = [role_prompt, instructions_prompt, function_call_prompt]
        return "\n\n\n\n".join(p for p in parts if p).strip()
