from pathlib import Path
from typing import Literal


class PromptBuilder:
    """
    Отвечает за сборку статической части промпта (Характер + Инструкции + Скиллы).
    Динамический контекст (память, время, логи) добавляется отдельно в context/builder.py.
    """

    def __init__(self, prompt_dir: str | Path):
        self.prompt_dir = Path(prompt_dir)
        # Убеждаемся, что папка для кастомных промптов существует
        (self.prompt_dir / "custom").mkdir(parents=True, exist_ok=True)

    def _gather_markdown(self, sub_folder: Literal["personality", "system", "custom"]) -> str:
        """
        Рекурсивно ищет, читает и склеивает все .md файлы в указанной подпапке.
        Игнорирует примеры (.example.md).
        """

        target_dir = self.prompt_dir / sub_folder
        if not target_dir.exists() or not target_dir.is_dir():
            return ""

        valid_files = [
            f for f in target_dir.rglob("*.md") if not f.name.endswith(".example.md")
        ]

        def sort_key(path: Path):
            name = path.name.upper()

            if name in ("SOUL.md", "INSTRUCTIONS.md"):
                return 0, name
            
            elif name in ("EXAMPLES_OF_STYLE.md", "FUNCTION_CALL.md"):
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
        Порядок важен: Характер -> Кастомные промпты агента -> Инструкции.
        """

        personality = self._gather_markdown("personality")
        custom = self._gather_markdown("custom")
        system_rules = self._gather_markdown("system")

        parts = [p for p in (personality, custom, system_rules) if p]
        return "\n\n\n\n".join(parts).strip()
