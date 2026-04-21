"""
Главный скрипт запуска фреймворка JAWL.
Действует как умный бутстраппер: проверяет виртуальное окружение,
устанавливает зависимости и запускает CLI-интерфейс.
"""

import os
import sys
import subprocess
import venv
from pathlib import Path


def is_venv() -> bool:
    """Проверяет, запущен ли скрипт внутри виртуального окружения."""
    return sys.prefix != sys.base_prefix


def setup_and_run() -> None:
    """
    Проверяет зависимости, поднимает venv при необходимости
    и передает управление главному меню.
    """

    root_dir = Path(__file__).resolve().parent
    venv_dir = root_dir / "venv"
    req_file = root_dir / "requirements.txt"

    # Если мы НЕ в виртуальном окружении - создаем его и перезапускаемся
    if not is_venv():
        print("[*] JAWL Bootstrapper: Инициализация окружения.")

        if not venv_dir.exists():
            print("[*] Создание виртуального окружения (venv).")
            venv.create(venv_dir, with_pip=True)

        # Определяем путь к бинарнику python в зависимости от ОС
        if os.name == "nt":
            venv_python = venv_dir / "Scripts" / "python.exe"
        else:
            venv_python = venv_dir / "bin" / "python"

        if req_file.exists():
            print("[*] Проверка и установка зависимостей.")
            # Тихая установка зависимостей
            subprocess.run(
                [str(venv_python), "-m", "pip", "install", "-r", str(req_file), "--quiet"]
            )

        print("[*] Перезапуск внутри изолированного окружения.\n")

        # Перезапускаем этот же скрипт, но уже используя python из venv
        # sys.exit() гарантирует, что текущий (глобальный) процесс умрет
        sys.exit(subprocess.call([str(venv_python), str(root_dir / "jawl.py")] + sys.argv[1:]))

    # Если мы уже в venv - импортируем и запускаем главное меню
    sys.path.append(str(root_dir))

    # Импорт здесь, чтобы не словить ModuleNotFoundError до установки зависимостей
    from src.cli.menu import main_menu

    main_menu()


if __name__ == "__main__":
    try:
        setup_and_run()
    except KeyboardInterrupt:
        print("\nОстановка загрузчика.")
        sys.exit(0)
