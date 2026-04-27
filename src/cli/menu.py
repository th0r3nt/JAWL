import sys
import time
import questionary

from src.cli.widgets.ui import (
    draw_header,
    print_info,
    get_custom_style,
    flush_input,
    launch_in_new_window,
)

from src.cli.screens.agent_control import start_agent_screen, stop_agent_screen
from src.cli.screens.setup_wizard import setup_wizard_screen
from src.cli.screens.database_manager import database_manager_screen
from src.cli.screens.terminal_chat import terminal_chat_screen


def main_menu() -> None:
    """Главный бесконечный цикл меню."""

    style = get_custom_style()

    while True:
        draw_header()

        flush_input()

        choice = questionary.select(
            "Добро пожаловать в JAWL. Выберите действие:",
            choices=[
                questionary.Choice("🚀 Запустить агента", "start"),
                questionary.Choice("⏹️ Остановить агента", "stop"),
                questionary.Choice("💻 Чат", "terminal"),
                questionary.Choice("📋 Логи", "logs"),
                questionary.Choice("⚙️ Мастер настройки интерфейсов", "setup"),
                questionary.Choice("🗄️ Управление базами данных", "db_manager"),
                questionary.Separator(" "),
                questionary.Choice("❌ Выход", "exit"),
            ],
            style=style,
            qmark="",
            instruction="\n (Используйте стрелочки ↑/↓ и Enter)\n",
        ).ask()

        if choice is None or choice == "exit":
            print_info(" Отключение. До встречи.")
            time.sleep(2)
            sys.exit(0)

        # Маршрутизация
        if choice == "start":
            start_agent_screen()

        elif choice == "stop":
            stop_agent_screen()

        elif choice == "terminal":
            terminal_chat_screen()

        elif choice == "logs":
            launch_in_new_window("--logs")

        elif choice == "setup":
            setup_wizard_screen()

        elif choice == "db_manager":
            database_manager_screen()
