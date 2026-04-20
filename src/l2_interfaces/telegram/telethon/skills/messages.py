from datetime import timedelta
from typing import Optional, Union
from pathlib import Path

from src.utils._tools import format_size
from src.utils.logger import system_logger

from src.l2_interfaces.telegram.telethon.client import TelethonClient

from src.l3_agent.skills.registry import SkillResult, skill


class TelethonMessages:
    """
    Навыки агента для прямого взаимодействия с сообщениями (отправка, удаление, редактирование),
    а также скачивание и отправка файлов из песочницы.
    """

    def __init__(self, tg_client: TelethonClient):
        self.tg_client = tg_client

    def _parse_entity(self, entity_id: Union[int, str]) -> Union[int, str]:
        try:
            return int(entity_id)
        except ValueError:
            return str(entity_id).strip()

    def _validate_sandbox_path(self, filepath: str) -> Path:
        """Внутренний гейткипер: разрешает работу с файлами строго внутри папки sandbox/."""

        sandbox_dir = (Path.cwd() / "sandbox").resolve()
        sandbox_dir.mkdir(parents=True, exist_ok=True)

        path_str = str(filepath).replace("\\", "/")
        if path_str.startswith("sandbox/"):
            path_str = path_str[8:]

        resolved = (sandbox_dir / path_str).resolve()
        if not resolved.is_relative_to(sandbox_dir):
            raise PermissionError(
                "Доступ запрещен: можно отправлять и скачивать файлы только в пределах папки sandbox/"
            )

        return resolved

    @skill()
    async def send_message(
        self,
        to_id: Union[int, str],
        text: str,
        reply_to_message_id: Optional[int] = None,
        topic_id: Optional[int] = None,
        is_silent: bool = False,
        time_delay: Optional[int] = None,
    ) -> SkillResult:
        """
        Отправляет текстовое сообщение в группу/чат или канал. Важно: to_id может быть как числовым ID, так и юзернеймом.
        Для отправки в конкретный топик форума - использовать аргумент topic_id.
        Поддерживается Markdown форматирование: **жирный**, __курсив__, ~~зачеркнутый~~, ||спойлер||, `код`.
        """
        try:
            client = self.tg_client.client()
            entity = self._parse_entity(to_id)

            # Явно указываем parse_mode, чтобы Telethon 100% считывал разметку
            kwargs = {
                "entity": entity,
                "message": text,
                "silent": is_silent,
                "parse_mode": "md",
            }

            if reply_to_message_id:
                kwargs["reply_to"] = int(reply_to_message_id)
            elif topic_id:
                kwargs["reply_to"] = int(topic_id)

            if time_delay:
                delay_sec = max(10, int(time_delay))
                kwargs["schedule"] = timedelta(seconds=delay_sec)

            sent_msg = await client.send_message(**kwargs)

            try:
                await client.send_read_acknowledge(entity)
            except Exception:
                pass

            schedule_info = f" (отложено на {time_delay} сек)" if time_delay else ""
            msg = f"Сообщение успешно отправлено{schedule_info}. ID: {sent_msg.id}"

            return SkillResult.ok(msg)

        except ValueError:
            return SkillResult.fail("Ошибка: Некорректный ID или Username.")
        except Exception as e:
            system_logger.error(f"Ошибка при отправке сообщения: {e}")
            return SkillResult.fail(f"Ошибка при отправке сообщения: {e}")

    @skill()
    async def send_file(
        self, chat_id: Union[int, str], file_path: str, caption: str = ""
    ) -> SkillResult:
        """Отправляет локальный файл с диска (из папки sandbox/) в указанный чат Telegram."""

        try:
            safe_path = self._validate_sandbox_path(file_path)

            if not safe_path.is_file():
                return SkillResult.fail(
                    f"Ошибка: Файл не найден или это директория ({safe_path.name})."
                )

            size_str = format_size(safe_path.stat().st_size)
            client = self.tg_client.client()
            entity = self._parse_entity(chat_id)

            await client.send_file(entity, file=str(safe_path), caption=caption)

            system_logger.info(
                f"[Telegram Telethon] Файл {safe_path.name} ({size_str}) отправлен в чат {chat_id}"
            )
            return SkillResult.ok(f"Файл {safe_path.name} ({size_str}) успешно отправлен.")

        except PermissionError as e:
            return SkillResult.fail(str(e))
        except Exception as e:
            return SkillResult.fail(f"Ошибка при отправке файла: {e}")

    @skill()
    async def download_file(
        self, chat_id: Union[int, str], message_id: int, dest_filename: str
    ) -> SkillResult:
        """Скачивает медиа-вложение (картинку, гс, документ) из сообщения в Telegram в локальную папку sandbox/."""

        try:
            safe_path = self._validate_sandbox_path(dest_filename)
            client = self.tg_client.client()
            entity = self._parse_entity(chat_id)

            msg = await client.get_messages(entity, ids=int(message_id))
            if not msg or not msg.media:
                return SkillResult.fail(
                    "Ошибка: Сообщение не найдено или не содержит медиа-вложений."
                )

            system_logger.info(
                f"[Telegram Telethon] Скачивание файла из сообщения {message_id}..."
            )

            # Запускаем скачивание напрямую по указанному пути
            downloaded_path = await client.download_media(msg, file=str(safe_path))

            if not downloaded_path:
                return SkillResult.fail(
                    "Не удалось скачать файл (возможно, формат не поддерживается)."
                )

            size_str = format_size(safe_path.stat().st_size)
            system_logger.info(
                f"[Telegram Telethon] Файл скачан: {safe_path.name} ({size_str})"
            )

            return SkillResult.ok(
                f"Файл успешно скачан и сохранен как: sandbox/{safe_path.name} ({size_str})"
            )

        except PermissionError as e:
            return SkillResult.fail(str(e))

        except Exception as e:
            return SkillResult.fail(f"Ошибка при скачивании файла: {e}")

    @skill()
    async def forward_message(
        self, msg_id: int, from_id: Union[int, str], to_id: Union[int, str]
    ) -> SkillResult:
        """Пересылает сообщение из одного чата в другой."""

        try:
            client = self.tg_client.client()
            await client.forward_messages(
                entity=self._parse_entity(to_id),
                messages=int(msg_id),
                from_peer=self._parse_entity(from_id),
            )
            system_logger.info(f"[Telegram Telethon] Пересылка сообщения {msg_id} в {to_id}")
            return SkillResult.ok(f"Сообщение {msg_id} успешно переслано.")

        except Exception as e:
            return SkillResult.fail(f"Ошибка при пересылке сообщения: {e}")

    @skill()
    async def delete_message(self, msg_id: int, chat_id: Union[int, str]) -> SkillResult:
        """Удаляет сообщение (для себя и для всех, если есть права)."""
        try:
            client = self.tg_client.client()
            await client.delete_messages(
                entity=self._parse_entity(chat_id), message_ids=[int(msg_id)]
            )
            system_logger.info(
                f"[Telegram Telethon] Сообщение {msg_id} удалено в чате {chat_id}"
            )
            return SkillResult.ok(f"Сообщение {msg_id} успешно удалено.")

        except Exception as e:
            return SkillResult.fail(f"Ошибка при удалении сообщения: {e}")

    @skill()
    async def edit_message(
        self, msg_id: int, new_text: str, chat_id: Union[int, str]
    ) -> SkillResult:
        """
        Изменяет текст уже отправленного сообщения.
        Поддерживается Markdown форматирование: **жирный**, __курсив__, ~~зачеркнутый~~, ||спойлер||, `код`.
        """

        try:
            client = self.tg_client.client()
            await client.edit_message(
                entity=self._parse_entity(chat_id),
                message=int(msg_id),
                text=new_text,
                parse_mode="md",
            )
            system_logger.info(f"[Telegram Telethon] Сообщение {msg_id} отредактировано")
            return SkillResult.ok(f"Текст сообщения {msg_id} успешно изменен.")

        except Exception as e:
            return SkillResult.fail(f"Ошибка при редактировании сообщения: {e}")

    @skill()
    async def click_inline_button(
        self, chat_id: Union[int, str], message_id: int, button_text: str
    ) -> SkillResult:
        """
        Нажимает inline-кнопку (встроенную под сообщением ботов).
        button_text: частичный или точный текст кнопки.
        """

        try:
            client = self.tg_client.client()
            msg = await client.get_messages(self._parse_entity(chat_id), ids=int(message_id))

            if not msg or not msg.buttons:
                return SkillResult.fail(
                    "Ошибка: Сообщение не найдено или у него нет inline-кнопок."
                )

            target_i, target_j = None, None
            for i, row in enumerate(msg.buttons):
                for j, button in enumerate(row):
                    if button.text and button_text.lower() in button.text.lower():
                        target_i, target_j = i, j
                        break
                if target_i is not None:
                    break

            if target_i is None:
                available = [btn.text for row in msg.buttons for btn in row if btn.text]
                return SkillResult.fail(
                    f"Ошибка: Кнопка '{button_text}' не найдена. Доступные: {available}"
                )

            result = await msg.click(target_i, target_j)

            msg_callback = (
                result.message
                if (result and hasattr(result, "message") and result.message)
                else ""
            )
            system_logger.info(
                f"[Telegram Telethon] Нажата кнопка '{button_text}' в сообщении {message_id}"
            )

            return SkillResult.ok(
                f"Кнопка успешно нажата. Ответ бота: {msg_callback}"
                if msg_callback
                else "Кнопка успешно нажата."
            )

        except ValueError:
            return SkillResult.fail("Ошибка: Некорректный ID чата или сообщения.")

        except Exception as e:
            return SkillResult.fail(f"Ошибка при нажатии кнопки: {e}")

    @skill()
    async def search_messages(
        self, chat_id: Union[int, str], query: str, limit: int = 10
    ) -> SkillResult:
        """
        Ищет сообщения в чате по ключевому слову.
        Рекомендуется для поиска старой информации без необходимости читать весь чат.
        """
        try:
            client = self.tg_client.client()
            entity = self._parse_entity(chat_id)

            from src.l2_interfaces.telegram.telethon._message_parser import (
                TelethonMessageParser,
            )

            messages = []
            # Используем встроенный поиск Telethon
            async for msg in client.iter_messages(entity, search=query, limit=limit):
                formatted = await TelethonMessageParser.build_string(
                    client=client,
                    target_entity=entity,
                    msg=msg,
                    timezone=self.tg_client.timezone,
                    truncate_text=True,
                )
                messages.append(formatted)

            if not messages:
                return SkillResult.ok(
                    f"По запросу '{query}' в чате {chat_id} ничего не найдено."
                )

            # Разворачиваем, чтобы старые были сверху
            messages.reverse()

            return SkillResult.ok(
                f"Результаты поиска по '{query}':\n\n" + "\n\n".join(messages)
            )

        except Exception as e:
            return SkillResult.fail(f"Ошибка при поиске сообщений: {e}")
