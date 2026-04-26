from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional, Union

from pyrogram.enums import ParseMode
from pyrogram.types import ReplyParameters

from src.utils._tools import (
    format_size,
    parse_int_or_str,
    truncate_text,
    validate_sandbox_path,
)
from src.utils.dtime import format_datetime
from src.utils.logger import system_logger

from src.l3_agent.skills.registry import SkillResult, skill


class KurigramMessages:
    """
    Навыки агента для прямого взаимодействия с сообщениями (отправка, удаление, редактирование),
    а также скачивание и отправка файлов из песочницы.
    """

    def __init__(self, tg_client: Any):
        self.tg_client = tg_client

    @staticmethod
    def _peer_key(peer: Any) -> tuple[str, int] | None:
        """Build a comparable key for Pyrogram raw Peer/InputPeer objects."""

        for attr in ("user_id", "chat_id", "channel_id"):
            value = getattr(peer, attr, None)
            if value is not None:
                return attr, int(value)
        return None

    @staticmethod
    def _is_mock_value(value: Any) -> bool:
        return type(value).__module__.startswith("unittest.mock")

    @classmethod
    def _instance_attr(cls, obj: Any, name: str, default: Any = None) -> Any:
        if obj is None:
            return default
        value = vars(obj).get(name, default)
        return default if cls._is_mock_value(value) else value

    @classmethod
    def _same_peer(cls, left: Any, right: Any) -> bool:
        return cls._peer_key(left) == cls._peer_key(right)

    @classmethod
    def _same_draft_target(
        cls, update: Any, target_peer: Any, topic_id: Optional[int]
    ) -> bool:
        if not cls._same_peer(getattr(update, "peer", None), target_peer):
            return False

        update_topic_id = cls._topic_id(getattr(update, "top_msg_id", None))
        if topic_id:
            return update_topic_id == int(topic_id)
        return not update_topic_id

    @staticmethod
    def _topic_id(value: Any) -> Optional[int]:
        return value if isinstance(value, int) else None

    @staticmethod
    def _draft_reply_to(topic_id: Optional[int]) -> Any:
        if not topic_id:
            return None

        from pyrogram import raw

        return raw.types.InputReplyToMessage(
            reply_to_msg_id=int(topic_id), top_msg_id=int(topic_id)
        )

    @staticmethod
    def _button_rows(msg: Any) -> list[list[Any]]:
        reply_markup = getattr(msg, "reply_markup", None)
        if reply_markup:
            rows = getattr(reply_markup, "inline_keyboard", None) or getattr(
                reply_markup, "keyboard", None
            )
            if isinstance(rows, list):
                return rows

        rows = getattr(msg, "buttons", None)
        return rows if isinstance(rows, list) else []

    @staticmethod
    def _button_text(button: Any) -> str:
        return str(getattr(button, "text", "") or "")

    @classmethod
    async def _format_pyrogram_message(
        cls, client: Any, chat_id: Union[int, str], msg: Any, timezone: int
    ) -> str:
        sender = getattr(msg, "from_user", None) or getattr(msg, "sender_chat", None)
        if sender:
            first_name = getattr(sender, "first_name", None) or ""
            last_name = getattr(sender, "last_name", None) or ""
            name = " ".join(p for p in (first_name, last_name) if p).strip()
            name = name or getattr(sender, "title", None) or getattr(sender, "username", None)
            sender_id = getattr(sender, "id", None)
            sender_name = f"{name} (ID: {sender_id})" if name and sender_id else name
            sender_name = sender_name or f"Unknown (ID: {sender_id})"
        else:
            sender_name = "Unknown"

        text = getattr(msg, "text", None) or getattr(msg, "caption", None) or ""
        text = truncate_text(text, 1000, "... [Обрезано системой]")

        parts = []
        if getattr(msg, "service", None):
            parts.append("[Системное сообщение]")
        elif getattr(msg, "media", None):
            media_name = str(getattr(msg, "media", "media")).split(".")[-1].lower()
            parts.append(f"[{media_name or 'media'}]")

        if text:
            parts.append(text)

        forward_origin = (
            getattr(msg, "forward_origin", None)
            or cls._instance_attr(msg, "forward_from")
            or cls._instance_attr(msg, "forward_from_chat")
            or cls._instance_attr(msg, "forward_sender_name")
        )
        if forward_origin:
            parts.append("[Переслано]")

        reply = getattr(msg, "reply_to_message", None)
        if reply:
            reply_id = getattr(reply, "id", None)
            reply_sender = getattr(reply, "from_user", None) or getattr(
                reply, "sender_chat", None
            )
            reply_sender_id = getattr(reply_sender, "id", None) if reply_sender else None
            suffix = f" от ID {reply_sender_id}" if reply_sender_id else ""
            parts.append(f"(В ответ на сообщение ID {reply_id}{suffix})")

        rows = cls._button_rows(msg)
        buttons = [cls._button_text(btn) for row in rows for btn in row]
        buttons = [text for text in buttons if text]
        if buttons:
            parts.append(f"[Кнопки: {', '.join(f'[{text}]' for text in buttons)}]")

        final_text = " ".join(parts) or "[Пустое сообщение]"
        msg_date = getattr(msg, "date", None)
        time_str = (
            format_datetime(msg_date, timezone, fmt="%Y-%m-%d %H:%M")
            if msg_date
            else "unknown-date"
        )
        msg_id = getattr(msg, "id", "?")

        return f"[{time_str}] [ID: {msg_id}] {sender_name}: {final_text}"

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
            entity = parse_int_or_str(to_id)

            kwargs = {
                "chat_id": entity,
                "text": text,
                "disable_notification": is_silent,
                "parse_mode": ParseMode.MARKDOWN,
            }

            if reply_to_message_id:
                kwargs["reply_parameters"] = ReplyParameters(
                    message_id=int(reply_to_message_id)
                )
            elif topic_id:
                kwargs["message_thread_id"] = int(topic_id)

            if time_delay:
                delay_sec = max(10, int(time_delay))
                kwargs["schedule_date"] = datetime.now() + timedelta(seconds=delay_sec)

            sent_msg = await client.send_message(**kwargs)

            try:
                await client.read_chat_history(entity)
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
            safe_path = validate_sandbox_path(file_path)

            if not safe_path.is_file():
                return SkillResult.fail(
                    f"Ошибка: Файл не найден или это директория ({safe_path.name})."
                )

            size_str = format_size(safe_path.stat().st_size)
            client = self.tg_client.client()
            entity = parse_int_or_str(chat_id)

            await client.send_document(
                chat_id=entity,
                document=str(safe_path),
                caption=caption,
                parse_mode=ParseMode.MARKDOWN,
            )

            system_logger.info(
                f"[Telegram Kurigram] Файл {safe_path.name} ({size_str}) отправлен в чат {chat_id}"
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
        """Скачивает медиа-вложение из сообщения в Telegram. По умолчанию сохраняет в sandbox/download/."""

        try:
            if "/" not in dest_filename and "\\" not in dest_filename:
                dest_filename = f"download/{dest_filename}"

            safe_path = validate_sandbox_path(dest_filename)
            client = self.tg_client.client()
            entity = parse_int_or_str(chat_id)

            msg = await client.get_messages(
                chat_id=entity, message_ids=int(message_id), replies=0
            )
            if not msg or not getattr(msg, "media", None):
                return SkillResult.fail(
                    "Ошибка: Сообщение не найдено или не содержит медиа-вложений."
                )

            system_logger.info(
                f"[Telegram Kurigram] Скачивание файла из сообщения {message_id}..."
            )

            downloaded_path = await client.download_media(msg, file_name=str(safe_path))

            if not downloaded_path:
                return SkillResult.fail(
                    "Не удалось скачать файл (возможно, формат не поддерживается)."
                )

            downloaded = Path(downloaded_path)
            size_str = format_size(downloaded.stat().st_size)
            system_logger.info(
                f"[Telegram Kurigram] Файл скачан: {downloaded.name} ({size_str})"
            )

            return SkillResult.ok(
                f"Файл успешно скачан и сохранен как: sandbox/{downloaded.name} ({size_str})"
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
                chat_id=parse_int_or_str(to_id),
                from_chat_id=parse_int_or_str(from_id),
                message_ids=int(msg_id),
            )
            system_logger.info(f"[Telegram Kurigram] Пересылка сообщения {msg_id} в {to_id}")
            return SkillResult.ok(f"Сообщение {msg_id} успешно переслано.")

        except Exception as e:
            return SkillResult.fail(f"Ошибка при пересылке сообщения: {e}")

    @skill()
    async def delete_message(self, msg_id: int, chat_id: Union[int, str]) -> SkillResult:
        """Удаляет сообщение (для себя и для всех, если есть права)."""
        try:
            client = self.tg_client.client()
            await client.delete_messages(
                chat_id=parse_int_or_str(chat_id), message_ids=int(msg_id)
            )
            system_logger.info(
                f"[Telegram Kurigram] Сообщение {msg_id} удалено в чате {chat_id}"
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
            await client.edit_message_text(
                chat_id=parse_int_or_str(chat_id),
                message_id=int(msg_id),
                text=new_text,
                parse_mode=ParseMode.MARKDOWN,
            )
            system_logger.info(f"[Telegram Kurigram] Сообщение {msg_id} отредактировано")
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
            entity = parse_int_or_str(chat_id)
            msg = await client.get_messages(
                chat_id=entity, message_ids=int(message_id), replies=0
            )

            rows = self._button_rows(msg) if msg else []
            if not msg or not rows:
                return SkillResult.fail(
                    "Ошибка: Сообщение не найдено или у него нет inline-кнопок."
                )

            target_i, target_j = None, None
            for i, row in enumerate(rows):
                for j, button in enumerate(row):
                    text = self._button_text(button)
                    if text and button_text.lower() in text.lower():
                        target_i, target_j = i, j
                        break
                if target_i is not None:
                    break

            if target_i is None:
                available = [
                    self._button_text(btn)
                    for row in rows
                    for btn in row
                    if self._button_text(btn)
                ]
                return SkillResult.fail(
                    f"Ошибка: Кнопка '{button_text}' не найдена. Доступные: {available}"
                )

            result = await msg.click(target_i, target_j)

            msg_callback = (
                getattr(result, "message", None)
                if (result and getattr(result, "message", None))
                else ""
            )
            system_logger.info(
                f"[Telegram Kurigram] Нажата кнопка '{button_text}' в сообщении {message_id}"
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
            entity = parse_int_or_str(chat_id)

            messages = []
            async for msg in client.search_messages(
                chat_id=entity, query=query, limit=int(limit)
            ):
                formatted = await self._format_pyrogram_message(
                    client=client,
                    chat_id=entity,
                    msg=msg,
                    timezone=self.tg_client.timezone,
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

    @skill()
    async def edit_draft(
        self,
        chat_id: Union[int, str],
        text: str,
        append: bool = True,
        topic_id: Optional[int] = None,
    ) -> SkillResult:
        """
        Сохраняет или обновляет черновик (неотправленное сообщение) в указанном чате.
        Если append=True, добавляет текст к уже существующему черновику (удобно для неспешного сбора лонгридов).
        Для форума можно передать topic_id, чтобы работать с черновиком конкретного топика.
        """
        try:
            from pyrogram.raw import functions

            client = self.tg_client.client()
            chat_key = parse_int_or_str(chat_id)
            target_peer = await client.resolve_peer(chat_key)

            current_text = ""
            if append:
                drafts = await client.invoke(functions.messages.GetAllDrafts())
                for update in getattr(drafts, "updates", []):
                    if not self._same_draft_target(update, target_peer, topic_id):
                        continue

                    draft = getattr(update, "draft", None)
                    current_text = getattr(draft, "message", "") or ""
                    if current_text:
                        break

            final_text = f"{current_text}\n\n{text}".strip() if current_text else text

            save_kwargs = {"peer": target_peer, "message": final_text}
            reply_to = self._draft_reply_to(topic_id)
            if reply_to:
                save_kwargs["reply_to"] = reply_to

            await client.invoke(functions.messages.SaveDraft(**save_kwargs))

            action_type = "дополнен" if current_text else "создан"
            system_logger.info(f"[Telegram Kurigram] Черновик {action_type} в чате {chat_id}")

            return SkillResult.ok(f"Черновик успешно {action_type} в чате {chat_id}.")

        except ValueError:
            return SkillResult.fail("Ошибка: Некорректный ID чата или Username.")
        except Exception as e:
            return SkillResult.fail(f"Ошибка при работе с черновиком: {e}")

    @skill()
    async def delete_draft(
        self, chat_id: Union[int, str], topic_id: Optional[int] = None
    ) -> SkillResult:
        """
        Удаляет черновик (неотправленное сообщение) в указанном чате.
        Для форума можно передать topic_id, чтобы удалить черновик конкретного топика.
        """
        try:
            from pyrogram.raw import functions

            client = self.tg_client.client()
            target_peer = await client.resolve_peer(parse_int_or_str(chat_id))

            save_kwargs = {"peer": target_peer, "message": ""}
            reply_to = self._draft_reply_to(topic_id)
            if reply_to:
                save_kwargs["reply_to"] = reply_to

            await client.invoke(functions.messages.SaveDraft(**save_kwargs))

            system_logger.info(f"[Telegram Kurigram] Черновик удален в чате {chat_id}")
            return SkillResult.ok(f"Черновик успешно удален в чате {chat_id}.")

        except ValueError:
            return SkillResult.fail("Ошибка: Некорректный ID чата или Username.")
        except Exception as e:
            return SkillResult.fail(f"Ошибка при удалении черновика: {e}")
