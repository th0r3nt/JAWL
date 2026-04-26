from typing import Union

from src.l2_interfaces.telegram.kurigram.client import KurigramClient
from src.l3_agent.skills.registry import SkillResult, skill
from src.utils._tools import parse_int_or_str
from src.utils.logger import system_logger


class KurigramPolls:
    """
    Навыки агента для взаимодействия с опросами (создание, чтение результатов, голосование, закрытие).
    """

    def __init__(self, tg_client: KurigramClient):
        self.tg_client = tg_client

    @staticmethod
    def _text_value(value) -> str:
        return getattr(value, "text", value) or ""

    @skill()
    async def create_poll(
        self, chat_id: Union[int, str], question: str, options: list[str]
    ) -> SkillResult:
        """Создает новый опрос в указанном чате."""

        if len(options) < 2 or len(options) > 10:
            return SkillResult.fail(
                "Ошибка: Количество вариантов ответа должно быть от 2 до 10."
            )

        try:
            client = self.tg_client.client()

            msg = await client.send_poll(
                chat_id=parse_int_or_str(chat_id), question=question, options=options
            )

            system_logger.info(f"[Telegram Kurigram] Создан опрос '{question}' в чате {chat_id}")
            return SkillResult.ok(f"Опрос успешно создан. ID сообщения: {msg.id}")

        except Exception as e:
            msg = f"Ошибка при создании опроса: {e}"
            return SkillResult.fail(msg)

    @skill()
    async def get_poll_results(
        self, chat_id: Union[int, str], message_id: int
    ) -> SkillResult:
        """Возвращает текущие результаты опроса (варианты ответов и количество голосов)."""

        try:
            client = self.tg_client.client()
            msg = await client.get_messages(
                chat_id=parse_int_or_str(chat_id),
                message_ids=int(message_id),
                replies=0,
            )

            poll = getattr(msg, "poll", None) if msg else None
            if not msg or not poll:
                return SkillResult.fail(
                    f"Ошибка: Сообщение {message_id} не найдено или не является опросом."
                )

            total_voters = getattr(poll, "total_voter_count", 0) or 0
            question = self._text_value(getattr(poll, "question", ""))
            lines = [f"Опрос: {question}", f"Всего голосов: {total_voters}\n"]

            for option in getattr(poll, "options", []) or []:
                text = self._text_value(getattr(option, "text", ""))
                voters = getattr(option, "voter_count", 0) or 0
                lines.append(f"- {text}: {voters} голосов")

            return SkillResult.ok("\n".join(lines))

        except Exception as e:
            return SkillResult.fail(f"Ошибка при получении результатов опроса: {e}")

    @skill()
    async def vote_in_poll(
        self,
        chat_id: Union[int, str],
        message_id: int,
        option_indices: list[int],
    ) -> SkillResult:
        """
        Голосует в опросе.
        option_indices - массив индексов вариантов ответов (начиная с 0).
        """
        try:
            client = self.tg_client.client()
            target_chat = parse_int_or_str(chat_id)
            target_message = int(message_id)
            msg = await client.get_messages(
                chat_id=target_chat,
                message_ids=target_message,
                replies=0,
            )

            poll = getattr(msg, "poll", None) if msg else None
            if not msg or not poll:
                return SkillResult.fail(
                    "Ошибка: Сообщение не найдено или не является опросом."
                )

            if getattr(poll, "is_closed", False) is True:
                return SkillResult.fail("Ошибка: Опрос уже закрыт, голосование невозможно.")

            options_to_vote = []
            poll_options = getattr(poll, "options", None)
            if not isinstance(poll_options, list):
                legacy_poll = getattr(poll, "poll", None)
                poll_options = getattr(legacy_poll, "answers", None)
            poll_options = poll_options or []
            for idx in option_indices:
                idx = int(idx)
                if 0 <= idx < len(poll_options):
                    options_to_vote.append(idx)
                else:
                    return SkillResult.fail(f"Ошибка: Несуществующий индекс ответа ({idx}).")

            await client.vote_poll(target_chat, target_message, options_to_vote)

            system_logger.info(f"[Telegram Kurigram] Оставлен голос в опросе {message_id} (чат {chat_id})")
            return SkillResult.ok("Голос успешно учтен.")

        except Exception as e:
            msg = f"Ошибка при голосовании: {e}"
            return SkillResult.fail(msg)

    @skill()
    async def close_poll(
        self, chat_id: Union[int, str], message_id: int
    ) -> SkillResult:
        """Закрывает опрос (останавливает голосование)."""
        try:
            client = self.tg_client.client()
            target_chat = parse_int_or_str(chat_id)
            target_message = int(message_id)
            msg = await client.get_messages(
                chat_id=target_chat,
                message_ids=target_message,
                replies=0,
            )

            poll = getattr(msg, "poll", None) if msg else None
            if not msg or not poll:
                return SkillResult.fail(
                    "Ошибка: Сообщение не найдено или не является опросом."
                )

            if getattr(poll, "is_closed", False) is True:
                return SkillResult.ok("Опрос уже был закрыт ранее.")

            await client.stop_poll(target_chat, target_message)

            system_logger.info(f"[Telegram Kurigram] Опрос {message_id} закрыт (чат {chat_id})")
            return SkillResult.ok("Опрос успешно закрыт.")

        except Exception as e:
            return SkillResult.fail(f"Ошибка при закрытии опроса: {e}")
