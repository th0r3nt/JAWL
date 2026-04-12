from telethon import utils
from telethon.tl.functions.contacts import BlockRequest, UnblockRequest, GetBlockedRequest
from telethon.tl.types import ChannelParticipantsKicked

from src.l2_interfaces.telegram.telethon.client import TelethonClient
from src.l3_agent.skills.registry import SkillResult, skill
from src.utils.logger import system_logger
from typing import Optional


class TelethonModeration:
    """
    Навыки для блокировки и разблокировки пользователей (глобально или в чатах).
    """

    def __init__(self, tg_client: TelethonClient):
        self.tg_client = tg_client

    @skill()
    async def ban_user(self, user_id: int, chat_id: Optional[int] = None) -> SkillResult:
        """
        Блокирует пользователя.
        - Если chat_id НЕ передан: добавляет юзера в глобальный черный список аккаунта.
        - Если chat_id передан: банит (исключает) юзера в указанной группе/канале.
        """

        try:
            client = self.tg_client.client()
            target_user = int(user_id)

            if chat_id:
                target_chat = int(chat_id)
                # view_messages=False - это полный бан пользователя (он больше не увидит чат)
                await client.edit_permissions(target_chat, target_user, view_messages=False)
                msg = f"Пользователь {target_user} забанен в чате {target_chat}."
            else:
                await client(BlockRequest(id=target_user))
                msg = f"Пользователь {target_user} добавлен в глобальный ЧС."

            system_logger.info({msg})
            return SkillResult.ok(msg)

        except ValueError:
            return SkillResult.fail("Ошибка: ID пользователя и чата должны быть числами.")
        except Exception as e:
            return SkillResult.fail(f"Ошибка при блокировке: {e}")

    @skill()
    async def unban_user(self, user_id: int, chat_id: Optional[int] = None) -> SkillResult:
        """
        Разблокирует пользователя.
        - Если chat_id НЕ передан: удаляет юзера из глобального ЧС.
        - Если chat_id передан: разбанивает юзера в указанной группе/канале (снимает ограничения).
        """

        try:
            client = self.tg_client.client()
            target_user = int(user_id)

            if chat_id:
                target_chat = int(chat_id)
                # Снимаем все ограничения, возвращая пользователю дефолтные права группы
                await client.edit_permissions(target_chat, target_user)
                msg = f"Пользователь {target_user} разбанен в чате {target_chat}."
            else:
                await client(UnblockRequest(id=target_user))
                msg = f"Пользователь {target_user} удален из глобального ЧС."

            system_logger.info({msg})
            return SkillResult.ok(msg)

        except ValueError:
            return SkillResult.fail("Ошибка: ID пользователя и чата должны быть числами.")
        except Exception as e:
            return SkillResult.fail(f"Ошибка при разблокировке: {e}")

    @skill()
    async def get_banned_users(self, limit: int = 50, chat_id: Optional[int] = None) -> SkillResult:
        """
        Возвращает список заблокированных пользователей.
        - Если chat_id НЕ передан: возвращает глобальный ЧС аккаунта.
        - Если chat_id передан: возвращает список забаненных юзеров в конкретном чате.
        """

        try:
            client = self.tg_client.client()
            banned_list = []

            if chat_id:
                target_chat = int(chat_id)
                # Ищем забаненных участников через фильтр
                async for user in client.iter_participants(
                    target_chat, filter=ChannelParticipantsKicked, limit=limit
                ):
                    name = utils.get_display_name(user) or "Unknown"
                    banned_list.append(f"- ID: `{user.id}` | Имя: {name}")

                context_str = f"в чате {target_chat}"
            else:
                # Получаем глобальный ЧС
                blocked_req = await client(GetBlockedRequest(offset=0, limit=limit))
                for user in blocked_req.users:
                    name = utils.get_display_name(user) or "Unknown"
                    banned_list.append(f"- ID: `{user.id}` | Имя: {name}")

                context_str = "в глобальном ЧС"

            if not banned_list:
                return SkillResult.ok(f"Список забаненных {context_str} пуст.")

            return SkillResult.ok("\n".join(banned_list))

        except Exception as e:
            return SkillResult.fail(f"Ошибка при получении списка забаненных: {e}")
