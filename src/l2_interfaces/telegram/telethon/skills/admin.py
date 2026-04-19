from typing import Union

from telethon import utils
from telethon.tl.functions.channels import CreateChannelRequest, EditTitleRequest
from telethon.tl.functions.messages import ExportChatInviteRequest, EditChatTitleRequest

from src.utils.logger import system_logger
from src.l2_interfaces.telegram.telethon.client import TelethonClient
from src.l3_agent.skills.registry import SkillResult, skill


class TelethonAdmin:
    """
    Навыки администратора: создание каналов, управление участниками, закрепление сообщений и выдача прав.
    """

    def __init__(self, tg_client: TelethonClient):
        self.tg_client = tg_client

    def _parse_entity(self, entity_id: Union[int, str]) -> Union[int, str]:
        """Утилитный метод для преобразования строковых ID в числа."""

        try:
            return int(entity_id)
        except ValueError:
            return str(entity_id).strip()

    @skill()
    async def create_channel(
        self, title: str, about: str = "", is_megagroup: bool = False
    ) -> SkillResult:
        """
        Создает новый публичный или приватный канал (или супергруппу).
        is_megagroup: Если True, будет создана группа для общения (супергруппа). Если False - канал (только для публикаций).

        """
        try:
            client = self.tg_client.client()
            result = await client(
                CreateChannelRequest(title=title, about=about, megagroup=is_megagroup)
            )

            # Извлекаем ID созданного чата. Формат -100XXXX... нужен для супергрупп и каналов.
            chat_id = f"-100{result.chats[0].id}"
            chat_type = "Супергруппа" if is_megagroup else "Канал"

            msg = f"{chat_type} '{title}' успешно создан. ID: {chat_id}"
            system_logger.info(f"[Telegram Telethon] {msg}")
            return SkillResult.ok(msg)

        except Exception as e:
            return SkillResult.fail(f"Ошибка при создании чата: {e}")

    @skill()
    async def edit_chat_title(self, chat_id: Union[int, str], new_title: str) -> SkillResult:
        """Меняет название группы или канала."""

        try:
            client = self.tg_client.client()
            entity = await client.get_entity(self._parse_entity(chat_id))

            # Telethon разделяет смену имени для каналов/супергрупп и обычных маленьких групп
            try:
                await client(EditTitleRequest(channel=entity, title=new_title))
            except Exception:
                await client(EditChatTitleRequest(chat_id=entity.id, title=new_title))

            system_logger.info(
                f"[Telegram Telethon] Название чата {chat_id} изменено на '{new_title}'"
            )
            return SkillResult.ok(f"Название чата успешно изменено на '{new_title}'.")

        except ValueError:
            return SkillResult.fail("Ошибка: Некорректный ID чата.")
        except Exception as e:
            return SkillResult.fail(f"Ошибка при изменении названия чата: {e}")

    @skill()
    async def create_invite_link(self, chat_id: Union[int, str]) -> SkillResult:
        """Генерирует новую пригласительную ссылку для указанного чата."""

        try:
            client = self.tg_client.client()
            entity = await client.get_input_entity(self._parse_entity(chat_id))

            result = await client(ExportChatInviteRequest(peer=entity))

            system_logger.info(f"[Telegram Telethon] Создана ссылка для чата {chat_id}")
            return SkillResult.ok(f"Пригласительная ссылка сгенерирована: {result.link}")

        except Exception as e:
            return SkillResult.fail(f"Ошибка при генерации ссылки: {e}")

    @skill()
    async def get_participants(self, chat_id: Union[int, str], limit: int = 100) -> SkillResult:
        """Возвращает список участников группы или канала."""

        try:
            client = self.tg_client.client()
            entity = await client.get_entity(self._parse_entity(chat_id))

            participants = []
            async for user in client.iter_participants(entity, limit=limit):
                name = utils.get_display_name(user) or "Unknown"
                bot_tag = " [Bot]" if user.bot else ""
                participants.append(f"- ID: `{user.id}` | Имя: {name}{bot_tag}")

            if not participants:
                return SkillResult.ok("Список участников пуст (или нет прав на его просмотр).")

            return SkillResult.ok(f"Участники (последние {limit} чел.):\n" + "\n".join(participants))

        except Exception as e:
            return SkillResult.fail(f"Ошибка при получении участников: {e}")

    @skill()
    async def promote_user(
        self, chat_id: Union[int, str], user_id: Union[int, str], add_admins: bool = False
    ) -> SkillResult:
        """
        Выдает пользователю права администратора в чате.
        Если add_admins=True, пользователь сможет назначать других администраторов.
        """

        try:
            client = self.tg_client.client()

            await client.edit_admin(
                entity=self._parse_entity(chat_id),
                user=self._parse_entity(user_id),
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

            system_logger.info(
                f"[Telegram Telethon] Пользователь {user_id} назначен администратором в {chat_id}"
            )
            return SkillResult.ok(f"Пользователь {user_id} успешно повышен до администратора.")

        except Exception as e:
            return SkillResult.fail(f"Ошибка при выдаче прав администратора: {e}")

    @skill()
    async def demote_user(
        self, chat_id: Union[int, str], user_id: Union[int, str]
    ) -> SkillResult:
        """Забирает у пользователя права администратора (понижает до обычного участника)."""

        try:
            client = self.tg_client.client()

            await client.edit_admin(
                entity=self._parse_entity(chat_id),
                user=self._parse_entity(user_id),
                is_admin=False,
            )

            system_logger.info(
                f"[Telegram Telethon] Пользователь {user_id} лишен прав администратора в {chat_id}"
            )
            return SkillResult.ok(f"Пользователь {user_id} понижен до обычного участника.")

        except Exception as e:
            return SkillResult.fail(f"Ошибка при снятии прав администратора: {e}")

    @skill()
    async def pin_message(
        self, chat_id: Union[int, str], message_id: int, notify: bool = True
    ) -> SkillResult:
        """Закрепляет сообщение в группе или канале. notify=True (с уведомлением всех), False (тихо)."""

        try:
            client = self.tg_client.client()
            await client.pin_message(
                entity=self._parse_entity(chat_id), message=int(message_id), notify=notify
            )

            system_logger.info(
                f"[Telegram Telethon] Сообщение {message_id} закреплено в {chat_id}"
            )
            return SkillResult.ok(f"Сообщение {message_id} успешно закреплено.")

        except Exception as e:
            return SkillResult.fail(f"Ошибка при закреплении сообщения: {e}")

    @skill()
    async def unpin_message(self, chat_id: Union[int, str], message_id: int) -> SkillResult:
        """Открепляет конкретное сообщение в чате."""

        try:
            client = self.tg_client.client()
            await client.unpin_message(
                entity=self._parse_entity(chat_id), message=int(message_id)
            )

            system_logger.info(
                f"[Telegram Telethon] Сообщение {message_id} откреплено в {chat_id}"
            )
            return SkillResult.ok(f"Сообщение {message_id} успешно откреплено.")

        except Exception as e:
            return SkillResult.fail(f"Ошибка при откреплении сообщения: {e}")
