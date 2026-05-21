"""
Interactive YAML Configuration Editor.

Recursively traverses deep yaml maps/sequences, preserving comments,
and handles real-time type coercion (bool, int, float, str) on user input.
"""

from pathlib import Path
from typing import Any, List, Union
import questionary
from ruamel.yaml import YAML

from src.cli.widgets.ui import (
    clear_screen,
    draw_header,
    get_custom_style,
    print_error,
    print_success,
)


class YamlEditor:
    """
    Universal visual editor for YAML files.
    Supports deep drilling down navigation and editing of primitive scalars.
    """

    def __init__(self, file_path: Path, title: str = "Configuration Editor") -> None:
        """
        Initializes the editor.

        Args:
            file_path: Absolute physical path to the target .yaml.
            title: Title text for the UI header.
        """

        self.file_path = file_path
        self.title = title

        self.yaml = YAML()
        self.yaml.preserve_quotes = True

        self.data = self._load()
        self.current_path: List[Union[str, int]] = []
        self.style = get_custom_style()

    def _load(self) -> Any:
        """
        Safely loads the YAML map structure.
        """

        if not self.file_path.exists():
            raise FileNotFoundError(f"File not found: {self.file_path}")
        with open(self.file_path, "r", encoding="utf-8") as f:
            return self.yaml.load(f)

    def _save(self) -> None:
        """
        Saves the memory tree back to disk, preserving comments.
        """

        with open(self.file_path, "w", encoding="utf-8") as f:
            self.yaml.dump(self.data, f)

    def _get_current_node(self) -> Any:
        """
        Retrieves reference of the current nested node based on navigation stack.
        """

        node = self.data
        for p in self.current_path:
            node = node[p]
        return node

    def _get_path_string(self) -> str:
        """
        Formats a human-readable path breadcrumb.
        """

        if not self.current_path:
            return "Root"
        return " > ".join(str(p) for p in self.current_path)

    def run(self) -> None:
        """
        Main interactive editor loop.
        """

        while True:
            draw_header()

            node = self._get_current_node()
            path_str = self._get_path_string()

            prompt_msg = (
                f"{self.title}\n Current Path: [{path_str}]\n\n Select a key to modify:"
            )

            if isinstance(node, dict):
                keep_running = self._handle_dict_view(node, prompt_msg)
            elif isinstance(node, list):
                keep_running = self._handle_list_view(node, prompt_msg)
            else:
                keep_running = False

            if not keep_running:
                break

    def _handle_dict_view(self, node: dict, prompt_msg: str) -> bool:
        """
        Renders a dictionary key selection menu.
        """

        choices = []

        for key, val in node.items():
            if isinstance(val, dict):
                choices.append(questionary.Choice(f" {key}/", key))
            elif isinstance(val, list):
                choices.append(questionary.Choice(f" {key} ({len(val)} items)", key))
            elif isinstance(val, bool):
                status = "ON" if val else "OFF"
                choices.append(questionary.Choice(f" {key}: {status}", key))
            else:
                choices.append(questionary.Choice(f" {key}: {val}", key))

        choices.append(questionary.Separator(" "))

        back_label = "[x] Save and Exit" if not self.current_path else "↩ Back"
        choices.append(questionary.Choice(back_label, "_back_"))

        choice = questionary.select(
            prompt_msg,
            choices=choices,
            style=self.style,
            qmark="",
            instruction="\n Use arrows ↑/↓ and Enter\n",
        ).ask()

        if choice is None or choice == "_back_":
            if not self.current_path:
                return False
            self.current_path.pop()
            return True

        selected_val = node[choice]
        if isinstance(selected_val, (dict, list)):
            self.current_path.append(choice)
        else:
            self._edit_scalar(node, choice, selected_val)

        return True

    def _handle_list_view(self, node: list, prompt_msg: str) -> bool:
        """
        Renders a sequence list view. Supporting items insertions/deletion.
        """
        choices = [questionary.Choice(" Add Item", "_add_")]

        if node:
            choices.append(questionary.Choice(" Delete Item", "_del_"))
            choices.append(questionary.Separator("--- Current Items ---"))

            for i, val in enumerate(node):
                if isinstance(val, (dict, list)):
                    choices.append(questionary.Choice(f" Item [{i}]", i))
                else:
                    choices.append(questionary.Choice(f" [{i}]: {val}", i))

        choices.append(questionary.Separator(" "))
        choices.append(questionary.Choice("↩ Back", "_back_"))

        choice = questionary.select(
            prompt_msg, choices=choices, style=self.style, qmark="", instruction=" "
        ).ask()

        if choice is None or choice == "_back_":
            self.current_path.pop()
            return True

        if choice == "_add_":
            new_val = questionary.text("Enter new string value:").ask()
            if new_val:
                node.append(new_val)
                self._save()
            return True

        if choice == "_del_":
            del_choices = [
                questionary.Choice(f"[{i}]: {val}", i) for i, val in enumerate(node)
            ]
            del_choices.append(questionary.Choice("Cancel", "_cancel_"))

            to_del = questionary.select(
                "Which item to delete?", choices=del_choices, style=self.style, qmark=""
            ).ask()
            if to_del != "_cancel_" and to_del is not None:
                node.pop(to_del)
                self._save()
            return True

        selected_val = node[choice]
        if isinstance(selected_val, (dict, list)):
            self.current_path.append(choice)
        else:
            self._edit_scalar(node, choice, selected_val)

        return True

    def _edit_scalar(
        self, parent_node: Union[dict, list], key: Union[str, int], current_val: Any
    ) -> None:
        """
        Prompts user for modifications. Applies immediate type coercion.
        """

        clear_screen()
        print(
            f" Editing: {key}\n Current Value: {current_val} ({type(current_val).__name__})\n"
        )

        if isinstance(current_val, bool):
            parent_node[key] = not current_val
            self._save()
            return

        new_val_str = questionary.text(
            "New Value:", default=str(current_val), style=self.style
        ).ask()

        if new_val_str is None:
            return

        try:
            if isinstance(current_val, int):
                new_val = int(new_val_str)
            elif isinstance(current_val, float):
                new_val = float(new_val_str)
            else:
                new_val = new_val_str

            parent_node[key] = new_val
            self._save()
            print_success("Value successfully updated.")

        except ValueError:
            print_error(f"Type error. Expected {type(current_val).__name__}. Changes aborted.")
            import time

            time.sleep(2)
