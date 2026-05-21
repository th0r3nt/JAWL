"""
Main CLI Menu Loop for JAWL.

Provides an interactive console selection for agent controls, chat terminal,
log viewers, configuration wizards, and database managers.
"""

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
        questionary.Choice("[>] Start Agent", "start"),
        questionary.Choice("[■] Stop Agent", "stop"),
        questionary.Choice("[@] Chat", "terminal"),
        questionary.Choice("[i] Logs", "logs"),
        questionary.Choice("[*] Setup Wizard", "setup"),
        questionary.Choice("[#] Database Manager", "db_manager"),
        questionary.Separator(" "),
        questionary.Choice("[x] Exit", "exit"),
    ]

    while True:
        set_window_title("JAWL - Main Menu")
        draw_header()

        result = questionary.select(
            "Welcome to JAWL. Choose an action:",
            choices=choices,
            style=get_custom_style(),
            qmark="",
            instruction="\n Use arrows ↑/↓ and Enter\n",
        ).ask()

        if result is None or result == "exit":
            draw_header()
            print_info(" Shutting down. Goodbye.")
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
                "Select a log stream to view:",
                choices=[
                    questionary.Separator(" "),
                    questionary.Choice(" Main (everything at once)", "main"),
                    questionary.Choice(" Agent (main agent thoughts and actions)", "agent"),
                    questionary.Choice(" Swarm (subagents activity)", "swarm"),
                    questionary.Choice(" ToT (thoughts simulation tree)", "tot"),
                    questionary.Choice(
                        " Subconscious (background cognitive patterns)", "subconscious"
                    ),
                    questionary.Separator(" "),
                    questionary.Separator("--- Controls ---"),
                    questionary.Choice(" Clear all logs", "clear"),
                    questionary.Separator(" "),
                    questionary.Choice("↩ Back", "back"),
                ],
                instruction=" ",
            ).ask()

            if log_choice == "clear":
                from src.cli.screens.logs import LOG_DIR

                if LOG_DIR.exists():
                    for log_file in LOG_DIR.glob("*.log*"):
                        try:
                            # Safely clear the file without deleting to preserve active file descriptors
                            with open(log_file, "w", encoding="utf-8") as f:
                                f.truncate(0)
                        except Exception:
                            pass
                print_info(" All log files cleared successfully.")
                time.sleep(1.5)
            elif log_choice and log_choice != "back":
                launch_in_new_window(f"--logs-{log_choice}")

        elif result == "setup":
            setup_wizard_screen()

        elif result == "db_manager":
            database_manager_screen()
