"""
Экран настройки интерфейсов (Мастер настройки).
Позволяет пользователю включать и выключать интерфейсы (изменяя interfaces.yaml).
"""

import shutil
from pathlib import Path
from dotenv import dotenv_values
import questionary
from ruamel.yaml import YAML

from src.cli.widgets.ui import console, draw_header, get_custom_style, print_error, print_info

ROOT_DIR = Path(__file__).resolve().parent.parent.parent.parent
CONFIG_FILE = ROOT_DIR / "config" / "interfaces.yaml"
CONFIG_EXAMPLE = ROOT_DIR / "config" / "interfaces.example.yaml"
ENV_FILE = ROOT_DIR / ".env"

yaml = YAML()
yaml.preserve_quotes = True


def _ensure_config_exists() -> bool:
    """Проверяет наличие файла interfaces.yaml, если нет - копирует example."""
    if not CONFIG_FILE.exists():
        if CONFIG_EXAMPLE.exists():
            shutil.copy(CONFIG_EXAMPLE, CONFIG_FILE)
            print_info("Создан базовый файл конфигурации interfaces.yaml")
        else:
            print_error("Не найден файл конфигурации (interfaces.example.yaml).")
            return False
    return True


def _check_api_keys() -> tuple[bool, bool]:
    """
    Проверяет наличие ключей в .env файле.
    Возвращает (telethon_ok, aiogram_ok).
    """

    if not ENV_FILE.exists():
        return False, False

    env_dict = dotenv_values(ENV_FILE, encoding="utf-8-sig")

    telethon_ok = bool(env_dict.get("TELETHON_API_ID")) and bool(
        env_dict.get("TELETHON_API_HASH")
    )
    aiogram_ok = bool(env_dict.get("AIOGRAM_BOT_TOKEN"))

    return telethon_ok, aiogram_ok


def _load_yaml() -> dict:
    """Загружает YAML файл как словарь (сохраняя структуру ruamel)."""
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        return yaml.load(f)


def _save_yaml(data: dict) -> None:
    """Сохраняет словарь обратно в YAML файл."""
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        yaml.dump(data, f)


def _toggle_interface(data: dict, path_keys: list[str]) -> None:
    """Инвертирует значение флага enabled по вложенному пути. Создает ключи, если их нет."""
    target = data
    for key in path_keys[:-1]:
        if key not in target:
            target[key] = {}
        target = target[key]

    # Если самого ключа 'enabled' не было, считаем его False и инвертируем
    current_value = target.get(path_keys[-1], False)
    target[path_keys[-1]] = not current_value


def setup_wizard_screen() -> None:
    """Главный цикл экрана Мастера настройки."""
    if not _ensure_config_exists():
        console.print("\n[dim]Нажмите Enter для возврата.[/dim]")
        input()
        return

    style = get_custom_style()

    # Карта маппинга: Title -> путь в YAML-структуре
    # Это позволяет легко расширять меню, не переписывая логику
    interface_map = {
        "Host OS": ["host", "os", "enabled"],
        "Telegram Telethon": ["telegram", "telethon", "enabled"],
        "Telegram Aiogram": ["telegram", "aiogram", "enabled"],
        "GitHub": ["github", "enabled"],
        "Email": ["email", "enabled"],
        "Web Search": ["web", "search", "enabled"],
        "Web HTTP": ["web", "http", "enabled"],
        "Web Browser": ["web", "browser", "enabled"],
        "Meta": ["meta", "enabled"],
        "Multimodality": ["multimodality", "enabled"],
        "Calendar": ["calendar", "enabled"],
    }

    while True:
        draw_header()
        data = _load_yaml()

        # Формируем динамический список кнопок
        choices = []
        for name, path_keys in interface_map.items():
            # Достаем текущее значение
            target = data
            for key in path_keys:
                target = target.get(key, {})

            is_enabled = bool(target)
            status_str = "[ON] " if is_enabled else "[OFF]"

            # Выравниваем название интерфейса (до 18 символов), чтобы статусы шли в ровную колонку
            formatted_name = f"{name:<18} {status_str}"
            choices.append(questionary.Choice(formatted_name, name))

        choices.append(questionary.Separator())
        choices.append(questionary.Choice("❌ Выход в главное меню", "exit"))

        choice = questionary.select(
            "Выберите интерфейс, нажмите Enter и измените значение:\n",
            choices=choices,
            style=style,
            instruction="(Стрелочки ↑/↓ для навигации)\n",
        ).ask()

        if choice is None or choice == "exit":
            break

        # Если выбрали интерфейс - инвертируем его флаг и сохраняем
        path_to_toggle = interface_map[choice]
        _toggle_interface(data, path_to_toggle)
        _save_yaml(data)
