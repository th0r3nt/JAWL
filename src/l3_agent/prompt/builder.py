"""
Сборщик статической части системного промпта.

Отвечает за конкатенацию разрозненных Markdown-файлов (характер, инструкции, примеры)
в единый статичный System Prompt. Динамический контекст (память, время, логи)
добавляется отдельно в модуле 'context/builder.py'.
"""

from pathlib import Path
from typing import Literal


class PromptBuilder:
    """
    Отвечает за сборку статической части промпта (Характер + Инструкции + Скиллы).
    Динамически фильтрует системные инструкции в зависимости от включенных модулей (YAML).
    """

    def __init__(
        self,
        prompt_dir: str | Path,
        drives_enabled: bool = False,
        tasks_enabled: bool = False,
        traits_enabled: bool = False,
        mental_states_enabled: bool = False,
        swarm_enabled: bool = False,
    ) -> None:
        """
        Инициализирует билдер.

        Args:
            prompt_dir: Абсолютный путь к директории 'prompt'.
            drives_enabled: Включен ли модуль внутренних мотиваторов.
            tasks_enabled: Включен ли модуль долгосрочных задач.
            traits_enabled: Включен ли модуль черт характера.
            mental_states_enabled: Включен ли модуль сущностей.
            swarm_enabled: Включена ли система субагентов.
        """
        
        self.prompt_dir = Path(prompt_dir)

        # Убеждаемся, что системные папки существуют
        (self.prompt_dir / "custom").mkdir(parents=True, exist_ok=True)
        (self.prompt_dir / "system" / "optional").mkdir(parents=True, exist_ok=True)

        self.drives_enabled = drives_enabled
        self.tasks_enabled = tasks_enabled
        self.traits_enabled = traits_enabled
        self.mental_states_enabled = mental_states_enabled
        self.swarm_enabled = swarm_enabled

    def _gather_markdown(self, sub_folder: Literal["personality", "system", "custom"]) -> str:
        """
        Рекурсивно ищет, читает и склеивает все .md файлы в указанной подпапке.
        Игнорирует примеры (.example.md) и отключает инструкции для выключенных модулей.

        Args:
            sub_folder: Имя целевой поддиректории.

        Returns:
            Конкатенированная строка содержимого всех валидных Markdown файлов.

        Raises:
            RuntimeError: Если файл промпта невозможно прочитать.
        """

        target_dir = self.prompt_dir / sub_folder
        if not target_dir.exists() or not target_dir.is_dir():
            return ""

        valid_files = [
            f for f in target_dir.rglob("*.md") if not f.name.endswith(".example.md")
        ]

        # Фильтруем системные модули (если они выключены в настройках)
        if not self.drives_enabled:
            valid_files = [f for f in valid_files if f.name.upper() != "DRIVES.md"]

        if not self.tasks_enabled:
            valid_files = [f for f in valid_files if f.name.upper() != "TASKS.md"]

        if not self.traits_enabled:
            valid_files = [f for f in valid_files if f.name.upper() != "PERSONALITY_TRAITS.md"]

        if not self.mental_states_enabled:
            valid_files = [f for f in valid_files if f.name.upper() != "MENTAL_STATES.md"]

        if not self.swarm_enabled:
            valid_files = [f for f in valid_files if f.name.upper() != "SWARM.md"]

        def sort_key(path: Path):
            name = path.name.upper()

            if name in ("SOUL.MD", "INSTRUCTIONS.MD"):
                return 0, name

            elif name in ("EXAMPLES_OF_STYLE.MD", "FUNCTION_CALL.MD"):
                return 2, name

            else:
                return 1, name

        valid_files.sort(key=sort_key)

        parts = []
        for file_path in valid_files:
            try:
                parts.append(file_path.read_text(encoding="utf-8").strip())
            except Exception as e:
                raise RuntimeError(f"Ошибка чтения файла промпта {file_path}: {e}")

        return "\n\n".join(parts)

    def build(self) -> str:
        """
        Собирает итоговый системный промпт.

        Порядок блоков строго регламентирован:
        Характер (Personality) -> Кастомные промпты агента (Custom) -> Инструкции (System).

        Returns:
            Итоговая строка статического промпта для LLM.
        """

        personality = self._gather_markdown("personality")
        custom = self._gather_markdown("custom")
        system_rules = self._gather_markdown("system")

        parts = [p for p in (personality, custom, system_rules) if p]
        return "\n\n\n\n".join(parts).strip()
