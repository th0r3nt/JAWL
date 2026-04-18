from typing import Literal
import shutil
import asyncio

from src.utils.logger import system_logger

from src.l2_interfaces.host.os.client import HostOSClient

from src.l3_agent.skills.registry import SkillResult, skill


class HostOSFiles:
    """
    Навыки агента для работы с файловой системой хоста.
    Учитывают уровень доступа (Madness Level) через Гейткипер (HostOSClient).
    """

    def __init__(self, host_os_client: HostOSClient):
        self.host_os = host_os_client

    @skill()
    async def read_file(
        self, filepath: str, read_from: Literal["head", "tail"] = "head"
    ) -> SkillResult:
        """
        Читает содержимое файла. Имеет встроенную защиту от огромных файлов.
        read_from: 'head' (с начала) или 'tail' (с конца, полезно для логов).
        """
        max_chars = self.host_os.config.file_read_max_chars

        try:
            safe_path = self.host_os.validate_path(filepath, is_write=False)

            if not safe_path.is_file():
                return SkillResult.fail(
                    f"Ошибка: Путь не является файлом или не существует ({filepath})."
                )

            def _read_fast():
                with open(safe_path, "rb") as f:
                    f.seek(0, 2)
                    file_size = f.tell()

                    # Если файл маленький - читаем целиком
                    if file_size <= max_chars:
                        f.seek(0)
                        return f.read().decode("utf-8", errors="replace"), False

                    # Иначе читаем только нужный кусок
                    if read_from == "tail":
                        f.seek(file_size - max_chars)
                        return f.read().decode("utf-8", errors="replace"), True
                    else:
                        f.seek(0)
                        return f.read(max_chars).decode("utf-8", errors="replace"), True

            # Выполняем тяжелый I/O в пуле потоков
            content, is_truncated = await asyncio.to_thread(_read_fast)

            if is_truncated:
                if read_from == "tail":
                    content = (
                        f"...[Файл обрезан с начала. Показаны последние {max_chars} символов]...\n"
                        + content
                    )
                else:
                    content = (
                        content
                        + f"\n...[Файл обрезан с конца. Показаны первые {max_chars} символов]..."
                    )

            system_logger.info(f"[Host OS] Прочитан файл ({read_from}): {safe_path.name}")
            return SkillResult.ok(content)

        except PermissionError as e:
            return SkillResult.fail(str(e))

        except Exception as e:
            return SkillResult.fail(f"Ошибка при чтении файла: {e}")

    @skill()
    async def write_file(
        self, filepath: str, content: str, mode: Literal["w", "a"]
    ) -> SkillResult:
        """Создает или перезаписывает файл. mode: 'w' - перезапись, 'a' - добавление."""

        if mode not in ("w", "a"):
            return SkillResult.fail("Ошибка: Допустимые режимы 'w' или 'a'.")

        try:
            safe_path = self.host_os.validate_path(filepath, is_write=True)

            # Автоматически создаем родительские директории, если агент указал вложенный путь
            safe_path.parent.mkdir(parents=True, exist_ok=True)

            with open(safe_path, mode, encoding="utf-8") as f:
                f.write(content)

            action_type = "Перезаписан" if mode == "w" else "Обновлен"
            system_logger.info(f"[Host OS] {action_type} файл: {safe_path.name}")
            return SkillResult.ok(f"Файл {safe_path.name} успешно сохранен.")

        except PermissionError as e:
            return SkillResult.fail(str(e))

        except Exception as e:
            return SkillResult.fail(f"Ошибка при записи в файл: {e}")

    @skill()
    async def list_directory(self, path: str = ".") -> SkillResult:
        """Аналог команды ls. Показывает содержимое папки."""

        limit = self.host_os.config.file_list_limit

        try:
            safe_path = self.host_os.validate_path(path, is_write=False)

            if not safe_path.is_dir():
                return SkillResult.fail(f"Ошибка: Путь не является директорией ({path}).")

            items = []
            for i, item in enumerate(safe_path.iterdir()):
                if i >= limit:
                    items.append(f"... [Показано {limit} элементов. Остальные скрыты] ...")
                    break

                prefix = "📁" if item.is_dir() else "📄"
                items.append(f"{prefix} {item.name}")

            if not items:
                return SkillResult.ok(f"Директория '{safe_path.name}' пуста.")

            system_logger.info(f"[Host OS] Просмотр директории: {safe_path.name}")
            return SkillResult.ok("\n".join(items))

        except PermissionError as e:
            return SkillResult.fail(str(e))

        except Exception as e:
            return SkillResult.fail(f"Ошибка при чтении директории: {e}")

    @skill()
    async def search_files(self, pattern: str, path: str = ".") -> SkillResult:
        """Поиск файлов по маске (например, '*.py', 'log_*.txt') во вложенных папках."""

        limit = self.host_os.config.file_list_limit

        try:
            safe_path = self.host_os.validate_path(path, is_write=False)

            if not safe_path.is_dir():
                return SkillResult.fail(
                    "Ошибка: Базовый путь для поиска должен быть директорией."
                )

            found = []
            for i, file_path in enumerate(safe_path.rglob(pattern)):
                if i >= limit:
                    found.append(f"... [Лимит поиска: найдено более {limit} совпадений] ...")
                    break

                # Показываем путь относительно стартовой папки для экономии токенов
                rel_path = file_path.relative_to(safe_path)
                found.append(f"- {rel_path}")

            if not found:
                return SkillResult.ok(f"По маске '{pattern}' ничего не найдено.")

            system_logger.info(f"[Host OS] Поиск файлов '{pattern}' в {safe_path.name}")
            return SkillResult.ok("\n".join(found))

        except PermissionError as e:
            return SkillResult.fail(str(e))

        except Exception as e:
            return SkillResult.fail(f"Ошибка при поиске файлов: {e}")

    @skill()
    async def delete_file(self, filepath: str) -> SkillResult:
        """Удаляет указанный файл (не папки)."""
        try:
            safe_path = self.host_os.validate_path(filepath, is_write=True)

            if not safe_path.exists():
                return SkillResult.fail(f"Ошибка: Файл не существует ({filepath}).")
            if not safe_path.is_file():
                return SkillResult.fail(
                    "Ошибка: Это не файл, удаление директорий через этот инструмент запрещено."
                )

            safe_path.unlink()

            system_logger.info(f"[Host OS] Удален файл: {safe_path.name}")
            return SkillResult.ok(f"Файл {safe_path.name} успешно удален.")

        except PermissionError as e:
            return SkillResult.fail(str(e))

        except Exception as e:
            return SkillResult.fail(f"Ошибка при удалении файла: {e}")

    @skill()
    async def delete_directory(self, path: str) -> SkillResult:
        """Удаляет указанную директорию вместе со всем её содержимым."""
        try:
            safe_path = self.host_os.validate_path(path, is_write=True)

            if not safe_path.exists():
                return SkillResult.fail(f"Ошибка: Директория не существует ({path}).")
            if not safe_path.is_dir():
                return SkillResult.fail(
                    "Ошибка: Это не директория. Для удаления файлов используйте delete_file."
                )

            # Защита от экзистенциального кризиса агента: не даем снести корень
            if (
                safe_path == self.host_os.sandbox_dir
                or safe_path == self.host_os.framework_dir
            ):
                return SkillResult.fail(
                    "Ошибка: Отказано в доступе. Запрещено удалять корневую директорию песочницы или фреймворка."
                )

            # Выполняем I/O-операцию в отдельном потоке, чтобы не блокировать event loop
            await asyncio.to_thread(shutil.rmtree, safe_path)

            system_logger.info(f"[Host OS] Удалена директория: {safe_path.name}")
            return SkillResult.ok(
                f"Директория {safe_path.name} и всё её содержимое успешно удалены."
            )

        except PermissionError as e:
            return SkillResult.fail(str(e))

        except Exception as e:
            return SkillResult.fail(f"Ошибка при удалении директории: {e}")

    @skill()
    async def create_directories(self, paths: list[str]) -> SkillResult:
        """
        Создает одну или несколько директорий (папок).
        Поддерживает создание вложенных структур (например, 'project/src/api').
        """

        if not paths:
            return SkillResult.fail("Ошибка: Список путей пуст.")

        created = []
        errors = []

        for path in paths:
            try:
                # Гейткипер проверит права на запись
                safe_path = self.host_os.validate_path(path, is_write=True)

                # Создаем папку вместе со всеми промежуточными
                await asyncio.to_thread(safe_path.mkdir, parents=True, exist_ok=True)
                created.append(safe_path.name)
                
            except PermissionError as e:
                errors.append(f"{path}: {e}")

            except Exception as e:
                errors.append(f"{path}: Ошибка создания ({e})")

        # Формируем итоговый отчет
        if not created and errors:
            return SkillResult.fail("Не удалось создать директории:\n" + "\n".join(errors))

        msg = f"Успешно созданы директории: {', '.join(created)}."
        if errors:
            msg += "\n\nНо возникли ошибки с этими путями:\n" + "\n".join(errors)

        system_logger.info(f"[Host OS] Созданы директории: {', '.join(created)}")
        return SkillResult.ok(msg)