"""
Интерактивное редактирование YAML конфигураций.

Реализует рекурсивный обход вложенных словарей и списков (CommentedMap/CommentedSeq).
Обеспечивает приведение типов (Type Coercion) на лету и сохраняет оригинальные
комментарии файла.
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
    Универсальный визуальный редактор YAML файлов.
    Поддерживает навигацию вглубь (drilling down) и редактирование примитивов.
    """

    def __init__(self, file_path: Path, title: str = "Редактор конфигурации") -> None:
        """
        Инициализирует редактор.

        Args:
            file_path: Абсолютный путь к целевому .yaml файлу.
            title: Заголовок для отображения в UI.
        """

        self.file_path = file_path
        self.title = title

        self.yaml = YAML()
        self.yaml.preserve_quotes = True

        self.data = self._load()
        # Стек навигации. Например: ["system", "db", "sql"]
        self.current_path: List[Union[str, int]] = []
        self.style = get_custom_style()

    def _load(self) -> Any:
        """
        Безопасно загружает YAML.
        """

        if not self.file_path.exists():
            raise FileNotFoundError(f"Файл не найден: {self.file_path}")
        with open(self.file_path, "r", encoding="utf-8") as f:
            return self.yaml.load(f)

    def _save(self) -> None:
        """
        Сохраняет структуру обратно на диск с сохранением комментариев.
        """

        with open(self.file_path, "w", encoding="utf-8") as f:
            self.yaml.dump(self.data, f)

    def _get_current_node(self) -> Any:
        """
        Возвращает ссылку на текущий уровень вложенности на основе стека навигации.
        """

        node = self.data
        for p in self.current_path:
            node = node[p]
        return node

    def _get_path_string(self) -> str:
        """
        Человекочитаемый путь.
        """

        if not self.current_path:
            return "Корень"
        return " > ".join(str(p) for p in self.current_path)

    def run(self) -> None:
        """
        Главный цикл работы редактора.
        """

        while True:
            draw_header()

            node = self._get_current_node()
            path_str = self._get_path_string()

            prompt_msg = (
                f"{self.title}\n Текущий путь: [{path_str}]\n\n Выберите ключ для изменения:"
            )

            if isinstance(node, dict):
                keep_running = self._handle_dict_view(node, prompt_msg)
            elif isinstance(node, list):
                keep_running = self._handle_list_view(node, prompt_msg)
            else:
                # Fallback, хотя сюда попасть не должны
                keep_running = False

            if not keep_running:
                break

    def _handle_dict_view(self, node: dict, prompt_msg: str) -> bool:
        """
        Отрисовывает меню для словаря (dict/CommentedMap).
        Возвращает False, если пользователь хочет выйти из редактора полностью.
        """
        
        choices = []

        for key, val in node.items():
            if isinstance(val, dict):
                choices.append(questionary.Choice(f" {key}/", key))
            elif isinstance(val, list):
                choices.append(questionary.Choice(f" {key} ({len(val)} элементов)", key))
            elif isinstance(val, bool):
                status = "ON" if val else "OFF"
                choices.append(questionary.Choice(f" {key}: {status}", key))
            else:
                choices.append(questionary.Choice(f" {key}: {val}", key))

        choices.append(questionary.Separator(" "))

        back_label = "❌ Сохранить и выйти" if not self.current_path else "↩ Назад"
        choices.append(questionary.Choice(back_label, "_back_"))

        choice = questionary.select(
            prompt_msg,
            choices=choices,
            style=self.style,
            qmark="",
            instruction="\n (Используйте стрелочки ↑/↓ и Enter)\n",
        ).ask()

        if choice is None or choice == "_back_":
            if not self.current_path:
                return False  # Выход из редактора
            self.current_path.pop()
            return True

        # Если выбрали ключ
        selected_val = node[choice]
        if isinstance(selected_val, (dict, list)):
            self.current_path.append(choice)  # Проваливаемся глубже
        else:
            self._edit_scalar(node, choice, selected_val)

        return True

    def _handle_list_view(self, node: list, prompt_msg: str) -> bool:
        """
        Отрисовывает меню для списка (list/CommentedSeq).
        Поддерживает добавление и удаление примитивных элементов (строк).
        """
        choices = [questionary.Choice(" Добавить элемент", "_add_")]

        if node:
            choices.append(questionary.Choice(" Удалить элемент", "_del_"))
            choices.append(questionary.Separator("--- Текущие элементы ---"))

            for i, val in enumerate(node):
                if isinstance(val, (dict, list)):
                    choices.append(questionary.Choice(f" Элемент [{i}]", i))
                else:
                    choices.append(questionary.Choice(f" [{i}]: {val}", i))

        choices.append(questionary.Separator(" "))
        choices.append(questionary.Choice("↩ Назад", "_back_"))

        choice = questionary.select(
            prompt_msg, choices=choices, style=self.style, qmark="", instruction=""
        ).ask()

        if choice is None or choice == "_back_":
            self.current_path.pop()
            return True

        if choice == "_add_":
            new_val = questionary.text("Введите новое строковое значение:").ask()
            if new_val:
                node.append(new_val)
                self._save()
            return True

        if choice == "_del_":
            del_choices = [
                questionary.Choice(f"[{i}]: {val}", i) for i, val in enumerate(node)
            ]
            del_choices.append(questionary.Choice("Отмена", "_cancel_"))

            to_del = questionary.select(
                "Какой элемент удалить?", choices=del_choices, style=self.style, qmark=""
            ).ask()
            if to_del != "_cancel_" and to_del is not None:
                node.pop(to_del)
                self._save()
            return True

        # Редактирование или проваливание в конкретный элемент списка
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
        Вызывает промпт изменения скалярного значения (bool, int, float, str).
        Сразу применяет Type Coercion и сохраняет файл.
        """

        clear_screen()
        print(
            f" Редактирование: {key}\n Текущее значение: {current_val} ({type(current_val).__name__})\n"
        )

        # Для Boolean инвертируем напрямую, без ввода текста
        if isinstance(current_val, bool):
            parent_node[key] = not current_val
            self._save()
            return

        # Для чисел и строк запрашиваем текстовый ввод
        new_val_str = questionary.text(
            "Новое значение:", default=str(current_val), style=self.style
        ).ask()

        if new_val_str is None:
            return  # Отмена (Ctrl+C)

        try:
            # Type Coercion
            if isinstance(current_val, int):
                new_val = int(new_val_str)
            elif isinstance(current_val, float):
                new_val = float(new_val_str)
            else:
                new_val = new_val_str

            parent_node[key] = new_val
            self._save()
            print_success("Значение успешно обновлено.")

        except ValueError:
            print_error(
                f"Ошибка типа. Ожидается {type(current_val).__name__}. Изменения отменены."
            )
            # Пауза, чтобы юзер успел прочитать ошибку перед перерисовкой экрана
            import time

            time.sleep(2)
