"""
Telethon Messages Skills.

Provides skills for sending texts, documents, media downloads, forwards,
interacting with Inline buttons, and managing drafts.
"""

from datetime import timedelta
from typing import Optional, Union

from telethon.tl.functions.messages import SaveDraftRequest

from src.utils._tools import format_size, validate_sandbox_path, parse_int_or_str
from src.utils.logger import main_logger

from src.l2_interfaces.telegram.telethon.client import TelethonClient
from src.l2_interfaces.telegram.telethon.utils._message_parser import TelethonMessageParser

from src.l3_agent.skills.registry import SkillResult, skill


class TelethonMessages:
    """Tools for sending, editing, and managing messages."""

    def __init__(self, tg_client: TelethonClient) -> None:
        self.tg_client = tg_client

    @skill()
    async def send_message(
        self,
        to_id: Union[int, str],
        text: str,
        reply_to_message_id: Optional[int] = None,
        topic_id: Optional[int] = None,
        is_silent: bool = False,
        time_delay: Optional[int] = None,
    ) -> SkillResult:
        """
        Sends text message.
        Markdown supported.
        """

        try:
            client = self.tg_client.client()
            entity = parse_int_or_str(to_id)

            kwargs = {
                "entity": entity,
                "message": text,
                "silent": is_silent,
                "parse_mode": "md",
            }

            if reply_to_message_id:
                kwargs["reply_to"] = int(reply_to_message_id)
            elif topic_id:
                kwargs["reply_to"] = int(topic_id)

            if time_delay:
                delay_sec = max(10, int(time_delay))
                kwargs["schedule"] = timedelta(seconds=delay_sec)

            sent_msg = await client.send_message(**kwargs)

            try:
                await client.send_read_acknowledge(entity)
            except Exception:
                pass

            return SkillResult.ok(f"True. ID: {sent_msg.id}")

        except ValueError:
            return SkillResult.fail("Error: Invalid ID or Username.")
        except Exception as e:
            main_logger.error(f"Error sending message: {e}")
            return SkillResult.fail(f"Error sending message: {e}")

    @skill()
    async def send_file(
        self, chat_id: Union[int, str], file_path: str, caption: str = ""
    ) -> SkillResult:
        """
        Sends file from sandbox/ to chat.
        """
        try:
            safe_path = validate_sandbox_path(file_path)
            if not safe_path.is_file():
                return SkillResult.fail(f"Error: File not found ({safe_path.name}).")

            size_str = format_size(safe_path.stat().st_size)  # noqa: F841
            client = self.tg_client.client()
            entity = parse_int_or_str(chat_id)

            await client.send_file(entity, file=str(safe_path), caption=caption)

            main_logger.info(f"[Telegram Telethon] File {safe_path.name} sent to {chat_id}")
            return SkillResult.ok("True")

        except PermissionError as e:
            return SkillResult.fail(str(e))
        except Exception as e:
            return SkillResult.fail(f"Error sending file: {e}")

    @skill()
    async def download_file(
        self, chat_id: Union[int, str], message_id: int, dest_filename: str
    ) -> SkillResult:
        """
        Downloads message media attachment to sandbox/download/.
        """
        try:
            if "/" not in dest_filename and "\\" not in dest_filename:
                dest_filename = f"sandbox/_system/download/{dest_filename}"

            safe_path = validate_sandbox_path(dest_filename)
            client = self.tg_client.client()
            entity = parse_int_or_str(chat_id)

            msg = await client.get_messages(entity, ids=int(message_id))
            if not msg or not msg.media:
                return SkillResult.fail("Error: Message not found or does not contain media.")

            main_logger.info(
                f"[Telegram Telethon] Downloading file from message {message_id}..."
            )

            downloaded_path = await client.download_media(msg, file=str(safe_path))
            if not downloaded_path:
                return SkillResult.fail("Failed to download file.")

            size_str = format_size(safe_path.stat().st_size)
            main_logger.info(
                f"[Telegram Telethon] File downloaded: {safe_path.name} ({size_str})"
            )

            return SkillResult.ok(
                f"File downloaded successfully and saved as: sandbox/{safe_path.name} ({size_str})"
            )

        except PermissionError as e:
            return SkillResult.fail(str(e))
        except Exception as e:
            return SkillResult.fail(f"Error downloading file: {e}")

    @skill()
    async def forward_message(
        self, msg_id: int, from_id: Union[int, str], to_id: Union[int, str]
    ) -> SkillResult:
        """
        Forwards message from one chat to another.
        """

        try:
            client = self.tg_client.client()
            await client.forward_messages(
                entity=parse_int_or_str(to_id),
                messages=int(msg_id),
                from_peer=parse_int_or_str(from_id),
            )
            return SkillResult.ok("True")
        except Exception as e:
            return SkillResult.fail(f"Error forwarding message: {e}")

    @skill()
    async def delete_message(self, msg_id: int, chat_id: Union[int, str]) -> SkillResult:
        """
        Deletes message.
        """

        try:
            client = self.tg_client.client()
            await client.delete_messages(
                entity=parse_int_or_str(chat_id), message_ids=[int(msg_id)]
            )
            return SkillResult.ok("True")
        except Exception as e:
            return SkillResult.fail(f"Error deleting message: {e}")

    @skill()
    async def edit_message(
        self, msg_id: int, new_text: str, chat_id: Union[int, str]
    ) -> SkillResult:
        """
        Edits message text.
        """

        try:
            client = self.tg_client.client()
            await client.edit_message(
                entity=parse_int_or_str(chat_id),
                message=int(msg_id),
                text=new_text,
                parse_mode="md",
            )
            return SkillResult.ok("True")
        except Exception as e:
            return SkillResult.fail(f"Error editing message: {e}")

    @skill()
    async def click_inline_button(
        self, chat_id: Union[int, str], message_id: int, button_text: str
    ) -> SkillResult:
        """
        Clicks inline button under bot message by text.
        """

        try:
            client = self.tg_client.client()
            msg = await client.get_messages(parse_int_or_str(chat_id), ids=int(message_id))

            if not msg or not msg.buttons:
                return SkillResult.fail("Error: Message not found or has no inline buttons.")

            target_i, target_j = None, None
            for i, row in enumerate(msg.buttons):
                for j, button in enumerate(row):
                    if button.text and button_text.lower() in button.text.lower():
                        target_i, target_j = i, j
                        break
                if target_i is not None:
                    break

            if target_i is None:
                available = [btn.text for row in msg.buttons for btn in row if btn.text]
                return SkillResult.fail(
                    f"Error: Button '{button_text}' not found. Available: {available}"
                )

            result = await msg.click(target_i, target_j)
            msg_callback = (
                result.message
                if (result and hasattr(result, "message") and result.message)
                else ""
            )

            return SkillResult.ok(
                f"True. Callback: {msg_callback}" if msg_callback else "True"
            )

        except ValueError:
            return SkillResult.fail("Error: Invalid chat or message ID.")
        except Exception as e:
            return SkillResult.fail(f"Error clicking button: {e}")

    @skill()
    async def search_messages(
        self, chat_id: Union[int, str], query: str, limit: int = 10
    ) -> SkillResult:
        """
        Searches chat history.
        """

        try:
            client = self.tg_client.client()
            entity = parse_int_or_str(chat_id)

            messages = []
            async for msg in client.iter_messages(entity, search=query, limit=limit):
                formatted = await TelethonMessageParser.build_string(
                    client=client,
                    target_entity=entity,
                    msg=msg,
                    timezone=self.tg_client.timezone,
                    truncate_text_flag=True,
                )
                messages.append(formatted)

            if not messages:
                return SkillResult.ok(f"No messages found for query '{query}' in this chat.")

            messages.reverse()
            return SkillResult.ok(
                f"Search results for query '{query}':\n\n" + "\n\n".join(messages)
            )

        except Exception as e:
            return SkillResult.fail(f"Error searching messages: {e}")

    @skill()
    async def edit_draft(
        self, chat_id: Union[int, str], text: str, append: bool = True
    ) -> SkillResult:
        """
        Updates chat draft.
        Appends if append=True.
        """

        try:
            client = self.tg_client.client()
            target_entity = await client.get_entity(parse_int_or_str(chat_id))

            current_text = ""
            if append:
                drafts = await client.get_drafts()
                for d in drafts:
                    if getattr(d.entity, "id", None) == target_entity.id:
                        current_text = d.text
                        break

            final_text = f"{current_text}\n\n{text}".strip() if current_text else text

            await client(
                SaveDraftRequest(
                    peer=await client.get_input_entity(target_entity), message=final_text
                )
            )

            return SkillResult.ok("True")

        except Exception as e:
            return SkillResult.fail(f"Error saving draft: {e}")

    @skill()
    async def delete_draft(self, chat_id: Union[int, str]) -> SkillResult:
        """
        Deletes chat draft.
        """

        try:
            client = self.tg_client.client()
            target_entity = await client.get_entity(parse_int_or_str(chat_id))

            await client(
                SaveDraftRequest(peer=await client.get_input_entity(target_entity), message="")
            )
            return SkillResult.ok("True")

        except Exception as e:
            return SkillResult.fail(f"Error deleting draft: {e}")
