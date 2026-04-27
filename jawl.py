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
        print("[*] Обнаружено критическое падение во время деплой-сессии")
        print("[*] Агент сломал код к чертям. Инициирован автоматический откат исходников.")

        try:
            # Восстанавливаем оригиналы
            for r, d, files in os.walk(backup_dir):
                for file in files:
                    if file in (".deploy_active", ".newfiles_manifest"):
                        continue
                    b_path = Path(r) / file
                    rel_path = b_path.relative_to(backup_dir)
                    target_path = root_dir / rel_path
                    shutil.copy2(b_path, target_path)

            # Удаляем новые файлы
            manifest = backup_dir / ".newfiles_manifest"
            if manifest.exists():
                with open(manifest, "r", encoding="utf-8") as f:
                    new_files = f.read().splitlines()
                for nf in new_files:
                    if nf:
                        (root_dir / nf).unlink(missing_ok=True)

            # 3. Чистим
            shutil.rmtree(backup_dir, ignore_errors=True)

            # 4. Пишем webhook агенту в песочницу, чтобы он проснулся и понял, что умер
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

    # Страховка от смерти агента
    recover_deploy_crashes(root_dir)

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
                # Проверяем успешность установки
                result = subprocess.run(
                    [str(venv_python), "-m", "pip", "install", "-r", str(req_file)]
                )
                if result.returncode != 0:
                    print("\n[!] Ошибка при первичной установке зависимостей.")
                    print(
                        "[!] Внимательно изучите ошибки pip выше (возможно, версия Python не поддерживается)."
                    )
                    if os.name == "nt":
                        input("Нажмите Enter для выхода...")
                    sys.exit(1)

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
        if os.environ.get("JAWL_RECOVERY_ATTEMPTED") == "1":
            print(
                f"\n[!] Критический сбой: модуль {e.name} так и не найден после переустановки."
            )
            if os.name == "nt":
                input("Нажмите Enter для выхода...")
            sys.exit(1)

        print(f"\n[*] Сбой: отсутствует модуль {e.name}. Похоже, зависимости были повреждены.")
        print("[*] Запуск автоматического восстановления.")
        time.sleep(2)

        # Проверяем код возврата при восстановлении
        result = subprocess.run([sys.executable, "-m", "pip", "install", "-r", str(req_file)])

        if result.returncode != 0:
            print("\n[!] Критическая ошибка: pip не смог восстановить зависимости.")
            print(
                "[!] Изучите логи выше. Возможно, версия Python несовместима с библиотеками."
            )
            if os.name == "nt":
                input("Нажмите Enter для выхода...")
            sys.exit(1)

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

    except Exception:
        import traceback

        print("\n[Критическая ошибка загрузчика]:")
        traceback.print_exc()
        if os.name == "nt":
            input("\nНажмите Enter для выхода.")
        sys.exit(1)
