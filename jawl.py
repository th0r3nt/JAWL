"""
Главный скрипт запуска фреймворка JAWL.
Действует как умный бутстраппер: проверяет виртуальное окружение,
устанавливает зависимости и запускает CLI-интерфейс.
"""

import os
import sys
import subprocess
import time
import venv
from pathlib import Path


def is_venv() -> bool:
    """Проверяет, запущен ли скрипт внутри виртуального окружения."""
    return sys.prefix != sys.base_prefix


def setup_and_run() -> None:
    root_dir = Path(__file__).resolve().parent
    venv_dir = root_dir / "venv"
    req_file = root_dir / "requirements.txt"

    # =========================================================
    # Если мы ВНЕ виртуального окружения (Глобальный Python)
    # =========================================================

    if not is_venv():
        if not venv_dir.exists():
            print("[*] JAWL Bootstrapper: Первичная инициализация.")
            print("[*] Создание виртуального окружения (venv).")
            venv.create(venv_dir, with_pip=True)

            venv_python = (
                venv_dir / "Scripts" / "python.exe"
                if os.name == "nt"
                else venv_dir / "bin" / "python"
            )

            if req_file.exists():
                print(
                    "[*] Установка зависимостей из requirements.txt. Пожалуйста, подождите несколько минут."
                )
                subprocess.run([str(venv_python), "-m", "pip", "install", "-r", str(req_file)])
                print("[*] Установка завершена.\n")

        # Определяем путь к python внутри venv
        venv_python = (
            venv_dir / "Scripts" / "python.exe"
            if os.name == "nt"
            else venv_dir / "bin" / "python"
        )

        # Запускаем этот же скрипт через venv
        exit_code = subprocess.call(
            [str(venv_python), str(root_dir / "jawl.py")] + sys.argv[1:]
        )

        # Если произошел краш на уровне CLI, ставим паузу (чтобы окно не закрылось)
        if exit_code != 0 and os.name == "nt":
            input("\n[!] Процесс завершился с ошибкой. Нажмите Enter для выхода.")

        sys.exit(exit_code)

    # =========================================================
    # Если мы ВНУТРИ виртуального окружения
    # =========================================================

    sys.path.append(str(root_dir))

    # Механизм самовосстановления: если модулей нет, докачиваем их и проактивно стартуем
    try:
        from src.cli.menu import main_menu
    except ModuleNotFoundError as e:
        # Защита от бесконечного цикла, если pip так и не смог поставить модуль
        if os.environ.get("JAWL_RECOVERY_ATTEMPTED") == "1":
            print(
                f"\n[!] Критический сбой: модуль {e.name} так и не найден после переустановки."
            )
            if os.name == "nt":
                input("Нажмите Enter для выхода...")
            sys.exit(1)

        print(f"\n[*] Сбой: отсутствует модуль {e.name}. Похоже, зависимости были повреждены.")
        print("[*] Запуск автоматического восстановления.")
        time.sleep(2)  # Даем юзеру время на чтение

        subprocess.run([sys.executable, "-m", "pip", "install", "-r", str(req_file)])

        print("\n[*] Зависимости успешно восстановлены. Запускаем интерфейс.")
        time.sleep(1)

        # Перезапускаем сами себя (с флагом восстановления), чтобы Python подтянул новые пути
        env = os.environ.copy()
        env["JAWL_RECOVERY_ATTEMPTED"] = "1"
        exit_code = subprocess.call(
            [sys.executable, str(root_dir / "jawl.py")] + sys.argv[1:], env=env
        )
        sys.exit(exit_code)

    # Если всё импортировалось успешно — запускаем меню
    main_menu()


if __name__ == "__main__":
    try:
        setup_and_run()

    except KeyboardInterrupt:
        print("\nОстановка загрузчика.")
        sys.exit(0)

    except Exception as e:
        print(f"\n[Критическая ошибка]: {e}")
        if os.name == "nt":
            input("Нажмите Enter для выхода...")
        sys.exit(1)
