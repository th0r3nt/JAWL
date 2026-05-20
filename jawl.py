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
import shutil
from pathlib import Path
import json
import uuid

from src import __version__


def is_venv() -> bool:
    """Проверяет, запущен ли скрипт внутри виртуального окружения."""
    return sys.prefix != sys.base_prefix


def recover_deploy_crashes(root_dir: Path):
    """
    Механизм воскрешения: откатывает сломанный код, если процесс умер во время деплоя.
    """
    backup_dir = root_dir / "src" / "utils" / "local" / "data" / "deploy_backup"
    active_flag = backup_dir / ".deploy_active"

    if backup_dir.exists() and active_flag.exists():
        print("[*] Обнаружено критическое падение во время деплой-сессии.")
        print("[*] Агент сломал код к чертям. Инициирован автоматический откат исходников.")

        try:
            for r, d, files in os.walk(backup_dir):
                if "__pycache__" in r:
                    continue
                for file in files:
                    if file in (".deploy_active", ".newfiles_manifest") or file.endswith(
                        ".pyc"
                    ):
                        continue
                    b_path = Path(r) / file
                    rel_path = b_path.relative_to(backup_dir)
                    target_path = root_dir / rel_path

                    target_path.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(b_path, target_path)

            manifest = backup_dir / ".newfiles_manifest"
            if manifest.exists():
                with open(manifest, "r", encoding="utf-8") as f:
                    new_files = f.read().splitlines()
                for nf in new_files:
                    if nf:
                        target = root_dir / nf
                        if target.exists():
                            if target.is_dir():
                                shutil.rmtree(target, ignore_errors=True)
                            else:
                                target.unlink(missing_ok=True)

            shutil.rmtree(backup_dir, ignore_errors=True)

            events_dir = root_dir / "sandbox" / ".jawl_events"
            events_dir.mkdir(parents=True, exist_ok=True)
            evt_id = str(uuid.uuid4())
            data = {
                "message": "Критический сбой. Прошлый код (в сессии деплоя) вызвал фатальное падение. Bootstrapper автоматически откатил исходники. Старайтесь не совершать сэппуку.",
                "payload": {},
            }
            with open(
                events_dir / f"{int(time.time())}_{evt_id}.json", "w", encoding="utf-8"
            ) as f:
                json.dump(data, f, ensure_ascii=False)

            print("[*] Откат успешно завершен. Запуск стабильной версии.")
            time.sleep(2)

        except Exception as e:
            print(f"[!] Ошибка при откате деплоя: {e}")


