from telethon.tl.types import InputMediaPoll, Poll, PollAnswer, TextWithEntities
from telethon.tl.functions.messages import SendVoteRequest

from src.l2_interfaces.telegram.telethon.client import TelethonClient
from src.l3_agent.skills.registry import SkillResult, skill
from src.utils.logger import system_logger


class TelethonPolls:
    """
    Навыки агента для взаимодействия с опросами (создание, чтение результатов, голосование, закрытие).
    """

    def __init__(self, tg_client: TelethonClient):
        self.tg_client = tg_client

    @skill()
    async def create_poll(
        self, chat_id: int, question: str, options: list[str]
    ) -> SkillResult:
        """Создает новый опрос в указанном чате."""

        if len(options) < 2 or len(options) > 10:
            return SkillResult.fail(
                "Ошибка: Количество вариантов ответа должно быть от 2 до 10."
            )

        try:
            client = self.tg_client.client()

            # Оборачиваем текст ответов в TextWithEntities
            answers = [
                PollAnswer(
                    text=TextWithEntities(text=opt, entities=[]), option=str(i).encode("utf-8")
                )
                for i, opt in enumerate(options)
            ]

            # Оборачиваем вопрос в TextWithEntities
            poll = Poll(
                id=0,
                question=TextWithEntities(text=question, entities=[]),
                answers=answers,
            )

            msg = await client.send_message(int(chat_id), file=InputMediaPoll(poll=poll))

            system_logger.info(f"[Telegram Telethon] Создан опрос '{question}' в чате {chat_id}")
            return SkillResult.ok(f"Опрос успешно создан. ID сообщения: {msg.id}")

        except Exception as e:
            msg = f"Ошибка при создании опроса: {e}"
            return SkillResult.fail(msg)

    @skill()
    async def get_poll_results(self, chat_id: int, message_id: int) -> SkillResult:
        """Возвращает текущие результаты опроса (варианты ответов и количество голосов)."""

        try:
            client = self.tg_client.client()
            msg = await client.get_messages(int(chat_id), ids=int(message_id))

            if not msg or not msg.poll:
                return SkillResult.fail(
                    f"Ошибка: Сообщение {message_id} не найдено или не является опросом."
                )

            poll = msg.poll.poll
            results = msg.poll.results

            total_voters = results.total_voters if results else 0
            lines = [f"Опрос: {poll.question}", f"👥 Всего голосов: {total_voters}\n"]

            # Сопоставляем ответы с результатами
            if results and results.results:
                for answer in poll.answers:
                    # Ищем статистику конкретного ответа (сравниваем bytes)
                    res = next((r for r in results.results if r.option == answer.option), None)
                    voters = res.voters if res else 0
                    lines.append(f"- {answer.text}: {voters} голосов")

            return SkillResult.ok("\n".join(lines))

        except Exception as e:
            return SkillResult.fail(f"Ошибка при получении результатов опроса: {e}")

    @skill()
    async def vote_in_poll(
        self, chat_id: int, message_id: int, option_indices: list[int]
    ) -> SkillResult:
        """
        Голосует в опросе.
        option_indices - массив индексов вариантов ответов (начиная с 0).
        """
        try:
            client = self.tg_client.client()
            msg = await client.get_messages(int(chat_id), ids=int(message_id))

            if not msg or not msg.poll:
                return SkillResult.fail(
                    "Ошибка: Сообщение не найдено или не является опросом."
                )

            if msg.poll.poll.closed:
                return SkillResult.fail("Ошибка: Опрос уже закрыт, голосование невозможно.")

            # Формируем байтовые значения выбранных ответов
            options_to_vote = []
            for idx in option_indices:
                idx = int(idx)
                if 0 <= idx < len(msg.poll.poll.answers):
                    options_to_vote.append(msg.poll.poll.answers[idx].option)
                else:
                    return SkillResult.fail(f"Ошибка: Несуществующий индекс ответа ({idx}).")

            # Отправляем голос
            await client(
                SendVoteRequest(
                    peer=await client.get_input_entity(int(chat_id)),
                    msg_id=int(message_id),
                    options=options_to_vote,
                )
            )

            system_logger.info(f"[Telegram Telethon] Оставлен голос в опросе {message_id} (чат {chat_id})")
            return SkillResult.ok("Голос успешно учтен.")

        except Exception as e:
            msg = f"Ошибка при голосовании: {e}"
            return SkillResult.fail(msg)

    @skill()
    async def close_poll(self, chat_id: int, message_id: int) -> SkillResult:
        """Закрывает опрос (останавливает голосование)."""
        try:
            client = self.tg_client.client()
            msg = await client.get_messages(int(chat_id), ids=int(message_id))

            if not msg or not msg.poll:
                return SkillResult.fail(
                    "Ошибка: Сообщение не найдено или не является опросом."
                )

            if msg.poll.poll.closed:
                return SkillResult.ok("Опрос уже был закрыт ранее.")

            # Закрываем опрос через редактирование (стандартный метод в Telethon)
            poll = msg.poll.poll
            poll.closed = True

            await client.edit_message(
                int(chat_id), int(message_id), file=InputMediaPoll(poll=poll)
            )

            system_logger.info(f"[Telegram Telethon] Опрос {message_id} закрыт (чат {chat_id})")
            return SkillResult.ok("Опрос успешно закрыт.")

        except Exception as e:
            return SkillResult.fail(f"Ошибка при закрытии опроса: {e}")
