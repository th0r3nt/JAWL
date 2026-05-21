"""
Telethon Admin Skills.

Provides group and channel administration capabilities: creating channels, modifying titles,
descriptions, managing Forums (Topics), exporting invite links, and modifying permissions/promotions.
"""

from typing import Union

from telethon import utils
from telethon.tl.functions.channels import (
    CreateChannelRequest,
    EditTitleRequest,
    UpdateUsernameRequest,
    SetDiscussionGroupRequest,
)
from telethon.tl.functions.channels import EditPhotoRequest as ChannelEditPhotoRequest
from telethon.tl.functions.messages import ExportChatInviteRequest, EditChatTitleRequest
from telethon.tl.functions.messages import EditChatAboutRequest, EditChatPhotoRequest
from telethon.tl.types import InputChatUploadedPhoto, InputPeerChannel, InputPeerChat

from src.utils._tools import validate_sandbox_path, parse_int_or_str
from src.utils.logger import main_logger
from src.l2_interfaces.telegram.telethon.client import TelethonClient
from src.l3_agent.skills.registry import SkillResult, skill

try:
    from telethon.tl.functions.channels import CreateForumTopicRequest
except ImportError:
    CreateForumTopicRequest = None


class TelethonAdmin:
    """Group and channel administration tools."""

    def __init__(self, tg_client: TelethonClient) -> None:
        self.tg_client = tg_client

    @skill()
    async def create_channel(
        self, title: str, about: str = "", is_megagroup: bool = False
    ) -> SkillResult:
        """
        Creates new private channel or supergroup.
        """
        try:
            client = self.tg_client.client()
            result = await client(
                CreateChannelRequest(title=title, about=about, megagroup=is_megagroup)
            )

            chat_id = f"-100{result.chats[0].id}"
            chat_type = "Supergroup" if is_megagroup else "Channel"

            msg = f"{chat_type} '{title}' successfully created. ID: {chat_id}"
            main_logger.info(f"[Telegram Telethon] {msg}")
            return SkillResult.ok(f"True. ID: {chat_id}")

        except Exception as e:
            return SkillResult.fail(f"Error creating chat: {e}")

    @skill()
    async def set_channel_username(
        self, chat_id: Union[int, str], username: str
    ) -> SkillResult:
        """
        Sets public username for channel/group.
        Pass empty string to make private.
        """

        try:
            client = self.tg_client.client()
            entity = await client.get_input_entity(parse_int_or_str(chat_id))

            clean_username = username.strip().lstrip("@")

            await client(UpdateUsernameRequest(channel=entity, username=clean_username))

            if clean_username:
                main_logger.info(
                    f"[Telegram Telethon] Channel {chat_id} is now public (@{clean_username})"
                )
                return SkillResult.ok(f"True. URL: t.me/{clean_username}")
            else:
                main_logger.info(f"[Telegram Telethon] Channel {chat_id} is now private")
                return SkillResult.ok("True")

        except ValueError:
            return SkillResult.fail("Error: Invalid chat ID.")
        except Exception as e:
            return SkillResult.fail(f"Error setting public link username: {e}")

    @skill()
    async def set_discussion_group(
        self, channel_id: Union[int, str], group_id: Union[int, str]
    ) -> SkillResult:
        """
        Links supergroup to channel as discussion group.
        Pass empty group_id to unlink.
        """

        try:
            client = self.tg_client.client()
            channel_entity = await client.get_input_entity(parse_int_or_str(channel_id))

            if not group_id or str(group_id).strip() == "":
                from telethon.tl.types import InputChannelEmpty

                group_entity = InputChannelEmpty()
            else:
                group_entity = await client.get_input_entity(parse_int_or_str(group_id))

            await client(
                SetDiscussionGroupRequest(broadcast=channel_entity, group=group_entity)
            )

            action_str = "linked to channel" if group_id else "unlinked from channel"
            msg = f"Supergroup successfully {action_str} {channel_id}."
            main_logger.info(f"[Telegram Telethon] {msg}")

            return SkillResult.ok("True")

        except ValueError:
            return SkillResult.fail("Error: Invalid channel or group ID.")
        except Exception as e:
            return SkillResult.fail(f"Error binding discussion group: {e}")

    @skill()
    async def edit_chat_title(self, chat_id: Union[int, str], new_title: str) -> SkillResult:
        """
        Changes channel/group title.
        """

        try:
            client = self.tg_client.client()
            entity = await client.get_entity(parse_int_or_str(chat_id))

            try:
                await client(EditTitleRequest(channel=entity, title=new_title))
            except Exception:
                await client(EditChatTitleRequest(chat_id=entity.id, title=new_title))

            main_logger.info(
                f"[Telegram Telethon] Chat {chat_id} title changed to '{new_title}'"
            )
            return SkillResult.ok("True")

        except ValueError:
            return SkillResult.fail("Error: Invalid chat ID.")
        except Exception as e:
            return SkillResult.fail(f"Error changing chat title: {e}")

    @skill()
    async def edit_chat_description(
        self, chat_id: Union[int, str], new_description: str
    ) -> SkillResult:
        """
        Changes channel/group description (bio).
        """

        try:
            client = self.tg_client.client()
            entity = await client.get_input_entity(parse_int_or_str(chat_id))

            await client(EditChatAboutRequest(peer=entity, about=new_description))

            main_logger.info(f"[Telegram Telethon] Chat {chat_id} description updated.")
            return SkillResult.ok("True")
        except ValueError:
            return SkillResult.fail("Error: Invalid chat ID.")
        except Exception as e:
            return SkillResult.fail(f"Error updating chat description: {e}")

    @skill()
    async def edit_chat_avatar(self, chat_id: Union[int, str], filepath: str) -> SkillResult:
        """
        Sets new chat avatar from sandbox/ filepath.
        """

        try:
            safe_path = validate_sandbox_path(filepath)
            if not safe_path.is_file():
                return SkillResult.fail(f"Error: Avatar file {safe_path.name} not found.")

            client = self.tg_client.client()
            entity = await client.get_input_entity(parse_int_or_str(chat_id))

            uploaded_file = await client.upload_file(str(safe_path))
            photo = InputChatUploadedPhoto(file=uploaded_file)

            if isinstance(entity, InputPeerChannel):
                await client(ChannelEditPhotoRequest(channel=entity, photo=photo))
            elif isinstance(entity, InputPeerChat):
                await client(EditChatPhotoRequest(chat_id=entity.chat_id, photo=photo))
            else:
                return SkillResult.fail(
                    "Error: This chat type does not support avatar updates."
                )

            main_logger.info(
                f"[Telegram Telethon] Chat {chat_id} avatar updated to {safe_path.name}"
            )
            return SkillResult.ok("True")

        except PermissionError as e:
            return SkillResult.fail(str(e))
        except ValueError:
            return SkillResult.fail("Error: Invalid chat ID.")
        except Exception as e:
            return SkillResult.fail(f"Error updating chat avatar: {e}")

    @skill()
    async def create_invite_link(self, chat_id: Union[int, str]) -> SkillResult:
        """
        Generates new invite link for private chat.
        """

        try:
            client = self.tg_client.client()
            entity = await client.get_input_entity(parse_int_or_str(chat_id))

            result = await client(ExportChatInviteRequest(peer=entity))

            return SkillResult.ok(f"Invite link generated: {result.link}")

        except Exception as e:
            return SkillResult.fail(f"Error exporting invite link: {e}")

    @skill()
    async def get_participants(
        self, chat_id: Union[int, str], limit: int = 100
    ) -> SkillResult:
        """
        Fetches participant list of group/channel.
        Requires admin rights.
        """

        try:
            client = self.tg_client.client()
            entity = await client.get_entity(parse_int_or_str(chat_id))

            participants = []
            async for user in client.iter_participants(entity, limit=limit):
                name = utils.get_display_name(user) or "Unknown"
                bot_tag = " [Bot]" if user.bot else ""
                participants.append(f"- ID: `{user.id}` | Name: {name}{bot_tag}")

            if not participants:
                return SkillResult.ok(
                    "Participants list is empty (or permissions are insufficient)."
                )

            return SkillResult.ok(
                f"Participants (Recent {limit}):\n" + "\n".join(participants)
            )

        except Exception as e:
            return SkillResult.fail(f"Error fetching participants: {e}")

    @skill()
    async def promote_user(
        self, chat_id: Union[int, str], user_id: Union[int, str], add_admins: bool = False
    ) -> SkillResult:
        """
        Promotes user to administrator.
        add_admins: if True, grants add-admin rights.
        """

        try:
            client = self.tg_client.client()

            await client.edit_admin(
                entity=parse_int_or_str(chat_id),
                user=parse_int_or_str(user_id),
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

            return SkillResult.ok("True")

        except Exception as e:
            return SkillResult.fail(f"Error promoting user to admin: {e}")

    @skill()
    async def demote_user(
        self, chat_id: Union[int, str], user_id: Union[int, str]
    ) -> SkillResult:
        """
        Demotes administrator to regular user.
        """

        try:
            client = self.tg_client.client()

            await client.edit_admin(
                entity=parse_int_or_str(chat_id),
                user=parse_int_or_str(user_id),
                is_admin=False,
            )

            return SkillResult.ok("True")

        except Exception as e:
            return SkillResult.fail(f"Error demoting administrator: {e}")

    @skill()
    async def pin_message(
        self, chat_id: Union[int, str], message_id: int, notify: bool = True
    ) -> SkillResult:
        """
        Pins specific message in chat.
        """

        try:
            client = self.tg_client.client()
            await client.pin_message(
                entity=parse_int_or_str(chat_id), message=int(message_id), notify=notify
            )

            main_logger.info(f"[Telegram Telethon] Message {message_id} pinned in {chat_id}")
            return SkillResult.ok("True")

        except Exception as e:
            return SkillResult.fail(f"Error pinning message: {e}")

    @skill()
    async def unpin_message(self, chat_id: Union[int, str], message_id: int) -> SkillResult:
        """
        Unpins message in chat.
        """

        try:
            client = self.tg_client.client()
            await client.unpin_message(
                entity=parse_int_or_str(chat_id), message=int(message_id)
            )

            main_logger.info(f"[Telegram Telethon] Message {message_id} unpinned in {chat_id}")
            return SkillResult.ok("True")

        except Exception as e:
            return SkillResult.fail(f"Error unpinning message: {e}")

    @skill()
    async def create_topic(self, chat_id: Union[int, str], title: str) -> SkillResult:
        """
        Creates new topic in forum-enabled group.
        """

        if not CreateForumTopicRequest:
            return SkillResult.fail(
                "Error: Telethon library version does not support Forum Topics."
            )

        try:
            client = self.tg_client.client()
            entity = await client.get_input_entity(parse_int_or_str(chat_id))

            result = await client(CreateForumTopicRequest(channel=entity, title=title))

            topic_id = None
            for update in result.updates:
                if hasattr(update, "message") and hasattr(update.message, "id"):
                    topic_id = update.message.id
                    break

            if not topic_id:
                return SkillResult.fail(
                    "Topic created, but failed to extract topic ID from response updates."
                )

            msg = f"Topic '{title}' created successfully. Topic ID: {topic_id}"
            main_logger.info(f"[Telegram Telethon] {msg} (chat {chat_id})")
            return SkillResult.ok(f"True. ID: {topic_id}")

        except ValueError:
            return SkillResult.fail("Error: Invalid chat ID.")

        except Exception as e:
            if "CHAT_NOT_MODIFIED" in str(e) or "not a forum" in str(e).lower():
                return SkillResult.fail(
                    "Error: Target group is not a forum (topics are not enabled)."
                )
            return SkillResult.fail(f"Error creating forum topic: {e}")