def setup_and_run() -> None:
    root_dir = Path(__file__).resolve().parent
    venv_dir = root_dir / "venv"
    req_file = root_dir / "requirements.txt"

    recover_deploy_crashes(root_dir)

    # Защита от конфликтов окружения: если скрипт запущен на 3.13,
    # а внутри будет 3.11, переменные окружения могут сломать пути поиска (Segmentation Fault)
    child_env = os.environ.copy()
    child_env.pop("PYTHONPATH", None)
    child_env.pop("PYTHONHOME", None)

    # =========================================================
    # Если мы ВНЕ виртуального окружения (Глобальный Python)
    # =========================================================

    if not is_venv():
        if not venv_dir.exists():
            print("\n[*] JAWL Bootstrapper: Инициализация.")
            print("[*] Создание виртуального окружения (venv).")
            venv.create(venv_dir, with_pip=True)

            venv_python = (
                venv_dir / "Scripts" / "python.exe"
                if os.name == "nt"
                else venv_dir / "bin" / "python"
            )

            if req_file.exists():
                print("[*] Обновление pip.")
                subprocess.run(
                    [str(venv_python), "-m", "pip", "install", "--upgrade", "pip"],
                    stdout=subprocess.DEVNULL,
                    check=False,
                )

                print(
                    "\n[*] Установка зависимостей из requirements.txt.\n"
                )

                # Пытаемся поставить пакеты стандартным способом
                result = subprocess.run(
                    [str(venv_python), "-m", "pip", "install", "-r", str(req_file)],
                    check=False,
                )

                # FALLBACK LOGIC 
                # Аварийное спасение через uv
                if result.returncode != 0:
                    print("\n" + "=" * 60)
                    print(
                        "[!] Ошибка: Не удалось установить зависимости (сборка C++/Rust пакетов)."
                    )
                    print("[i] Вероятно, вы используете новую версию Python (например, 3.13),")
                    print("    для которой еще не выпущены предкомпилированные бинарники.")
                    print("=" * 60 + "\n")

                    answer = (
                        input(
                            "[?] Использовать пакетный менеджер 'uv' для автоматического скачивания \n"
                            "    стабильной версии Python 3.11 и быстрой установки? [y/N]: "
                        )
                        .strip()
                        .lower()
                    )

                    if answer in ("y", "yes", "д", "да"):
                        print("\n[*] Установка uv.")
                        subprocess.run(
                            [sys.executable, "-m", "pip", "install", "uv"], check=True
                        )

                        print("[*] Удаление сломанного окружения.")
                        shutil.rmtree(venv_dir, ignore_errors=True)

                        print("[*] uv: Создание виртуальной среды (Python 3.11).")
                        subprocess.run(
                            [
                                sys.executable,
                                "-m",
                                "uv",
                                "venv",
                                "--python",
                                "3.11",
                                str(venv_dir),
                            ],
                            check=True,
                        )

                        print("[*] uv: Установка зависимостей.")
                        uv_result = subprocess.run(
                            [
                                sys.executable,
                                "-m",
                                "uv",
                                "pip",
                                "install",
                                "--python",
                                str(venv_python),
                                "-r",
                                str(req_file),
                            ],
                            check=False,
                        )

                        if uv_result.returncode != 0:
                            print(
                                "\n[!] Критическая ошибка: uv также не смог установить пакеты."
                            )
                            if os.name == "nt":
                                input("Нажмите Enter для выхода.")
                            sys.exit(1)

                        print("\n[+] Зависимости успешно установлены через uv.")
                    else:
                        print(
                            "\n[!] Установка прервана. Рекомендуется установить Python 3.11 вручную."
                        )
                        if os.name == "nt":
                            input("Нажмите Enter для выхода.")
                        sys.exit(1)

                print("\n\n[*] Установка завершена.\n")

        venv_python = (
            venv_dir / "Scripts" / "python.exe"
            if os.name == "nt"
            else venv_dir / "bin" / "python"
        )

        # Передаем очищенный env в дочерний процесс
        exit_code = subprocess.call(
            [str(venv_python), str(root_dir / "jawl.py")] + sys.argv[1:], env=child_env
        )

        sys.exit(exit_code)

    # =========================================================
    # Если мы ВНУТРИ виртуального окружения
    # =========================================================

    sys.path.append(str(root_dir))

    try:
        from src.cli.menu import main_menu
        from src.cli.screens.logs import logs_screen
        from src.cli.screens.terminal_chat import _open_terminal_chat
        import src.main  # noqa: F401

    except ModuleNotFoundError as e:
        if os.environ.get("JAWL_RECOVERY_ATTEMPTED") == "1":
            print(
                f"\n\n[!] Критический сбой: модуль {e.name} так и не найден после переустановки."
            )
            if os.name == "nt":
                input("Нажмите Enter для выхода.")
            sys.exit(1)

        print(
            f"\n\n[*] Сбой: отсутствует модуль {e.name}. Запуск автоматического восстановления."
        )
        time.sleep(2)

        subprocess.run(
            [sys.executable, "-m", "pip", "install", "--upgrade", "pip"],
            stdout=subprocess.DEVNULL,
            check=False,
        )
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", "-r", str(req_file)], check=False
        )

        if result.returncode != 0:
            print("\n\n[!] Критическая ошибка: pip не смог восстановить зависимости.")
            if os.name == "nt":
                input("Нажмите Enter для выхода.")
            sys.exit(1)

        print("\n\n[*] Зависимости успешно восстановлены. Запуск CLI.")
        time.sleep(1)

        child_env["JAWL_RECOVERY_ATTEMPTED"] = "1"
        exit_code = subprocess.call(
            [sys.executable, str(root_dir / "jawl.py")] + sys.argv[1:], env=child_env
        )
        sys.exit(exit_code)

    log_arg = next((arg for arg in sys.argv if arg.startswith("--logs")), None)

    if log_arg:
        if "-" in log_arg:
            log_type = log_arg.split("-")[-1]
            logs_screen(log_type)
        else:
            logs_screen("main")
    elif "--terminal" in sys.argv:
        _open_terminal_chat()
    elif "--version" in sys.argv:
        print(f"JAWL Framework v{__version__}")
        sys.exit(0)
    else:
        main_menu()


if __name__ == "__main__":
    try:
        setup_and_run()
    except KeyboardInterrupt:
        print("\nОстановка загрузчика.")
        sys.exit(0)
    except Exception:
        import traceback

        print("\n[Критическая ошибка загрузчика]:")
        traceback.print_exc()
        if os.name == "nt":
            input("\nНажмите Enter для выхода.")
        sys.exit(1)
