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
            log_choice = questionary.select(
                "Выберите поток логов для просмотра:",
                choices=[
                    questionary.Separator(" "),
                    questionary.Choice(" Main (всё сразу)", "main"),
                    questionary.Choice(" Agent (мысли и действия главного агента)", "agent"),
                    questionary.Choice(" Swarm (работа субагентов)", "swarm"),
                    questionary.Choice(" ToT (древо стратегий)", "tot"),
                    questionary.Choice(
                        " Subconscious (подсознательные паттерны)", "subconscious"
                    ),
                    questionary.Separator(" "),
                    questionary.Separator("--- Управление ---"),
                    questionary.Choice(" Очистить все логи", "clear"),
                    questionary.Separator(" "),
                    questionary.Choice("↩ Назад", "back"),
                ],
                instruction=" ",
            ).ask()

            if log_choice == "clear":
                from src.cli.screens.logs import LOG_DIR

                if LOG_DIR.exists():
                    for log_file in LOG_DIR.glob("*.log*"):
                        try:
                            # Безопасно очищаем файл не удаляя его, чтобы не сломать открытые дескрипторы логгера
                            with open(log_file, "w", encoding="utf-8") as f:
                                f.truncate(0)
                        except Exception:
                            pass
                print_info(" Все лог-файлы успешно очищены.")
                time.sleep(1.5)
            elif log_choice and log_choice != "back":
                launch_in_new_window(f"--logs-{log_choice}")

        elif result == "setup":
            setup_wizard_screen()

        elif result == "db_manager":
            database_manager_screen()
