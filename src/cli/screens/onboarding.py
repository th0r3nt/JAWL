"""
Экран первичной инициализации.

Проводит пользователя через базовый линейный опросник при самом первом запуске JAWL.

Запрашивает имя агента, ключи API, параметры LLM и настройку Swarm-субагентов.

Автоматически формирует `.env` файл и базовые YAML-конфиги.
"""

import shutil
from pathlib import Path

import questionary
from ruamel.yaml import YAML

from src.cli.widgets.ui import (
    clear_screen,
    get_custom_style,
    print_error,
    print_info,
    print_success,
    set_window_title,
)

ROOT_DIR = Path(__file__).resolve().parent.parent.parent.parent
ENV_FILE = ROOT_DIR / ".env"
ENV_EXAMPLE = ROOT_DIR / ".env.example"
SETTINGS_FILE = ROOT_DIR / "config" / "settings.yaml"
SETTINGS_EXAMPLE = ROOT_DIR / "config" / "settings.example.yaml"


def _ensure_base_files_exist() -> bool:
    """Проверяет и создает базовые файлы из шаблонов, если их нет."""
    files_to_check = [
        (ENV_FILE, ENV_EXAMPLE),
        (SETTINGS_FILE, SETTINGS_EXAMPLE),
        (
            ROOT_DIR / "config" / "interfaces.yaml",
            ROOT_DIR / "config" / "interfaces.example.yaml",
        ),
    ]

    for target, example in files_to_check:
        if not target.exists():
            if example.exists():
                shutil.copy2(example, target)
                print_info(f" Создан базовый файл {target.name}")
            else:
                print_error(f"Критическая ошибка: Шаблон {example.name} не найден.")
                return False
    return True


def _update_env_file(key_map: dict) -> None:
    """Обновляет значения в .env файле."""
    try:
        with open(ENV_FILE, "r", encoding="utf-8-sig") as f:
            lines = f.readlines()
    except UnicodeDecodeError:
        with open(ENV_FILE, "r", encoding="cp1251") as f:
            lines = f.readlines()

    new_lines = []
    for line in lines:
        matched = False
        for key, value in key_map.items():
            if line.startswith(f"{key}="):
                new_lines.append(f'{key}="{value}"\n')
                matched = True
                break
        if not matched:
            new_lines.append(line)

    with open(ENV_FILE, "w", encoding="utf-8") as f:
        f.writelines(new_lines)


def _update_settings_yaml(updates: dict) -> None:
    """Обновляет значения в settings.yaml."""
    yaml = YAML()
    yaml.preserve_quotes = True

    try:
        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
            data = yaml.load(f)

        for path_keys, new_val in updates.items():
            target = data
            for k in path_keys[:-1]:
                target = target[k]
            target[path_keys[-1]] = new_val

        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            yaml.dump(data, f)
    except Exception as e:
        print_error(f"Ошибка при сохранении settings.yaml: {e}")


def _is_onboarding_needed() -> bool:
    """Проверяет, нужно ли запускать опросник (если нет LLM_API_KEY_1 или файла .env)."""
    if not ENV_FILE.exists():
        return True

    try:
        with open(ENV_FILE, "r", encoding="utf-8-sig") as f:
            content = f.read()
            # Ищем хотя бы одну заполненную переменную (исключая пустые "")
            if 'LLM_API_KEY_1=""' in content or "LLM_API_KEY_1=\n" in content:
                # Если URL ведет на локалхост, считаем, что всё ок (онбординг не нужен)
                if "127.0.0.1" in content or "localhost" in content or "0.0.0.0" in content:
                    return False
                return True
    except Exception:
        return True

    return False


