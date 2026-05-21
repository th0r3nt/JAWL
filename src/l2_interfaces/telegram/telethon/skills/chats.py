"""
Telethon Chats Skills.

Provides dialogue lists navigation, history extraction, unread message clearing,
and channel subscription management skills.
"""

import re
from typing import Optional, Union, Any

from telethon.tl.functions.contacts import SearchRequest
from telethon.tl.functions.channels import (
    JoinChannelRequest,
    LeaveChannelRequest,
    GetFullChannelRequest,
    InviteToChannelRequest,
)
from telethon.tl.functions.messages import (
    ImportChatInviteRequest,
    GetPeerDialogsRequest,
    ReadMentionsRequest,
    GetFullChatRequest,
)

from src.utils.logger import main_logger
from src.utils._tools import parse_int_or_str

from src.l2_interfaces.telegram.telethon.client import TelethonClient
from src.l2_interfaces.telegram.telethon.utils._message_parser import TelethonMessageParser
from src.l3_agent.skills.registry import SkillResult, skill

try:
    from telethon.tl.functions.channels import GetForumTopicsRequest
except ImportError:
    GetForumTopicsRequest = None

try:
    from telethon.tl.functions.messages import ReadReactionsRequest
except ImportError:
    ReadReactionsRequest = None


class TelethonChats:
    """Dialogue and channel management skills."""

    def __init__(self, tg_client: TelethonClient) -> None:
        self.tg_client = tg_client

    @skill()
    async def get_chats(self, limit: int = 10) -> SkillResult:
        """
        Returns list of recent chats sorted by activity.
        """

        try:
            client = self.tg_client.client()
            chats = []

            total_dialogs = 0
            try:
                d_info = await client.get_dialogs(limit=0)
                total_dialogs = getattr(d_info, "total", 0)
            except Exception:
                pass

            async for dialog in client.iter_dialogs(limit=limit):
                chat_type = (
                    "User" if dialog.is_user else "Group" if dialog.is_group else "Channel"
                )
                unread = f" [UNREAD: {dialog.unread_count}]" if dialog.unread_count > 0 else ""

                forum_str = ""
                if getattr(dialog.entity, "forum", False):
                    chat_type = "Forum"
                    topics_list = []
                    try:
                        topics_data = await self._get_topics(client, dialog.entity, limit=10)
                        for topic in topics_data:
                            t_unread = (
                                f" (UNREAD: {topic.unread_count})"
                                if getattr(topic, "unread_count", 0) > 0
                                else ""
                            )
                            topics_list.append(
                                f"      ↳ Topic '{getattr(topic, 'title', 'Unknown')}' (ID: {topic.id}){t_unread}"
                            )
                    except Exception as e:
                        main_logger.error(f"[TelethonChats] Error fetching topics: {e}")

                    if not topics_list and dialog.unread_count > 0:
                        topics_list.append(
                            f"      ↳ General / Other topics (UNREAD: {dialog.unread_count})"
                        )

                    if topics_list:
                        forum_str = "\n" + "\n".join(topics_list)

                chats.append(
                    f"- {chat_type} | ID: `{dialog.id}` | Title: {dialog.name}{unread}{forum_str}"
                )

            if not chats:
                return SkillResult.ok("Dialogue list is empty.")

            res_str = "\n".join(chats)
            if total_dialogs > len(chats):
                hidden = total_dialogs - len(chats)
                res_str += (
                    f"\n\n...and {hidden} more chats hidden. Increase limit to load more."
                )

            return SkillResult.ok(res_str)

        except Exception as e:
            return SkillResult.fail(f"Error retrieving chats list: {e}")

    @skill()
    async def get_unread_chats(self, limit: int = 20) -> SkillResult:
        """
        Returns list of unread chats.
        """

        try:
            client = self.tg_client.client()
            chats = []

            async for dialog in client.iter_dialogs(limit=limit):
                if dialog.unread_count > 0:
                    chat_type = (
                        "User" if dialog.is_user else "Group" if dialog.is_group else "Channel"
                    )
                    forum_str = ""

                    if getattr(dialog.entity, "forum", False):
                        chat_type = "Forum"
                        topics_list = []
                        try:
                            topics_data = await self._get_topics(
                                client, dialog.entity, limit=100
                            )
                            for topic in topics_data:
                                unread = getattr(topic, "unread_count", 0)
                                if unread > 0:
                                    topics_list.append(
                                        f"      ↳ Topic '{getattr(topic, 'title', 'Unknown')}' (ID: {topic.id}) [UNREAD: {unread}]"
                                    )
                        except Exception:
                            pass

                        if not topics_list:
                            topics_list.append(
                                f"      ↳ General / Other topics [UNREAD: {dialog.unread_count}]"
                            )
                        forum_str = "\n" + "\n".join(topics_list)

                    chats.append(
                        f"- {chat_type} | ID: `{dialog.id}` | Title: **{dialog.name}** | UNREAD: {dialog.unread_count}{forum_str}"
                    )

            if not chats:
                return SkillResult.ok("No unread messages.")

            return SkillResult.ok("\n".join(chats))

        except Exception as e:
            return SkillResult.fail(f"Error checking unread chats: {e}")

    @skill()
    async def read_chat(
        self, chat_id: Union[int, str], limit: int = 10, topic_id: Optional[int] = None
    ) -> SkillResult:
        """
        Reads chat history without removing Unread flag.
        """
        try:
            client = self.tg_client.client()
            target_entity = await client.get_entity(parse_int_or_str(chat_id))

            read_outbox_max_id = 0
            try:
                peer_dialogs = await client(GetPeerDialogsRequest(peers=[target_entity]))
                if peer_dialogs and peer_dialogs.dialogs:
                    read_outbox_max_id = peer_dialogs.dialogs[0].read_outbox_max_id
            except Exception:
                pass

            messages = []
            kwargs = {"limit": limit}
            if topic_id:
                kwargs["reply_to"] = int(topic_id)

            async for msg in client.iter_messages(target_entity, **kwargs):
                formatted = await TelethonMessageParser.build_string(
                    client=client,
                    target_entity=target_entity,
                    msg=msg,
                    timezone=self.tg_client.timezone,
                    topic_id=topic_id,
                    read_outbox_max_id=read_outbox_max_id,
                )
                messages.append(formatted)

            draft_text = ""
            try:
                drafts = await client.get_drafts()
                for d in drafts:
                    if getattr(d.entity, "id", None) == target_entity.id:
                        if topic_id and getattr(d, "reply_to_msg_id", None) != int(topic_id):
                            continue
                        if d.text:
                            draft_text = f"\n\n[Draft (Unsent message)]:\n{d.text}"
                        break
            except Exception:
                pass

            if not messages:
                base_msg = (
                    "No messages in this topic." if topic_id else "No messages in this chat."
                )
                return SkillResult.ok(base_msg + draft_text)

            messages.reverse()
            return SkillResult.ok("\n\n".join(messages) + draft_text)

        except ValueError:
            return SkillResult.fail(f"Error: Invalid chat ID ({chat_id}).")
        except Exception as e:
            return SkillResult.fail(f"Error reading chat {chat_id}: {e}")

    @skill()
    async def mark_as_read(
        self, chat_id: Union[int, str], topic_id: Optional[int] = None
    ) -> SkillResult:
        """
        Marks all messages in chat as read.
        """

        try:
            client = self.tg_client.client()
            target_entity = await client.get_entity(parse_int_or_str(chat_id))

            if getattr(target_entity, "forum", False) and not topic_id:
                try:
                    topics_data = await self._get_topics(client, target_entity, limit=100)
                    for topic in topics_data:
                        if getattr(topic, "unread_count", 0) > 0:
                            await self._mark_chat_read(client, target_entity, topic.id)
                except Exception as e:
                    main_logger.error(f"[TelethonChats] Error clearing thread unreads: {e}")

                await self._mark_chat_read(client, target_entity)
            else:
                await self._mark_chat_read(client, target_entity, topic_id)

            return SkillResult.ok("True")

        except Exception as e:
            return SkillResult.fail(f"Error marking chat {chat_id} as read: {e}")

    @skill()
    async def search_public_chats(self, query: str, limit: int = 5) -> SkillResult:
        """
        Performs global Telegram search for public groups/channels.
        """

        try:
            client = self.tg_client.client()
            result = await client(SearchRequest(q=query, limit=limit))

            chats = []
            for chat in result.chats:
                chat_type = "Channel" if getattr(chat, "broadcast", False) else "Group"
                username = f"@{chat.username}" if getattr(chat, "username", None) else "None"
                participants = getattr(chat, "participants_count", None)
                part_str = (
                    f" | Subscribers: {participants}" if participants is not None else ""
                )

                chats.append(
                    f"- {chat_type} | ID: `{chat.id}` | Title: {chat.title} | Username: {username}{part_str}"
                )

            if not chats:
                return SkillResult.ok(f"No global search results found for query '{query}'.")

            return SkillResult.ok("\n".join(chats))

        except Exception as e:
            return SkillResult.fail(f"Error searching chats: {e}")

    @skill()
    async def get_chat_info(self, chat_id: Union[int, str]) -> SkillResult:
        """
        Returns extended chat information.
        """

        try:
            client = self.tg_client.client()
            entity = await client.get_entity(parse_int_or_str(chat_id))

            lines = [f"Chat information for {chat_id}:"]
            lines.append(f"Title: {getattr(entity, 'title', 'Unknown')}")

            if getattr(entity, "username", None):
                lines.append(f"Username: @{entity.username}")

            try:
                if getattr(entity, "broadcast", False) or getattr(entity, "megagroup", False):
                    full = await client(GetFullChannelRequest(channel=entity))
                    lines.append(
                        f"Type: {'Channel' if getattr(entity, 'broadcast', False) else 'Supergroup'}"
                    )
                    if full.full_chat.about:
                        lines.append(f"Description: {full.full_chat.about}")
                    lines.append(
                        f"Participants (subscribers): {full.full_chat.participants_count}"
                    )
                elif hasattr(entity, "participants_count"):
                    full = await client(GetFullChatRequest(chat_id=entity.id))
                    lines.append("Type: Group")
                    if full.full_chat.about:
                        lines.append(f"Description: {full.full_chat.about}")
                    lines.append(f"Participants: {full.full_chat.participants_count}")
            except Exception:
                if (
                    hasattr(entity, "participants_count")
                    and entity.participants_count is not None
                ):
                    lines.append(f"Participants: {entity.participants_count}")

            return SkillResult.ok("\n".join(lines))

        except ValueError:
            return SkillResult.fail("Error: Invalid chat ID or username.")
        except Exception as e:
            return SkillResult.fail(f"Error fetching chat info: {e}")

    @skill()
    async def join_chat(self, link_or_username: str) -> SkillResult:
        """
        Joins public or private chat by username or invite link.
        """

        try:
            client = self.tg_client.client()
            target = link_or_username.strip()

            if "t.me/+" in target or "t.me/joinchat/" in target or target.startswith("+"):
                hash_match = re.search(r"(?:joinchat/|\+)([\w-]+)", target)
                if not hash_match:
                    return SkillResult.fail("Error: Failed to extract hash from invite link.")
                await client(ImportChatInviteRequest(hash_match.group(1)))
            else:
                await client(JoinChannelRequest(target))

            return SkillResult.ok("True")

        except Exception as e:
            if "USER_ALREADY_PARTICIPANT" in str(e):
                return SkillResult.ok("True")
            return SkillResult.fail(f"Error joining chat: {e}")

    @skill()
    async def leave_chat(self, chat_id: Union[int, str]) -> SkillResult:
        """
        Leaves channel/group.
        """

        try:
            client = self.tg_client.client()
            entity = await client.get_input_entity(parse_int_or_str(chat_id))
            await client(LeaveChannelRequest(entity))
            return SkillResult.ok("True")
        except ValueError:
            return SkillResult.fail("Error: Invalid chat ID.")
        except Exception as e:
            return SkillResult.fail(f"Error leaving chat: {e}")

    @skill()
    async def join_channel_discussion(self, channel_id: Union[int, str]) -> SkillResult:
        """
        Joins discussion supergroup linked to specified channel.
        """

        try:
            client = self.tg_client.client()
            target_entity = await client.get_input_entity(parse_int_or_str(channel_id))
            full_channel = await client(GetFullChannelRequest(target_entity))
            linked_chat_id = full_channel.full_chat.linked_chat_id

            if not linked_chat_id:
                return SkillResult.fail(
                    f"Error: Channel {channel_id} has no linked discussion group."
                )

            await client(JoinChannelRequest(await client.get_input_entity(linked_chat_id)))

            return SkillResult.ok("True")

        except ValueError:
            return SkillResult.fail("Error: Invalid channel ID.")
        except Exception as e:
            if "USER_ALREADY_PARTICIPANT" in str(e):
                return SkillResult.ok("True")
            return SkillResult.fail(f"Error joining channel discussion: {e}")

    @skill()
    async def invite_to_chat(
        self, chat_id: Union[int, str], users: list[Union[int, str]]
    ) -> SkillResult:
        """
        Invites users to group/channel.
        """

        if not users:
            return SkillResult.fail("Error: User list is empty.")

        try:
            client = self.tg_client.client()
            chat_entity = await client.get_input_entity(parse_int_or_str(chat_id))

            user_entities = []
            for u in users:
                try:
                    user_entities.append(await client.get_input_entity(parse_int_or_str(u)))
                except ValueError:
                    return SkillResult.fail(f"Error: User '{u}' not found. Verify username.")

            await client(InviteToChannelRequest(channel=chat_entity, users=user_entities))

            return SkillResult.ok("True")

        except Exception as e:
            msg = str(e)
            if "USER_PRIVACY_RESTRICTED" in msg:
                return SkillResult.fail(
                    "Error: Target user's privacy settings restrict adding them."
                )
            if "CHAT_ADMIN_REQUIRED" in msg:
                return SkillResult.fail(
                    "Error: Admin rights required to invite users in this chat."
                )
            if "USER_ALREADY_PARTICIPANT" in msg:
                return SkillResult.ok("True")
            if "USER_NOT_MUTUAL_CONTACT" in msg:
                return SkillResult.fail(
                    "Error: User can only be invited if you are mutual contacts."
                )
            return SkillResult.fail(f"Error adding users to chat: {e}")

    # ===============================================================
    # Internal methods
    # ===============================================================

    async def _get_topics(self, client: Any, entity: Any, limit: int = 100) -> list:
        """Auxiliary method to fetch Forum topic structures."""

        if not GetForumTopicsRequest:
            return []
        try:
            result = await client(
                GetForumTopicsRequest(
                    channel=entity,
                    q="",
                    offset_date=0,
                    offset_id=0,
                    offset_topic=0,
                    limit=limit,
                )
            )
            return getattr(result, "topics", [])
        except Exception as e:
            main_logger.error(f"[TelethonChats] Error calling _get_topics: {e}")
            return []

    async def _mark_chat_read(
        self, client: Any, target_entity: Any, topic_id: Optional[int] = None
    ) -> None:
        """Auxiliary method: clears UNREAD, mentions, and reactions in chat/topic."""

        try:
            kwargs_ack = {"reply_to": int(topic_id)} if topic_id else {}
            await client.send_read_acknowledge(target_entity, **kwargs_ack)

            if topic_id:
                await client(ReadMentionsRequest(peer=target_entity, top_msg_id=int(topic_id)))
                if ReadReactionsRequest:
                    await client(
                        ReadReactionsRequest(peer=target_entity, top_msg_id=int(topic_id))
                    )
            else:
                await client(ReadMentionsRequest(peer=target_entity))
                if ReadReactionsRequest:
                    await client(ReadReactionsRequest(peer=target_entity))

        except Exception as e:
            main_logger.debug(f"[TelethonChats] Error clearing mentions/reactions: {e}")
