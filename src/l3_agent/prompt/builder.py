from pathlib import Path


class PromptBuilder:
    """
    Отвечает за сборку статической части промпта (Характер + Инструкции + Скиллы).
    Динамический контекст (память, время, логи) добавляется отдельно в context/builder.py.
    """

    def __init__(self, prompt_dir: str | Path):
        self.prompt_dir = Path(prompt_dir)

    def _gather_markdown(self, sub_folder: str) -> str:
        """
        Рекурсивно ищет, читает и склеивает все .md файлы в указанной подпапке.
        Игнорирует примеры (.example.md).
        """

        target_dir = self.prompt_dir / sub_folder
        if not target_dir.exists() or not target_dir.is_dir():
            return ""

        parts = []
        # Сортируем для предсказуемого порядка склейки
        for file_path in sorted(target_dir.rglob("*.md")):
            if file_path.name.endswith(".example.md"):
                continue

            try:
                parts.append(file_path.read_text(encoding="utf-8").strip())
            except Exception as e:
                # Если файл битый или нет прав - падаем жестко
                # Без промпта агент сойдет с ума
                raise RuntimeError(f"Ошибка чтения файла промпта {file_path}: {e}")

        return "\n\n".join(parts)

    def build(self) -> str:
        """
        Собирает итоговый системный промпт.
        Порядок важен: Характер -> Инструкции -> Описание доступных функций.
        """

        # Сначала сканируем папку prompt/personality
        personality = self._gather_markdown("personality")
        # Далее - prompt/system
        system_rules = self._gather_markdown("system")

        return (
            f"""
{personality}

{system_rules}
"""
        ).strip()
