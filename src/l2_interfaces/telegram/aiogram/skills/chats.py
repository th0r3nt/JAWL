from src.l0_state.interfaces.state import AiogramState
from src.l2_interfaces.telegram.aiogram.client import AiogramClient

from src.l3_agent.skills.registry import SkillResult, skill
from src.utils.logger import system_logger


class AiogramChats:
    """
    Навыки бота для работы со списком чатов.
    Ограничены спецификой Bot API: бот не может читать историю сообщений,
    если не сохранял их сам.
    """

    def __init__(self, aiogram_client: AiogramClient, state: AiogramState):
        self.client = aiogram_client
        self.state = state

    @skill()
    async def get_chats(self, limit: int = 10) -> SkillResult:
        """
        Возвращает список последних чатов, с которыми бот взаимодействовал.
        Боты не могут получить полный список всех диалогов из API Telegram.
        """
        try:
            if not self.state._chats_cache:
                return SkillResult.ok("Список чатов пуст. Никто не писал боту после запуска.")

            # Берем из кэша стейта (где самые свежие в конце), переворачиваем и обрезаем по limit
            lines = list(self.state._chats_cache.values())[::-1][:limit]

            return SkillResult.ok("\n".join(lines))

        except Exception as e:
            msg = f"Ошибка при получении списка чатов (Aiogram): {e}"
            system_logger.error(f"[Agent Action Result] {msg}")
            return SkillResult.fail(msg)

    @skill()
    async def get_chat_info(self, chat_id: int) -> SkillResult:
        """
        Получает информацию о конкретном чате (описание, кол-во участников).
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

            system_logger.info(
                f"[Agent Action] Запрошена информация о чате {chat_id} (Aiogram)"
            )
            return SkillResult.ok("\n".join(lines))

        except ValueError:
            return SkillResult.fail(f"Ошибка: Некорректный ID чата ({chat_id}).")
        except Exception as e:
            msg = f"Ошибка при получении информации о чате {chat_id} (Aiogram): {e}"
            system_logger.error(f"[Agent Action Result] {msg}")

            if "chat not found" in str(e).lower():
                return SkillResult.fail(
                    "Бот не нашел этот чат. Возможно, его удалили или заблокировали бота."
                )

            return SkillResult.fail(msg)