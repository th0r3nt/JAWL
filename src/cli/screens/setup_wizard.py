"""
Setup Wizard CLI Screen.

Allows selecting system configuration files (settings.yaml or interfaces.yaml)
and passes control to the universal interactive YamlEditor.
Protects against memory desyncs by blocking edits when the agent is running.
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
    Validates file presence. Copies template .example.yaml if missing.
    """

    target_file = CONFIG_DIR / file_name
    example_file = CONFIG_DIR / file_name.replace(".yaml", ".example.yaml")

    if not target_file.exists():
        if example_file.exists():
            shutil.copy2(example_file, target_file)
            print_info(f" Created base configuration file {file_name}")
        else:
            print_error(f"Template file not found ({example_file.name}).")
            return None

    return target_file


def setup_wizard_screen() -> None:
    """
    Interactive config file selection screen.
    """

    set_window_title("JAWL - Setup Wizard")

    if _is_agent_running():
        print_error("Error: Cannot change configuration while the agent is running.")
        print_info(
            " Stop the agent from the main menu (to prevent desynchronization of Pydantic models in memory)."
        )
        wait_for_enter()
        return

    style = get_custom_style()

    while True:
        draw_header()

        choice = questionary.select(
            "Select configuration file to edit:",
            choices=[
                questionary.Choice("[*] System Settings (settings.yaml)", "settings.yaml"),
                questionary.Choice(
                    "[*] Interfaces and Access Levels (interfaces.yaml)", "interfaces.yaml"
                ),
                questionary.Separator(" "),
                questionary.Choice("[x] Exit to main menu", "exit"),
            ],
            style=style,
            qmark="",
            instruction="\n Use arrows ↑/↓ and Enter\n",
        ).ask()

        if choice is None or choice == "exit":
            break

        target_path = _ensure_yaml_exists(choice)

        if target_path:
            editor = YamlEditor(file_path=target_path, title=f"Editor: {choice}")
            editor.run()
