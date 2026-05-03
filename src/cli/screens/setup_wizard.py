"""
Экран мастера настройки.

Предоставляет выбор конфигурационного файла (settings.yaml или interfaces.yaml)
и передает управление универсальному визуальному редактому (YamlEditor).
Оснащен защитой от рассинхрона памяти (запрет редактирования, если агент сейчас работает).
"""

import shutil
from pathlib import Path
from typing import Optional

import questionary

from src.cli.widgets.ui import (
    draw_header,
    get_custom_style,
    print_error,
    print_info,
    set_window_title,
    wait_for_enter,
)
from src.cli.screens.agent_control import _is_agent_running
from src.cli.widgets.yaml_editor import YamlEditor

ROOT_DIR = Path(__file__).resolve().parent.parent.parent.parent
CONFIG_DIR = ROOT_DIR / "config"


def _ensure_yaml_exists(file_name: str) -> Optional[Path]:
    """
    Проверяет наличие файла конфигурации.
    Если он отсутствует, автоматически создает его копию из шаблона (.example.yaml).

    Args:
        file_name: Имя файла (например, 'settings.yaml').

    Returns:
        Path к файлу, если он существует (или был создан), иначе None.
    """

    target_file = CONFIG_DIR / file_name
    example_file = CONFIG_DIR / file_name.replace(".yaml", ".example.yaml")

    if not target_file.exists():
        if example_file.exists():
            shutil.copy2(example_file, target_file)
            print_info(f" Создан базовый файл конфигурации {file_name}")
        else:
            print_error(f"Не найден шаблон файла ({example_file.name}).")
            return None

    return target_file


def setup_wizard_screen() -> None:
    """
    Главный цикл экрана выбора конфигурации.
    Блокирует доступ, если процесс агента активен.
    """

    set_window_title("JAWL - Мастер настройки")

    # Защита от рассинхронизации ОЗУ и Диска
    if _is_agent_running():
        print_error("Ошибка: Нельзя изменять конфигурацию во время работы агента.")
        print_info(
            "Остановите агента в главном меню (чтобы избежать рассинхронизации Pydantic моделей в памяти)."
        )
        wait_for_enter()
        return

    style = get_custom_style()

    while True:
        draw_header()

        choice = questionary.select(
            "Выберите конфигурационный файл для редактирования:",
            choices=[
                questionary.Choice("⚙️ Настройки системы (settings.yaml)", "settings.yaml"),
                questionary.Choice(
                    "🔌 Интерфейсы и доступы (interfaces.yaml)", "interfaces.yaml"
                ),
                questionary.Separator(" "),
                questionary.Choice("❌ Выход в главное меню", "exit"),
            ],
            style=style,
            qmark="",
            instruction="\n (Используйте стрелочки ↑/↓ и Enter)\n",
        ).ask()

        if choice is None or choice == "exit":
            break

        target_path = _ensure_yaml_exists(choice)

        if target_path:
            # Делегируем работу универсальному движку
            editor = YamlEditor(file_path=target_path, title=f"Редактор: {choice}")
            editor.run()
