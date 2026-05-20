"""
Навыки модерации и управления участниками чатов (Telethon).

Позволяют блокировать (Blacklist), мутить (Read-Only) и выкидывать
пользователей (Kick) из администрируемых агентом групп и каналов.
"""

import datetime
from typing import Optional
from telethon import utils
from telethon.tl.functions.contacts import BlockRequest, UnblockRequest, GetBlockedRequest
from telethon.tl.types import ChannelParticipantsKicked

from src.l2_interfaces.telegram.telethon.client import TelethonClient
from src.l3_agent.skills.registry import SkillResult, skill
from src.utils.logger import main_logger


class TelethonModeration:
    """Инструментарий карательных мер администратора."""

    def __init__(self, tg_client: TelethonClient) -> None:
        self.tg_client = tg_client

    @skill()
    async def ban_user(self, user_id: int, chat_id: Optional[int] = None) -> SkillResult:
        """
        Bans user. 
        If chat_id omitted, blocks globally in personal blacklist.
        """

        try:
            client = self.tg_client.client()
            target_user = int(user_id)

            if chat_id:
                target_chat = int(chat_id)
                await client.edit_permissions(target_chat, target_user, view_messages=False)
                msg = f"[Telegram Telethon] Пользователь {target_user} забанен в чате {target_chat}."
            else:
                await client(BlockRequest(id=target_user))
                msg = (
                    f"[Telegram Telethon] Пользователь {target_user} добавлен в глобальный ЧС."
                )

            main_logger.info(msg)
            return SkillResult.ok("True")

        except ValueError:
            return SkillResult.fail("Ошибка: ID пользователя и чата должны быть числами.")
        except Exception as e:
            return SkillResult.fail(f"Ошибка при блокировке: {e}")

    @skill()
    async def unban_user(self, user_id: int, chat_id: Optional[int] = None) -> SkillResult:
        """
        Unbans user. 
        If chat_id omitted, unblocks from personal blacklist.
        """

        try:
            client = self.tg_client.client()
            target_user = int(user_id)

            if chat_id:
                target_chat = int(chat_id)
                await client.edit_permissions(target_chat, target_user)
                msg = f"[Telegram Telethon] Пользователь {target_user} разбанен в чате {target_chat}."
            else:
                await client(UnblockRequest(id=target_user))
                msg = (
                    f"[Telegram Telethon] Пользователь {target_user} удален из глобального ЧС."
                )

            main_logger.info(msg)
            return SkillResult.ok("True")

        except ValueError:
            return SkillResult.fail("Ошибка: ID пользователя и чата должны быть числами.")
        except Exception as e:
            return SkillResult.fail(f"Ошибка при разблокировке: {e}")

    @skill()
    async def kick_user(self, user_id: int, chat_id: int) -> SkillResult:
        """
        Kicks user from group.
        """

        try:
            client = self.tg_client.client()
            target_user = int(user_id)
            target_chat = int(chat_id)

            await client.kick_participant(target_chat, target_user)

            msg = f"[Telegram Telethon] Пользователь {target_user} выгнан (kick) из чата {target_chat}."
            main_logger.info(msg)
            return SkillResult.ok("True")

        except ValueError:
            return SkillResult.fail("Ошибка: ID пользователя и чата должны быть числами.")
        except Exception as e:
            return SkillResult.fail(f"Ошибка при кике пользователя: {e}")

    @skill()
    async def mute_user(
        self, user_id: int, chat_id: int, duration_minutes: int = 0
    ) -> SkillResult:
        """
        Mutes user in group, preventing message sending.
        """
        try:
            client = self.tg_client.client()
            target_user = int(user_id)
            target_chat = int(chat_id)

            until_date = None
            if duration_minutes > 0:
                until_date = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(
                    minutes=duration_minutes
                )

            await client.edit_permissions(
                target_chat, target_user, until_date=until_date, send_messages=False
            )

            duration_str = (
                f"на {duration_minutes} минут" if duration_minutes > 0 else "навсегда"
            )
            msg = f"[Telegram Telethon] Пользователь {target_user} замучен {duration_str} в чате {target_chat}."
            main_logger.info(msg)
            return SkillResult.ok("True")

        except ValueError:
            return SkillResult.fail("Ошибка: Значения должны быть числами.")
        except Exception as e:
            return SkillResult.fail(f"Ошибка при муте пользователя: {e}")

    @skill()
    async def get_banned_users(
        self, limit: int = 50, chat_id: Optional[int] = None
    ) -> SkillResult:
        """
        Returns banned users list. 
        If chat_id omitted, returns personal blacklist.
        """

        try:
            client = self.tg_client.client()
            banned_list = []

            if chat_id:
                target_chat = int(chat_id)
                async for user in client.iter_participants(
                    target_chat, filter=ChannelParticipantsKicked, limit=limit
                ):
                    name = utils.get_display_name(user) or "Unknown"
                    banned_list.append(f"- ID: `{user.id}` | Имя: {name}")
                context_str = f"в чате {target_chat}"
            else:
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