def run_onboarding_if_needed() -> bool:
    """
    Точка входа. Запускает линейный опросник при первом старте фреймворка.
    Возвращает True, если можно продолжать запуск агента, False - если юзер отменил настройку.
    """

    if not _is_onboarding_needed():
        return True

    set_window_title("JAWL - Первоначальная настройка")
    clear_screen()
    print_info(" Добро пожаловать в JAWL. Похоже, это ваш первый запуск.")
    print_info(" Давайте выполним базовую настройку системы.\n")

    if not _ensure_base_files_exist():
        return False

    style = get_custom_style()

    # 1. Имя агента
    agent_name = questionary.text(
        "\nКак назовем вашего агента? (Оставьте пустым для 'Agent'):", style=style
    ).ask()
    if agent_name is None:
        return False
    agent_name = agent_name.strip() or "Agent"

    # 2. LLM Base URL
    print("\n")
    print_info(" Настройка подключения к языковой модели (LLM).")
    llm_url = questionary.text(
        "Введите Base URL (Например, для локальной модели: 'http://127.0.0.1:11434/v1/').\nОставьте пустым для стандартного OpenAI API:",
        style=style,
    ).ask()
    if llm_url is None:
        return False

    is_local = "127.0.0.1" in llm_url or "localhost" in llm_url or "0.0.0.0" in llm_url

    # 3. LLM API Key
    llm_key = ""
    if not is_local:
        llm_key = questionary.text(
            "Введите ваш LLM API Key (Обязательно для облачных моделей, для локальных - пропустить):", style=style
        ).ask()
        if not llm_key:
            print_error("Для облачных моделей API ключ обязателен. Запуск отменен.")
            return False
    else:
        print_info(" Обнаружен локальный URL. API ключ не требуется.")
        llm_key = "local_dummy_key"

    # 4. Название модели
    main_model = questionary.text(
        "Введите точное название модели для основного агента (Например: 'gemini-3.1-flash-lite', 'claude-4.6-opus', 'qwen3.6-27b'):",
        style=style,
    ).ask() # TODO: Автоматически подтягивать доступные модели для URL, который указал пользователь, и предлагать выбрать из списка
    if not main_model:
        return False

    # 5. Настройка Swarm (Субагенты)
    print("\n")
    print_info("Подсистема Swarm позволяет делегировать сложные задачи фоновым субагентам.")
    enable_swarm = questionary.confirm(
        "Включить систему субагентов (Swarm)?", default=True, style=style
    ).ask()
    if enable_swarm is None:
        return False

    env_updates = {"LLM_API_URL": llm_url.strip(), "LLM_API_KEY_1": llm_key.strip()}
    settings_updates = {
        ("identity", "agent_name"): agent_name,
        ("llm", "main_model"): main_model.strip(),
        ("system", "swarm", "enabled"): enable_swarm,
    }

    if enable_swarm:
        sub_model = questionary.text(
            "Введите название LLM модели для субагентов (Рекомендуется дешевая и быстрая):",
            style=style,
        ).ask()
        if not sub_model:
            return False

        settings_updates[("system", "swarm", "subagent_model")] = sub_model.strip()

        print("\n")
        print_info(
            " Вы можете указать отдельные API ключи для субагентов, чтобы не тратить лимиты основного ключа."
        )
        sub_url = questionary.text(
            "Base URL для субагентов (оставьте пустым, чтобы использовать тот же, что и у основной модели):",
            style=style,
        ).ask()

        sub_key = questionary.text(
            "API Key для субагентов (оставьте пустым, чтобы использовать ключ основной модели):",
            style=style,
        ).ask()

        if sub_url is not None and sub_url.strip():
            env_updates["SUB_LLM_API_URL"] = sub_url.strip()
        if sub_key is not None and sub_key.strip():
            env_updates["SUB_LLM_API_KEY_1"] = sub_key.strip()

    # Сохраняем все данные
    _update_env_file(env_updates)
    _update_settings_yaml(settings_updates)

    print("\n")
    print_success("Первоначальная настройка успешно завершена!")
    print_info(
        " Позже вы сможете изменить эти и другие параметры через 'Мастер настройки' в главном меню."
    )
    return True
