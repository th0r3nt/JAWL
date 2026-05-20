"""
Навыки администратора (Telethon).

Позволяют агенту создавать новые каналы, переименовывать чаты, привязывать
группы обсуждений к каналам, управлять топиками (Форумы) и выдавать/забирать
права администратора у других участников.
"""

from typing import Union

from telethon import utils
from telethon.tl.functions.channels import (
    CreateChannelRequest,
    EditTitleRequest,
    UpdateUsernameRequest,
    SetDiscussionGroupRequest,
)
from telethon.tl.functions.channels import EditPhotoRequest as ChannelEditPhotoRequest
from telethon.tl.functions.messages import ExportChatInviteRequest, EditChatTitleRequest
from telethon.tl.functions.messages import EditChatAboutRequest, EditChatPhotoRequest
from telethon.tl.types import InputChatUploadedPhoto, InputPeerChannel, InputPeerChat

from src.utils._tools import validate_sandbox_path, parse_int_or_str
from src.utils.logger import main_logger
from src.l2_interfaces.telegram.telethon.client import TelethonClient
from src.l3_agent.skills.registry import SkillResult, skill

try:
    from telethon.tl.functions.channels import CreateForumTopicRequest
except ImportError:
    CreateForumTopicRequest = None


class TelethonAdmin:
    """Группа навыков для администрирования групп и каналов."""

    def __init__(self, tg_client: TelethonClient) -> None:
        self.tg_client = tg_client

    @skill()
    async def create_channel(
        self, title: str, about: str = "", is_megagroup: bool = False
    ) -> SkillResult:
        """
        Creates new private channel or supergroup.
        """
        try:
            client = self.tg_client.client()
            result = await client(
                CreateChannelRequest(title=title, about=about, megagroup=is_megagroup)
            )

            chat_id = f"-100{result.chats[0].id}"
            chat_type = "Супергруппа" if is_megagroup else "Канал"

            msg = f"{chat_type} '{title}' успешно создан. ID: {chat_id}"
            main_logger.info(f"[Telegram Telethon] {msg}")
            return SkillResult.ok(f"True. ID: {chat_id}")

        except Exception as e:
            return SkillResult.fail(f"Ошибка при создании чата: {e}")

    @skill()
    async def set_channel_username(
        self, chat_id: Union[int, str], username: str
    ) -> SkillResult:
        """
        Sets public username for channel/group. 
        Pass empty string to make private.
        """

        try:
            client = self.tg_client.client()
            entity = await client.get_input_entity(parse_int_or_str(chat_id))

            clean_username = username.strip().lstrip("@")

            await client(UpdateUsernameRequest(channel=entity, username=clean_username))

            if clean_username:
                main_logger.info(
                    f"[Telegram Telethon] Канал {chat_id} стал публичным (@{clean_username})"
                )
                return SkillResult.ok(f"True. URL: t.me/{clean_username}")
            else:
                main_logger.info(f"[Telegram Telethon] Канал {chat_id} стал приватным")
                return SkillResult.ok("True")

        except ValueError:
            return SkillResult.fail("Ошибка: Некорректный ID чата.")
        except Exception as e:
            return SkillResult.fail(f"Ошибка при изменении статуса канала: {e}")

    @skill()
    async def set_discussion_group(
        self, channel_id: Union[int, str], group_id: Union[int, str]
    ) -> SkillResult:
        """
        Links supergroup to channel as discussion group. 
        Pass empty group_id to unlink.
        """

        try:
            client = self.tg_client.client()
            channel_entity = await client.get_input_entity(parse_int_or_str(channel_id))

            if not group_id or str(group_id).strip() == "":
                # Отвязываем группу (передаем пустой InputChannel)
                from telethon.tl.types import InputChannelEmpty

                group_entity = InputChannelEmpty()
            else:
                group_entity = await client.get_input_entity(parse_int_or_str(group_id))

            await client(
                SetDiscussionGroupRequest(broadcast=channel_entity, group=group_entity)
            )

            action_str = "привязана к каналу" if group_id else "отвязана от канала"
            msg = f"Супергруппа успешно {action_str} {channel_id}."
            main_logger.info(f"[Telegram Telethon] {msg}")

            return SkillResult.ok("True")

        except ValueError:
            return SkillResult.fail("Ошибка: Некорректный ID канала или группы.")
        except Exception as e:
            return SkillResult.fail(f"Ошибка при привязке группы обсуждений: {e}")

    @skill()
    async def edit_chat_title(self, chat_id: Union[int, str], new_title: str) -> SkillResult:
        """
        Changes channel/group title.
        """

        try:
            client = self.tg_client.client()
            entity = await client.get_entity(parse_int_or_str(chat_id))

            try:
                await client(EditTitleRequest(channel=entity, title=new_title))
            except Exception:
                await client(EditChatTitleRequest(chat_id=entity.id, title=new_title))

            main_logger.info(
                f"[Telegram Telethon] Название чата {chat_id} изменено на '{new_title}'"
            )
            return SkillResult.ok("True")

        except ValueError:
            return SkillResult.fail("Ошибка: Некорректный ID чата.")
        except Exception as e:
            return SkillResult.fail(f"Ошибка при изменении названия чата: {e}")

    @skill()
    async def edit_chat_description(
        self, chat_id: Union[int, str], new_description: str
    ) -> SkillResult:
        """
        Changes channel/group description (bio).
        """

        try:
            client = self.tg_client.client()
            entity = await client.get_input_entity(parse_int_or_str(chat_id))

            await client(EditChatAboutRequest(peer=entity, about=new_description))

            main_logger.info(f"[Telegram Telethon] Описание чата {chat_id} успешно изменено.")
            return SkillResult.ok("True")
        except ValueError:
            return SkillResult.fail("Ошибка: Некорректный ID чата.")
        except Exception as e:
            return SkillResult.fail(f"Ошибка при изменении описания чата: {e}")

    @skill()
    async def edit_chat_avatar(self, chat_id: Union[int, str], filepath: str) -> SkillResult:
        """
        Sets new chat avatar from sandbox/ filepath.
        """

        try:
            safe_path = validate_sandbox_path(filepath)
            if not safe_path.is_file():
                return SkillResult.fail(f"Ошибка: Файл {safe_path.name} не найден.")

            client = self.tg_client.client()
            entity = await client.get_input_entity(parse_int_or_str(chat_id))

            uploaded_file = await client.upload_file(str(safe_path))
            photo = InputChatUploadedPhoto(file=uploaded_file)

            if isinstance(entity, InputPeerChannel):
                await client(ChannelEditPhotoRequest(channel=entity, photo=photo))
            elif isinstance(entity, InputPeerChat):
                await client(EditChatPhotoRequest(chat_id=entity.chat_id, photo=photo))
            else:
                return SkillResult.fail("Ошибка: Этот тип чата не поддерживает смену аватара.")

            main_logger.info(
                f"[Telegram Telethon] Аватар чата {chat_id} изменен на {safe_path.name}"
            )
            return SkillResult.ok("True")

        except PermissionError as e:
            return SkillResult.fail(str(e))
        except ValueError:
            return SkillResult.fail("Ошибка: Некорректный ID чата.")
        except Exception as e:
            return SkillResult.fail(f"Ошибка при изменении аватара чата: {e}")

    @skill()
    async def create_invite_link(self, chat_id: Union[int, str]) -> SkillResult:
        """
        Generates new invite link for private chat.
        """

        try:
            client = self.tg_client.client()
            entity = await client.get_input_entity(parse_int_or_str(chat_id))

            result = await client(ExportChatInviteRequest(peer=entity))

            return SkillResult.ok(f"Пригласительная ссылка сгенерирована: {result.link}")

        except Exception as e:
            return SkillResult.fail(f"Ошибка при генерации ссылки: {e}")

    @skill()
    async def get_participants(
        self, chat_id: Union[int, str], limit: int = 100
    ) -> SkillResult:
        """
        Fetches participant list of group/channel. 
        Requires admin rights.
        """

        try:
            client = self.tg_client.client()
            entity = await client.get_entity(parse_int_or_str(chat_id))

            participants = []
            async for user in client.iter_participants(entity, limit=limit):
                name = utils.get_display_name(user) or "Unknown"
                bot_tag = " [Bot]" if user.bot else ""
                participants.append(f"- ID: `{user.id}` | Имя: {name}{bot_tag}")

            if not participants:
                return SkillResult.ok("Список участников пуст (или нет прав на его просмотр).")

            return SkillResult.ok(
                f"Участники (последние {limit} чел.):\n" + "\n".join(participants)
            )

        except Exception as e:
            return SkillResult.fail(f"Ошибка при получении участников: {e}")

    @skill()
    async def promote_user(
        self, chat_id: Union[int, str], user_id: Union[int, str], add_admins: bool = False
    ) -> SkillResult:
        """
        Promotes user to administrator. 
        add_admins: if True, grants add-admin rights.
        """

        try:
            client = self.tg_client.client()

            await client.edit_admin(
                entity=parse_int_or_str(chat_id),
                user=parse_int_or_str(user_id),
                is_admin=True,
                change_info=True,
                post_messages=True,
                edit_messages=True,
                delete_messages=True,
                ban_users=True,
                invite_users=True,
                pin_messages=True,
                add_admins=add_admins,
            )

            return SkillResult.ok("True")

        except Exception as e:
            return SkillResult.fail(f"Ошибка при выдаче прав администратора: {e}")

    @skill()
    async def demote_user(
        self, chat_id: Union[int, str], user_id: Union[int, str]
    ) -> SkillResult:
        """
        Demotes administrator to regular user.
        """

        try:
            client = self.tg_client.client()

            await client.edit_admin(
                entity=parse_int_or_str(chat_id),
                user=parse_int_or_str(user_id),
                is_admin=False,
            )

            return SkillResult.ok("True")

        except Exception as e:
            return SkillResult.fail(f"Ошибка при снятии прав администратора: {e}")

    @skill()
    async def pin_message(
        self, chat_id: Union[int, str], message_id: int, notify: bool = True
    ) -> SkillResult:
        """
        Pins specific message in chat.
        """

        try:
            client = self.tg_client.client()
            await client.pin_message(
                entity=parse_int_or_str(chat_id), message=int(message_id), notify=notify
            )

            main_logger.info(
                f"[Telegram Telethon] Сообщение {message_id} закреплено в {chat_id}"
            )
            return SkillResult.ok("True")

        except Exception as e:
            return SkillResult.fail(f"Ошибка при закреплении сообщения: {e}")

    @skill()
    async def unpin_message(self, chat_id: Union[int, str], message_id: int) -> SkillResult:
        """
        Unpins message in chat.
        """

        try:
            client = self.tg_client.client()
            await client.unpin_message(
                entity=parse_int_or_str(chat_id), message=int(message_id)
            )

            main_logger.info(
                f"[Telegram Telethon] Сообщение {message_id} откреплено в {chat_id}"
            )
            return SkillResult.ok("True")

        except Exception as e:
            return SkillResult.fail(f"Ошибка при откреплении сообщения: {e}")

    @skill()
    async def create_topic(self, chat_id: Union[int, str], title: str) -> SkillResult:
        """
        Creates new topic in forum-enabled group.
        """

        if not CreateForumTopicRequest:
            return SkillResult.fail(
                "Ошибка: Версия библиотеки Telethon не поддерживает работу с темами."
            )

        try:
            client = self.tg_client.client()
            entity = await client.get_input_entity(parse_int_or_str(chat_id))

            result = await client(CreateForumTopicRequest(channel=entity, title=title))

            topic_id = None
            for update in result.updates:
                if hasattr(update, "message") and hasattr(update.message, "id"):
                    topic_id = update.message.id
                    break

            if not topic_id:
                return SkillResult.fail(
                    "Топик создан, но не удалось извлечь его ID из ответа."
                )

            msg = f"Топик '{title}' успешно создан. ID топика: {topic_id}"
            main_logger.info(f"[Telegram Telethon] {msg} (чат {chat_id})")
            return SkillResult.ok(f"True. ID: {topic_id}")

        except ValueError:
            return SkillResult.fail("Ошибка: Некорректный ID чата.")

        except Exception as e:
            if "CHAT_NOT_MODIFIED" in str(e) or "not a forum" in str(e).lower():
                return SkillResult.fail(
                    "Ошибка: Этот чат не является форумом (темы не включены)."
                )
            return SkillResult.fail(f"Ошибка при создании топика: {e}")
