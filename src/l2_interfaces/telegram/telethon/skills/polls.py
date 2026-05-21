"""
Telethon Polls Skills.

Provides skills to create polls, cast votes, read results, and close polls in chats.
"""

from typing import List
from telethon.tl.types import InputMediaPoll, Poll, PollAnswer, TextWithEntities
from telethon.tl.functions.messages import SendVoteRequest

from src.l2_interfaces.telegram.telethon.client import TelethonClient
from src.l3_agent.skills.registry import SkillResult, skill
from src.utils.logger import main_logger


class TelethonPolls:
    """Group of skills for managing and interacting with polls."""

    def __init__(self, tg_client: TelethonClient) -> None:
        self.tg_client = tg_client

    @skill()
    async def create_poll(
        self, chat_id: int, question: str, options: List[str]
    ) -> SkillResult:
        """
        Creates poll in chat. Options array length 2-10.
        """

        if len(options) < 2 or len(options) > 10:
            return SkillResult.fail("Error: Options length must be between 2 and 10.")

        try:
            client = self.tg_client.client()

            answers = [
                PollAnswer(
                    text=TextWithEntities(text=opt, entities=[]), option=str(i).encode("utf-8")
                )
                for i, opt in enumerate(options)
            ]

            poll = Poll(
                id=0,
                question=TextWithEntities(text=question, entities=[]),
                answers=answers,
            )

            msg = await client.send_message(int(chat_id), file=InputMediaPoll(poll=poll))

            main_logger.info(
                f"[Telegram Telethon] Created poll '{question}' in chat {chat_id}"
            )
            return SkillResult.ok(f"True. ID: {msg.id}")

        except Exception as e:
            return SkillResult.fail(f"Error creating poll: {e}")

    @skill()
    async def get_poll_results(self, chat_id: int, message_id: int) -> SkillResult:
        """
        Reads poll statistics.
        """

        try:
            client = self.tg_client.client()
            msg = await client.get_messages(int(chat_id), ids=int(message_id))

            if not msg or not msg.poll:
                return SkillResult.fail(
                    f"Error: Message {message_id} not found or is not a poll."
                )

            poll = msg.poll.poll
            results = msg.poll.results

            total_voters = results.total_voters if results else 0
            lines = [f"Poll: {poll.question}", f"👥 Total votes: {total_voters}\n"]

            if results and results.results:
                for answer in poll.answers:
                    res = next((r for r in results.results if r.option == answer.option), None)
                    voters = res.voters if res else 0
                    lines.append(f"- {answer.text}: {voters} votes")

            return SkillResult.ok("\n".join(lines))

        except Exception as e:
            return SkillResult.fail(f"Error getting poll results: {e}")

    @skill()
    async def vote_in_poll(
        self, chat_id: int, message_id: int, option_indices: List[int]
    ) -> SkillResult:
        """
        Votes in poll using option indices (0-based).
        """

        try:
            client = self.tg_client.client()
            msg = await client.get_messages(int(chat_id), ids=int(message_id))

            if not msg or not msg.poll:
                return SkillResult.fail("Error: Message not found or is not a poll.")

            if msg.poll.poll.closed:
                return SkillResult.fail("Error: Poll is closed.")

            options_to_vote = []
            for idx in option_indices:
                idx = int(idx)
                if 0 <= idx < len(msg.poll.poll.answers):
                    options_to_vote.append(msg.poll.poll.answers[idx].option)
                else:
                    return SkillResult.fail(
                        f"Error: Non-existent answer option index ({idx})."
                    )

            await client(
                SendVoteRequest(
                    peer=await client.get_input_entity(int(chat_id)),
                    msg_id=int(message_id),
                    options=options_to_vote,
                )
            )

            main_logger.info(
                f"[Telegram Telethon] Cast vote in poll {message_id} (chat {chat_id})"
            )
            return SkillResult.ok("True")

        except Exception as e:
            return SkillResult.fail(f"Error casting vote: {e}")

    @skill()
    async def close_poll(self, chat_id: int, message_id: int) -> SkillResult:
        """
        Closes created poll, preventing further voting.
        """

        try:
            client = self.tg_client.client()
            msg = await client.get_messages(int(chat_id), ids=int(message_id))

            if not msg or not msg.poll:
                return SkillResult.fail("Error: Message not found or is not a poll.")

            if msg.poll.poll.closed:
                return SkillResult.ok("True")

            poll = msg.poll.poll
            poll.closed = True

            await client.edit_message(
                int(chat_id), int(message_id), file=InputMediaPoll(poll=poll)
            )

            main_logger.info(f"[Telegram Telethon] Poll {message_id} closed (chat {chat_id})")
            return SkillResult.ok("True")

        except Exception as e:
            return SkillResult.fail(f"Error closing poll: {e}")
