"""
Навыки агента для прямого взаимодействия с сообщениями (Telethon).

Позволяют отправлять текст, прикреплять локальные файлы, скачивать медиавложения,
форвардить, отвечать на inline-кнопки ботов и работать с черновиками (Drafts).
"""

from datetime import timedelta
from typing import Optional, Union

from telethon.tl.functions.messages import SaveDraftRequest

from src.utils._tools import format_size, validate_sandbox_path, parse_int_or_str
from src.utils.logger import system_logger

from src.l2_interfaces.telegram.telethon.client import TelethonClient
from src.l2_interfaces.telegram.telethon.utils._message_parser import TelethonMessageParser

from src.l3_agent.skills.registry import SkillResult, skill


class TelethonMessages:
    """Инструментарий отправки и управления сообщениями."""

    def __init__(self, tg_client: TelethonClient) -> None:
        self.tg_client = tg_client

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
        Отправляет текстовое сообщение.
        Поддерживается Markdown форматирование: **жирный**, __курсив__, ~~зачеркнутый~~, `код`.

        Args:
            to_id: ID или юзернейм получателя/группы.
            text: Текст сообщения.
            reply_to_message_id: Сделать Reply на это сообщение.
            topic_id: ID топика форума.
            is_silent: Отправить без звука.
            time_delay: Отложенная отправка (в секундах, мин 10).
        """

        try:
            client = self.tg_client.client()
            entity = parse_int_or_str(to_id)

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
        """
        Отправляет файл из папки sandbox/ в чат.

        Args:
            chat_id: Кому отправить.
            file_path: Относительный путь к файлу внутри песочницы.
            caption: Текст подписи к файлу.
        """
        try:
            safe_path = validate_sandbox_path(file_path)
            if not safe_path.is_file():
                return SkillResult.fail(f"Ошибка: Файл не найден ({safe_path.name}).")

            size_str = format_size(safe_path.stat().st_size)
            client = self.tg_client.client()
            entity = parse_int_or_str(chat_id)

            await client.send_file(entity, file=str(safe_path), caption=caption)

            system_logger.info(
                f"[Telegram Telethon] Файл {safe_path.name} отправлен в {chat_id}"
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
        """
        Скачивает медиа-вложение (документ, фото, видео) из сообщения Telegram.
        По умолчанию сохраняет в sandbox/download/.

        Args:
            chat_id: Откуда качаем.
            message_id: ID сообщения с файлом.
            dest_filename: Имя для сохранения.
        """
        try:
            if "/" not in dest_filename and "\\" not in dest_filename:
                dest_filename = f"download/{dest_filename}"

            safe_path = validate_sandbox_path(dest_filename)
            client = self.tg_client.client()
            entity = parse_int_or_str(chat_id)

            msg = await client.get_messages(entity, ids=int(message_id))
            if not msg or not msg.media:
                return SkillResult.fail("Ошибка: Сообщение не найдено или не содержит медиа.")

            system_logger.info(
                f"[Telegram Telethon] Скачивание файла из сообщения {message_id}..."
            )

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
                f"Файл успешно скачан и сохранен: sandbox/{safe_path.name} ({size_str})"
            )

        except PermissionError as e:
            return SkillResult.fail(str(e))
        except Exception as e:
            return SkillResult.fail(f"Ошибка при скачивании файла: {e}")

    @skill()
    async def forward_message(
        self, msg_id: int, from_id: Union[int, str], to_id: Union[int, str]
    ) -> SkillResult:
        """
        Пересылает сообщение из одного чата в другой.

        Args:
            msg_id: ID пересылаемого сообщения.
            from_id: ID исходного чата.
            to_id: ID чата назначения.
        """
        try:
            client = self.tg_client.client()
            await client.forward_messages(
                entity=parse_int_or_str(to_id),
                messages=int(msg_id),
                from_peer=parse_int_or_str(from_id),
            )
            return SkillResult.ok(f"Сообщение {msg_id} успешно переслано.")
        except Exception as e:
            return SkillResult.fail(f"Ошибка при пересылке: {e}")

    @skill()
    async def delete_message(self, msg_id: int, chat_id: Union[int, str]) -> SkillResult:
        """
        Безвозвратно удаляет сообщение (для себя и для всех участников чата, если хватает прав).
        """
        try:
            client = self.tg_client.client()
            await client.delete_messages(
                entity=parse_int_or_str(chat_id), message_ids=[int(msg_id)]
            )
            return SkillResult.ok(f"Сообщение {msg_id} успешно удалено.")
        except Exception as e:
            return SkillResult.fail(f"Ошибка при удалении: {e}")

    @skill()
    async def edit_message(
        self, msg_id: int, new_text: str, chat_id: Union[int, str]
    ) -> SkillResult:
        """
        Редактирует текст уже отправленного вашего сообщения.
        """
        try:
            client = self.tg_client.client()
            await client.edit_message(
                entity=parse_int_or_str(chat_id),
                message=int(msg_id),
                text=new_text,
                parse_mode="md",
            )
            return SkillResult.ok(f"Текст сообщения {msg_id} успешно изменен.")
        except Exception as e:
            return SkillResult.fail(f"Ошибка редактирования: {e}")

    @skill()
    async def click_inline_button(
        self, chat_id: Union[int, str], message_id: int, button_text: str
    ) -> SkillResult:
        """
        Нажимает inline-кнопку под сообщением Telegram-бота (ищет по тексту кнопки).

        Args:
            chat_id: ID чата, где находится бот.
            message_id: ID сообщения с кнопками.
            button_text: Частичный или полный текст кнопки (регистр не важен).
        """
        try:
            client = self.tg_client.client()
            msg = await client.get_messages(parse_int_or_str(chat_id), ids=int(message_id))

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

            return SkillResult.ok(
                f"Кнопка нажата. Ответ бота: {msg_callback}"
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
        Выполняет локальный поиск по истории переписки чата (удобно для извлечения старых логов).
        """

        try:
            client = self.tg_client.client()
            entity = parse_int_or_str(chat_id)

            messages = []
            async for msg in client.iter_messages(entity, search=query, limit=limit):
                formatted = await TelethonMessageParser.build_string(
                    client=client,
                    target_entity=entity,
                    msg=msg,
                    timezone=self.tg_client.timezone,
                    truncate_text_flag=True,
                )
                messages.append(formatted)

            if not messages:
                return SkillResult.ok(f"По запросу '{query}' в чате ничего не найдено.")

            messages.reverse()
            return SkillResult.ok(
                f"Результаты поиска по '{query}':\n\n" + "\n\n".join(messages)
            )

        except Exception as e:
            return SkillResult.fail(f"Ошибка при поиске: {e}")

    @skill()
    async def edit_draft(
        self, chat_id: Union[int, str], text: str, append: bool = True
    ) -> SkillResult:
        """
        Обновляет черновик (Draft - неотправленное сообщение) в чате.
        Если append=True, добавляет текст к уже существующему.
        """

        try:
            client = self.tg_client.client()
            target_entity = await client.get_entity(parse_int_or_str(chat_id))

            current_text = ""
            if append:
                drafts = await client.get_drafts()
                for d in drafts:
                    if getattr(d.entity, "id", None) == target_entity.id:
                        current_text = d.text
                        break

            final_text = f"{current_text}\n\n{text}".strip() if current_text else text

            await client(
                SaveDraftRequest(
                    peer=await client.get_input_entity(target_entity), message=final_text
                )
            )

            action_type = "дополнен" if current_text else "создан"
            return SkillResult.ok(f"Черновик успешно {action_type} в чате {chat_id}.")

        except Exception as e:
            return SkillResult.fail(f"Ошибка при работе с черновиком: {e}")

    @skill()
    async def delete_draft(self, chat_id: Union[int, str]) -> SkillResult:
        """Полностью удаляет черновик в указанном чате."""

        try:
            client = self.tg_client.client()
            target_entity = await client.get_entity(parse_int_or_str(chat_id))

            await client(
                SaveDraftRequest(peer=await client.get_input_entity(target_entity), message="")
            )
            return SkillResult.ok(f"Черновик успешно удален в чате {chat_id}.")

        except Exception as e:
            return SkillResult.fail(f"Ошибка при удалении черновика: {e}")
