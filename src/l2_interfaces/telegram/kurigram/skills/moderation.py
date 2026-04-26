import datetime
from typing import Optional, Union

from src.l2_interfaces.telegram.kurigram.client import KurigramClient
from src.l3_agent.skills.registry import SkillResult, skill
from src.utils._tools import parse_int_or_str
from src.utils.logger import system_logger


class KurigramModeration:
    """
    Навыки для блокировки, разблокировки, мута и кика пользователей.
    """

    def __init__(self, tg_client: KurigramClient):
        self.tg_client = tg_client

    @staticmethod
    def _display_name(entity) -> str:
        title = getattr(entity, "title", None)
        if title:
            return title

        name = " ".join(
            part
            for part in (
                getattr(entity, "first_name", ""),
                getattr(entity, "last_name", ""),
            )
            if part
        )
        return name or getattr(entity, "username", None) or "Unknown"

    @skill()
    async def ban_user(
        self, user_id: Union[int, str], chat_id: Optional[Union[int, str]] = None
    ) -> SkillResult:
        """
        Банит пользователя (исключает навсегда без возможности вернуться).
        - Если chat_id НЕ передан: добавляет юзера в глобальный черный список аккаунта.
        - Если chat_id передан: банит юзера в указанной группе/канале (если есть права).
        """

        try:
            client = self.tg_client.client()
            target_user = parse_int_or_str(user_id)

            if chat_id is not None:
                target_chat = parse_int_or_str(chat_id)
                await client.ban_chat_member(target_chat, target_user)
                msg = f"[Telegram Kurigram] Пользователь {target_user} забанен в чате {target_chat}."
            else:
                await client.block_user(target_user)
                msg = (
                    f"[Telegram Kurigram] Пользователь {target_user} добавлен в глобальный ЧС."
                )

            system_logger.info(msg)
            return SkillResult.ok(msg)

        except ValueError:
            return SkillResult.fail("Ошибка: ID пользователя и чата должны быть числами.")
        except Exception as e:
            return SkillResult.fail(f"Ошибка при блокировке: {e}")

    @skill()
    async def unban_user(
        self, user_id: Union[int, str], chat_id: Optional[Union[int, str]] = None
    ) -> SkillResult:
        """
        Разблокирует пользователя (снимает мут или бан).
        - Если chat_id НЕ передан: удаляет юзера из глобального ЧС.
        - Если chat_id передан: разбанивает юзера в группе (снимает ограничения).
        """

        try:
            client = self.tg_client.client()
            target_user = parse_int_or_str(user_id)

            if chat_id is not None:
                target_chat = parse_int_or_str(chat_id)
                await client.unban_chat_member(target_chat, target_user)
                msg = f"[Telegram Kurigram] Пользователь {target_user} разбанен в чате {target_chat}."
            else:
                await client.unblock_user(target_user)
                msg = (
                    f"[Telegram Kurigram] Пользователь {target_user} удален из глобального ЧС."
                )

            system_logger.info(msg)
            return SkillResult.ok(msg)

        except ValueError:
            return SkillResult.fail("Ошибка: ID пользователя и чата должны быть числами.")
        except Exception as e:
            return SkillResult.fail(f"Ошибка при разблокировке: {e}")

    @skill()
    async def kick_user(
        self, user_id: Union[int, str], chat_id: Union[int, str]
    ) -> SkillResult:
        """
        Выгоняет пользователя из группы (Kick).
        """

        try:
            client = self.tg_client.client()
            target_user = parse_int_or_str(user_id)
            target_chat = parse_int_or_str(chat_id)

            await client.ban_chat_member(target_chat, target_user)
            await client.unban_chat_member(target_chat, target_user)

            msg = f"[Telegram Kurigram] Пользователь {target_user} выгнан (kick) из чата {target_chat}."
            system_logger.info(msg)
            return SkillResult.ok(msg)

        except ValueError:
            return SkillResult.fail("Ошибка: ID пользователя и чата должны быть числами.")
        except Exception as e:
            return SkillResult.fail(f"Ошибка при кике пользователя: {e}")

    @skill()
    async def mute_user(
        self,
        user_id: Union[int, str],
        chat_id: Union[int, str],
        duration_minutes: int = 0,
    ) -> SkillResult:
        """
        Запрещает пользователю писать сообщения в группе (Read-Only).
        duration_minutes: длительность мута в минутах. Если 0 - мут навсегда.
        """

        try:
            client = self.tg_client.client()
            target_user = parse_int_or_str(user_id)
            target_chat = parse_int_or_str(chat_id)
            duration_minutes = int(duration_minutes)

            restrict_kwargs = {}
            if duration_minutes > 0:
                restrict_kwargs["until_date"] = datetime.datetime.now(
                    datetime.timezone.utc
                ) + datetime.timedelta(
                    minutes=duration_minutes
                )

            from pyrogram.types import ChatPermissions

            await client.restrict_chat_member(
                target_chat,
                target_user,
                permissions=ChatPermissions(can_send_messages=False),
                **restrict_kwargs,
            )

            duration_str = (
                f"на {duration_minutes} минут" if duration_minutes > 0 else "навсегда"
            )
            msg = f"[Telegram Kurigram] Пользователь {target_user} замучен {duration_str} в чате {target_chat}."
            system_logger.info(msg)
            return SkillResult.ok(msg)

        except ValueError:
            return SkillResult.fail("Ошибка: Значения должны быть числами.")
        except Exception as e:
            return SkillResult.fail(f"Ошибка при муте пользователя: {e}")

    @skill()
    async def get_banned_users(
        self, limit: int = 50, chat_id: Optional[Union[int, str]] = None
    ) -> SkillResult:
        """Возвращает список заблокированных пользователей."""

        try:
            client = self.tg_client.client()
            banned_list = []
            limit = int(limit)

            if chat_id is not None:
                target_chat = parse_int_or_str(chat_id)
                from pyrogram import enums

                async for member in client.get_chat_members(
                    target_chat,
                    filter=enums.ChatMembersFilter.BANNED,
                    limit=limit,
                ):
                    user = member.user
                    if not user:
                        continue
                    name = self._display_name(user)
                    banned_list.append(f"- ID: `{user.id}` | Имя: {name}")
                context_str = f"в чате {target_chat}"
            else:
                async for blocked in client.get_blocked_message_senders(limit=limit):
                    name = self._display_name(blocked)
                    banned_list.append(f"- ID: `{blocked.id}` | Имя: {name}")
                context_str = "в глобальном ЧС"

            if not banned_list:
                return SkillResult.ok(f"Список забаненных {context_str} пуст.")

            return SkillResult.ok("\n".join(banned_list))

        except Exception as e:
            return SkillResult.fail(f"Ошибка при получении списка забаненных: {e}")
