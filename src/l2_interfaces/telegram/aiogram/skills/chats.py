"""
Навыки бота для чтения списков чатов и их метаданных (Aiogram).

Внимание: ограничены спецификой Bot API. Бот не имеет доступа к глобальному списку
своих диалогов, поэтому он может "видеть" только те чаты, с которыми взаимодействовал
после старта системы (MRU-кэш).
"""

from src.l2_interfaces.telegram.aiogram.state import AiogramState
from src.l2_interfaces.telegram.aiogram.client import AiogramClient

from src.l3_agent.skills.registry import SkillResult, skill


class AiogramChats:
    """Навыки для взаимодействия со списком активных чатов."""

    def __init__(self, aiogram_client: AiogramClient, state: AiogramState) -> None:
        """
        Инициализирует скиллы.

        Args:
            aiogram_client (AiogramClient): Клиент Aiogram.
            state (AiogramState): Состояние интерфейса с кэшем диалогов.
        """
        self.client = aiogram_client
        self.state = state

    @skill()
    async def get_chats(self, limit: int = 10) -> SkillResult:
        """
        Возвращает список последних чатов, с которыми бот взаимодействовал.
        (Bot API не позволяет получить полный список всех диалогов аккаунта).

        Args:
            limit (int): Максимальное количество чатов для возврата.
        """
        try:
            if not self.state._chats_cache:
                return SkillResult.ok("Список чатов пуст. Никто не писал боту после запуска.")

            # Берем из кэша стейта (где самые свежие в конце), переворачиваем и обрезаем по limit
            lines = list(self.state._chats_cache.values())[::-1][:limit]

            return SkillResult.ok("\n".join(lines))

        except Exception as e:
            return SkillResult.fail(f"Ошибка при получении списка чатов (Aiogram): {e}")

    @skill()
    async def get_chat_info(self, chat_id: int) -> SkillResult:
        """
        Получает подробную метаинформацию о конкретном чате (описание, кол-во участников).

        Args:
            chat_id (int): Уникальный числовой идентификатор чата.
        """
        try:
            bot = self.client.bot()
            chat = await bot.get_chat(int(chat_id))

            lines = [f"Информация о чате {chat_id}:"]
            lines.append(f"Тип: {chat.type}")
            lines.append(
                f"Название/Имя: {chat.title or chat.full_name or chat.username or 'Unknown'}"
            )

            if chat.description:
                lines.append(f"Описание: {chat.description}")

            # Для групп можно получить количество участников
            if chat.type in ("group", "supergroup", "channel"):
                count = await bot.get_chat_member_count(int(chat_id))
                lines.append(f"Количество участников: {count}")

            return SkillResult.ok("\n".join(lines))

        except ValueError:
            return SkillResult.fail(f"Ошибка: Некорректный ID чата ({chat_id}).")

        except Exception as e:
            if "chat not found" in str(e).lower():
                return SkillResult.fail(
                    "Бот не нашел этот чат. Возможно, его удалили или пользователя заблокировали."
                )
            return SkillResult.fail(
                f"Ошибка при получении информации о чате {chat_id} (Aiogram): {e}"
            )
