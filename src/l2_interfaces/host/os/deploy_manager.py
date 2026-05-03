"""
Менеджер безопасной самомодификации фреймворка (Deploy Sessions).

Реализует механизм Copy-on-Write (CoW). Позволяет агенту изменять собственный
исходный код (Access Level >= 2), защищая систему от фатальных ошибок синтаксиса
посредством прогона тестов и автоматического отката (Rollback).
"""

import sys
import os
import shutil
import asyncio
from pathlib import Path
from typing import Tuple

from src import __version__

from src.utils.logger import system_logger


class HostOSDeployManager:
    """
    Управляет деплой-сессиями, бэкапами (Copy-on-Write) и проверками тестов.
    """

    def __init__(self, framework_dir: Path, max_retries: int = 5) -> None:
        """
        Инициализирует менеджер деплоя.

        Args:
            framework_dir: Корень фреймворка.
            max_retries: Количество попыток пройти тесты до автоматического отката.
        """
        self.framework_dir = framework_dir
        self.backup_dir = framework_dir / "src" / "utils" / "local" / "data" / "deploy_backup"
        self.active_flag = self.backup_dir / ".deploy_active"
        self.manifest_file = self.backup_dir / ".newfiles_manifest"

        self.is_active = False
        self.max_retries = max_retries
        self.retries_left = self.max_retries

        # Восстанавливаем состояние в памяти, если процесс рестартнулся штатно с открытой сессией
        if self.active_flag.exists():
            self.is_active = True

    def start_session(self) -> Tuple[bool, str]:
        """
        Открывает сессию самомодификации.

        Returns:
            Tuple[Успех, Сообщение].
        """
        if self.is_active:
            return False, "Деплой-сессия уже активна."

        self.backup_dir.mkdir(parents=True, exist_ok=True)
        self.active_flag.touch()
        self.is_active = True
        self.retries_left = self.max_retries

        if not self.manifest_file.exists():
            self.manifest_file.touch()

        system_logger.info(
            f"[Deploy] Деплой-сессия успешно инициализирована (JAWL v{__version__})."
        )
        return (
            True,
            f"Деплой-сессия начата. У вас есть {self.max_retries} попытки на прохождение тестов при коммите.",
        )

    def backup_file(self, filepath: Path) -> None:
        """
        Сохраняет оригинальный файл во временную директорию (Copy-on-Write)
        перед его первой перезаписью в рамках сессии.
        Если файл создается с нуля — фиксирует его в манифесте для последующего удаления при откате.

        Args:
            filepath: Абсолютный путь к файлу, который агент собирается изменить.
        """

        if not self.is_active:
            return

        rel_path = filepath.relative_to(self.framework_dir)
        backup_path = self.backup_dir / rel_path

        # Если файл уже бекапился в этой сессии - игнорируем
        if backup_path.exists():
            return

        if filepath.exists():
            if filepath.is_dir():
                # Если это директория (например, при удалении папки целиком), бэкапим все файлы внутри
                for child in filepath.rglob("*"):
                    if child.is_file():
                        self.backup_file(child)
                return

            backup_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(filepath, backup_path)
            system_logger.debug(f"[Deploy] Бэкап файла: {rel_path}")
        else:
            # Файл новый, его раньше не было. Запишем в манифест, чтобы потом удалить при откате.
            with open(self.manifest_file, "a", encoding="utf-8") as f:
                f.write(f"{rel_path}\n")
            system_logger.debug(f"[Deploy] Новый файл добавлен в манифест: {rel_path}")

    async def commit_session(self) -> Tuple[bool, str]:
        """
        Закрывает деплой-сессию и фиксирует изменения.
        Автоматически запускает синтаксический анализатор (compileall) и тесты (pytest).
        При падении тестов списывает одну попытку. Если попытки исчерпаны — вызывает rollback_session().

        Returns:
            Tuple[Успешность коммита, Подробный текстовый отчет или Traceback ошибки].
        """

        if not self.is_active:
            return False, "Нет активной деплой-сессии."

        system_logger.info("[Deploy] Запуск валидации изменений...")

        # 1. Синтаксическая проверка
        proc_syntax = await asyncio.create_subprocess_exec(
            sys.executable,
            "-m",
            "compileall",
            "-q",
            "src/",
            cwd=str(self.framework_dir),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr_syntax = await asyncio.wait_for(proc_syntax.communicate(), timeout=30)

        if proc_syntax.returncode != 0:
            return self._handle_failure(
                f"Синтаксическая ошибка (SyntaxError):\n{stderr_syntax.decode('utf-8', errors='replace')}"
            )

        # 2. Прогон тестов (Pytest)
        proc_tests = await asyncio.create_subprocess_exec(
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "--disable-warnings",
            "tests/",
            cwd=str(self.framework_dir),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout_test, stderr_test = await asyncio.wait_for(
            proc_tests.communicate(), timeout=120
        )

        if proc_tests.returncode != 0:
            out_str = stdout_test.decode("utf-8", errors="replace")
            # Берем только хвост лога, чтобы не убить контекст агента
            err_msg = out_str[-3000:] if len(out_str) > 3000 else out_str
            return self._handle_failure(f"Тесты упали:\n{err_msg}")

        # ЕСЛИ ВСЁ ГУД:
        self._cleanup()
        system_logger.info("[Deploy] Тесты пройдены. Изменения успешно зафиксированы.")
        return (
            True,
            "Тесты пройдены. Код зафиксирован, деплой-сессия закрыта. Необходимо инициировать reboot_system() для применения изменений.",
        )

    def _handle_failure(self, error_report: str) -> Tuple[bool, str]:
        """
        Обрабатывает ошибку тестов, уменьшая количество попыток.
        """

        self.retries_left -= 1

        if self.retries_left > 0:
            system_logger.warning(
                f"[Deploy] Тесты не пройдены. Осталось попыток: {self.retries_left}."
            )
            msg = f"Ошибка деплоя. \n{error_report} \n\nОсталось {self.retries_left} попыток исправить ошибку."
            return False, msg
        else:
            system_logger.error("[Deploy] Попытки исчерпаны. Откат изменений...")
            self.rollback_session()
            msg = f"Ошибка деплоя. \n{error_report} \n\nПопытки исчерпаны. Все изменения в коде фреймворка были автоматически удалены. Деплой-сессия закрыта."
            return False, msg

    def rollback_session(self) -> Tuple[bool, str]:
        """
        Откатывает состояние фреймворка до начала текущей деплой-сессии (Rollback).
        """
        if not self.is_active:
            return False, "Нет активной деплой-сессии."

        # 1. Восстанавливаем оригиналы
        for root, dirs, files in os.walk(self.backup_dir):
            if "__pycache__" in root:
                continue
            for file in files:
                if file in (".deploy_active", ".newfiles_manifest") or file.endswith(".pyc"):
                    continue
                backup_path = Path(root) / file
                rel_path = backup_path.relative_to(self.backup_dir)
                target_path = self.framework_dir / rel_path

                target_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(backup_path, target_path)

        # 2. Удаляем файлы, которых не было до сессии
        if self.manifest_file.exists():
            with open(self.manifest_file, "r", encoding="utf-8") as f:
                new_files = f.read().splitlines()
            for nf in new_files:
                if nf:
                    target = self.framework_dir / nf
                    if target.exists():
                        if target.is_dir():
                            shutil.rmtree(target, ignore_errors=True)
                        else:
                            target.unlink(missing_ok=True)

        self._cleanup()
        system_logger.info("[Deploy] Изменения успешно откачены (Rollback).")
        return (
            True,
            "Откат успешно выполнен. Системные файлы восстановлены до состояния начала сессии.",
        )

    def _cleanup(self) -> None:
        """Удаляет директорию с бэкапами и флаги."""
        shutil.rmtree(self.backup_dir, ignore_errors=True)
        self.is_active = False
