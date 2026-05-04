import sys
import time

import questionary

from src.cli.widgets.ui import (
    launch_in_new_window,
    draw_header,
    print_info,
    set_window_title,
    get_custom_style,
)

from src.cli.screens.agent_control import start_agent_screen, stop_agent_screen
from src.cli.screens.setup_wizard import setup_wizard_screen
from src.cli.screens.database_manager import database_manager_screen
from src.cli.screens.terminal_chat import terminal_chat_screen


def main_menu() -> None:
    choices = [
        questionary.Choice("[>] Запустить агента", "start"),
        questionary.Choice("[■] Остановить агента", "stop"),
        questionary.Choice("[@] Чат", "terminal"),
        questionary.Choice("[i] Логи", "logs"),
        questionary.Choice("[*] Мастер настройки", "setup"),
        questionary.Choice("[#] Управление базами данных", "db_manager"),
        questionary.Separator(" "),
        questionary.Choice("[x] Выход", "exit"),
    ]

    while True:
        set_window_title("JAWL - Главное меню")
        draw_header()

        result = questionary.select(
            "Добро пожаловать в JAWL. Выберите действие:",
            choices=choices,
            style=get_custom_style(),
            qmark="",
            instruction="\n (Используйте стрелочки ↑/↓ и Enter)\n",
        ).ask()

        if result is None or result == "exit":
            draw_header()
            print_info(" Отключение. До встречи.")
            time.sleep(1)
            sys.exit(0)

        draw_header()

        if result == "start":
            start_agent_screen()

        elif result == "stop":
            stop_agent_screen()

        elif result == "terminal":
            terminal_chat_screen()

        elif result == "logs":
            launch_in_new_window("--logs")

        elif result == "setup":
            setup_wizard_screen()

        elif result == "db_manager":
            database_manager_screen()
