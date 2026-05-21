"""
Event listener (Events Poller) for Telethon.

Powerful orchestrator of incoming data (MTProto Updates).
Intercepts DMs, mentions, system events, and reactions.
Manages dialogue MRU-cache, calculates "UNREAD" statuses, and dynamically pulls
chat history (up to 50 messages) to create deep context in EventBus.
"""

import time
from typing import Any, TYPE_CHECKING, Dict, Tuple, List

from telethon import events, utils
from telethon.tl.types import UpdateMessageReactions, Channel, Chat
from telethon.tl.functions.channels import GetFullChannelRequest
from telethon.tl.functions.messages import GetFullChatRequest, GetPeerDialogsRequest
from telethon.errors import FloodWaitError

from src.utils._tools import truncate_text
from src.utils.logger import main_logger, agent_logger
from src.utils.event.bus import EventBus
from src.utils.event.registry import Events

if TYPE_CHECKING:
    from src.utils.settings import TelethonConfig

from src.l2_interfaces.telegram.telethon.state import TelethonState
from src.l2_interfaces.telegram.telethon.client import TelethonClient
from src.l2_interfaces.telegram.telethon.utils._message_parser import TelethonMessageParser


class TelethonEvents:
    """
    Background worker-listener of Telethon events.
    """

    def __init__(
        self,
        tg_client: TelethonClient,
        state: TelethonState,
        event_bus: EventBus,
        config: "TelethonConfig",
    ) -> None:
        """
        Initializes the event manager.

        Args:
            tg_client (TelethonClient): Client instance.
            state (TelethonState): L0 state.
            event_bus (EventBus): JAWL event bus.
            config (TelethonConfig): Config with limits.
        """

        self.tg_client = tg_client
        self.state = state
        self.bus = event_bus
        self.config = config

        # Spam protection (rate limiter for state updates)
        self._last_state_update = 0.0

        # Chat descriptions cache. Saves from FloodWaitError by not making FullChatRequest on every breath.
        self._chat_desc_cache: Dict[int, str] = {}

    async def start(self) -> None:
        """Registers handlers on the Telethon socket and performs initial state gathering."""
        client = self.tg_client.client()
        await self._update_state(force=True)

        client.add_event_handler(
            self._on_private_message,
            events.NewMessage(incoming=True, func=lambda e: e.is_private),
        )
        client.add_event_handler(
            self._on_group_message,
            events.NewMessage(incoming=True, func=lambda e: e.is_group),
        )
        client.add_event_handler(
            self._on_channel_message,
            events.NewMessage(incoming=True, func=lambda e: e.is_channel and not e.is_group),
        )
        client.add_event_handler(self._on_chat_action, events.ChatAction())
        client.add_event_handler(self._on_reaction, events.Raw())
        client.add_event_handler(self._on_outgoing_message, events.NewMessage(outgoing=True))

        main_logger.info("[Telegram Telethon] Event listeners successfully started.")

    async def stop(self) -> None:
        """Stops event processing."""
        main_logger.info("[Telegram Telethon] Event listeners successfully stopped.")

    # ==========================================================
    # STATE DASHBOARD BUILDERS (L0 State)
    # ==========================================================

    async def _update_state(self, force: bool = False) -> None:
        """
        Orchestrator of the active chats dashboard update.
        Queries the list of dialogues and delegates their parsing to specialized methods.

        Args:
            force (bool): Ignore rate limiter (3 sec) and update immediately.
        """
        now = time.time()
        if not force and now - self._last_state_update < 3:
            return

        self._last_state_update = now
        client = self.tg_client.client()

        overview_lines = []
        unread_blocks = []

        try:
            total_dialogs = 0
            try:
                d_info = await client.get_dialogs(limit=0)
                total_dialogs = getattr(d_info, "total", 0)
            except Exception:
                pass

            async for dialog in client.iter_dialogs(limit=self.state.number_of_last_chats):
                entity = dialog.entity

                is_public = bool(getattr(entity, "username", None))
                status_str = "Public" if is_public else "Private"
                participants = getattr(entity, "participants_count", None)
                part_str = f" | {participants} people" if participants else ""
                unread_str = (
                    f" [UNREAD: {dialog.unread_count}]" if dialog.unread_count > 0 else ""
                )

                if dialog.is_user:
                    overview_line, unread_block = await self._process_user_dialog(
                        client, dialog, entity, unread_str
                    )
                    overview_lines.append(overview_line)
                    if unread_block:
                        unread_blocks.append(unread_block)

                elif dialog.is_group or dialog.is_channel:
                    desc_str = await self._get_entity_description(client, entity)
                    overview_line = await self._process_group_dialog(
                        client, dialog, entity, status_str, unread_str, part_str, desc_str
                    )
                    overview_lines.append(overview_line)

            self.state.last_chats = self._build_markdown_dashboard(
                unread_blocks, overview_lines, total_dialogs
            )

        except Exception as e:
            main_logger.error(f"[Telethon] Error updating state: {e}")

    async def _get_entity_description(self, client: Any, entity: Any) -> str:
        """Extracts and caches group/channel description."""
        if entity.id not in self._chat_desc_cache:
            try:
                about = ""
                if isinstance(entity, Channel):
                    full = await client(GetFullChannelRequest(channel=entity))
                    about = full.full_chat.about or ""
                elif isinstance(entity, Chat):
                    full = await client(GetFullChatRequest(chat_id=entity.id))
                    about = full.full_chat.about or ""
                self._chat_desc_cache[entity.id] = about.strip()
            except FloodWaitError:
                pass
            except Exception:
                self._chat_desc_cache[entity.id] = ""

        desc = self._chat_desc_cache.get(entity.id, "")
        if desc:
            clean_desc = desc.replace("\n", " ")
            return f" | Description: {truncate_text(clean_desc, 100, '... [Truncated]')}"
        return ""

    async def _process_user_dialog(
        self, client: Any, dialog: Any, entity: Any, unread_str: str
    ) -> Tuple[str, str]:
        """Processes DMs, fetching unread messages history if necessary."""

        bot_tag = " [Bot]" if getattr(entity, "bot", False) else ""
        overview_line = f"- [User] {dialog.name}{bot_tag} (ID: `{dialog.id}`){unread_str}"

        unread_block = ""
        if dialog.unread_count > 0:
            fetch_limit = max(2, min(dialog.unread_count, self.config.incoming_history_limit))
            try:
                recent_msgs = await client.get_messages(entity, limit=fetch_limit)
                if recent_msgs:
                    block = f"[User] {dialog.name}{bot_tag} (ID: {dialog.id}) [UNREAD: {dialog.unread_count}]:\n    Last {len(recent_msgs)} messages:"
                    msg_lines = []
                    for m in reversed(recent_msgs):
                        formatted = await TelethonMessageParser.build_string(
                            client=client,
                            target_entity=entity,
                            msg=m,
                            timezone=self.tg_client.timezone,
                            truncate_text_flag=True,
                        )
                        indented = "\n".join(
                            [f"        {line}" for line in formatted.split("\n")]
                        )
                        msg_lines.append(indented)
                    unread_block = block + "\n\n" + "\n\n".join(msg_lines)
            except Exception as e:
                main_logger.debug(f"[Telethon] Error loading history for {dialog.id}: {e}")

        return overview_line, unread_block

    async def _process_group_dialog(
        self,
        client: Any,
        dialog: Any,
        entity: Any,
        status_str: str,
        unread_str: str,
        part_str: str,
        desc_str: str,
    ) -> str:
        """Processes groups and channels, including Forum (topic) parsing logic."""
        chat_type = "Group" if dialog.is_group else "Channel"
        forum_str = ""

        if getattr(entity, "forum", False):
            chat_type = "Forum"
            topics_list = []
            try:
                topics_data = await self._get_topics(client, entity, limit=10)
                for topic in topics_data:
                    t_unread = (
                        f" (UNREAD: {topic.unread_count})"
                        if getattr(topic, "unread_count", 0) > 0
                        else ""
                    )
                    topics_list.append(
                        f"      ↳ Topic '{getattr(topic, 'title', 'Unknown')}' (ID: {topic.id}){t_unread}"
                    )
            except Exception:
                pass

            if not topics_list and dialog.unread_count > 0:
                topics_list.append(
                    f"      ↳ General / Main Topic (UNREAD: {dialog.unread_count})"
                )
            if topics_list:
                forum_str = "\n" + "\n".join(topics_list)

        return f"- [{status_str} {chat_type}] {dialog.name} (ID: `{dialog.id}`){part_str}{desc_str}{unread_str}{forum_str}"

    def _build_markdown_dashboard(
        self, unread_blocks: List[str], overview_lines: List[str], total_dialogs: int
    ) -> str:
        """Formats the Markdown representation of active dialogues."""
        res_str = ""
        if unread_blocks:
            res_str += "REQUIRED ATTENTION (Unread private messages):\n"
            res_str += "\n\n".join(unread_blocks)
            res_str += "\n\n---\n\n"

        if overview_lines:
            res_str += "RECENT DIALOGUES (General list):\n"
            res_str += "\n".join(overview_lines)
            if total_dialogs > len(overview_lines):
                hidden = total_dialogs - len(overview_lines)
                res_str += (
                    f"\n\n...and {hidden} more chats hidden. Increase limit to load more."
                )
        else:
            res_str += "Dialogues list is empty."

        return res_str

    # ==========================================================
    # HANDLERS
    # ==========================================================

    async def _on_outgoing_message(self, event: events.NewMessage.Event) -> None:
        """Trigger on outgoing (our) messages: force state update."""
        await self._update_state(force=True)

    async def _on_private_message(self, event: events.NewMessage.Event) -> None:
        """Intercepts DMs. Dynamically pulls chat context (history)."""
        await self._update_state(force=True)

        client = self.tg_client.client()
        msg_obj = event.message

        sender_name = await TelethonMessageParser.get_sender_name(msg_obj)
        chat = await event.get_chat()
        chat_name = utils.get_display_name(chat) if chat else "Unknown"

        fwd_info = await TelethonMessageParser.parse_forward(msg_obj)
        is_reply, reply_id = TelethonMessageParser.determine_reply(msg_obj, None)
        reply_info = await TelethonMessageParser.parse_reply(client, chat, is_reply, reply_id)

        media_tag = TelethonMessageParser.parse_media(msg_obj)
        msg_text = msg_obj.text or ""
        base_text = f"{media_tag} {msg_text}".strip() if media_tag else msg_text

        enriched_message = f"{base_text}{fwd_info}{reply_info}".strip()

        # Dynamic calculation of messages history
        unread_count = await self._get_unread_count(chat)
        limit = min(50, max(self.config.incoming_history_limit, unread_count))
        history = await self._fetch_recent_history(chat, limit=limit)

        payload = {
            "message": enriched_message,
            "raw_text": msg_text,
            "sender_name": sender_name,
            "chat_name": chat_name,
            "chat_id": event.chat_id,
            "msg_id": msg_obj.id,
        }
        if history:
            payload["recent_history"] = history

        await self.bus.publish(Events.TELETHON_MESSAGE_INCOMING, **payload)

    async def _on_group_message(self, event: events.NewMessage.Event) -> None:
        """Intercepts group messages. Resolves threads (Topics) on forums."""
        if event.mentioned:
            event_type = Events.TELETHON_GROUP_MENTION
        else:
            event_type = Events.TELETHON_GROUP_MESSAGE

        await self._update_state(force=True)

        client = self.tg_client.client()
        msg_obj = event.message

        sender_name = await TelethonMessageParser.get_sender_name(msg_obj)
        chat = await event.get_chat()
        chat_name = utils.get_display_name(chat) if chat else "Unknown"

        fwd_info = await TelethonMessageParser.parse_forward(msg_obj)

        topic_id = None
        topic_name = None
        if getattr(msg_obj, "reply_to", None) and getattr(
            msg_obj.reply_to, "forum_topic", False
        ):
            topic_id = msg_obj.reply_to.reply_to_top_id or msg_obj.reply_to.reply_to_msg_id
            if topic_id:
                try:
                    topic_msg = await client.get_messages(chat, ids=topic_id)
                    if (
                        topic_msg
                        and getattr(topic_msg, "action", None)
                        and hasattr(topic_msg.action, "title")
                    ):
                        topic_name = topic_msg.action.title
                except Exception:
                    pass

        is_reply, reply_id = TelethonMessageParser.determine_reply(msg_obj, topic_id)
        reply_info = await TelethonMessageParser.parse_reply(client, chat, is_reply, reply_id)

        media_tag = TelethonMessageParser.parse_media(msg_obj)
        msg_text = msg_obj.text or ""
        base_text = f"{media_tag} {msg_text}".strip() if media_tag else msg_text

        enriched_message = f"{base_text}{fwd_info}{reply_info}".strip()

        payload = {
            "message": enriched_message,
            "raw_text": msg_text,
            "sender_name": sender_name,
            "chat_name": chat_name,
            "chat_id": event.chat_id,
            "msg_id": msg_obj.id,
        }

        if topic_id:
            payload["topic_id"] = topic_id
            if topic_name:
                payload["topic_name"] = topic_name

        if event.mentioned:
            unread_count = await self._get_unread_count(chat)
            limit = min(50, max(self.config.incoming_history_limit, unread_count))
            history = await self._fetch_recent_history(chat, limit=limit)
            if history:
                payload["recent_history"] = history

        await self.bus.publish(event_type, **payload)

    async def _on_reaction(self, event: Any) -> None:
        """Intercepts message emoji reactions."""
        if not isinstance(event, UpdateMessageReactions):
            return

        await self._update_state()

        try:
            chat_id = utils.get_peer_id(event.peer)
        except Exception:
            chat_id = "Unknown"

        reactions_str = "Reactions removed"
        if getattr(event, "reactions", None) and getattr(event.reactions, "results", None):
            r_list = [
                f"{getattr(r.reaction, 'emoticon', '[CustomEmoji]')} x{r.count}"
                for r in event.reactions.results
            ]
            if r_list:
                reactions_str = ", ".join(r_list)

        await self.bus.publish(
            Events.TELETHON_MESSAGE_REACTION,
            chat_id=chat_id,
            message_id=event.msg_id,
            reactions=reactions_str,
        )

    async def _on_channel_message(self, event: events.NewMessage.Event) -> None:
        """Intercepts channel posts."""
        await self._update_state()

        client = self.tg_client.client()
        msg_obj = event.message

        sender_name = await TelethonMessageParser.get_sender_name(msg_obj)
        chat = await event.get_chat()
        chat_name = utils.get_display_name(chat) if chat else "Unknown"

        fwd_info = await TelethonMessageParser.parse_forward(msg_obj)
        is_reply, reply_id = TelethonMessageParser.determine_reply(msg_obj, None)
        reply_info = await TelethonMessageParser.parse_reply(client, chat, is_reply, reply_id)

        media_tag = TelethonMessageParser.parse_media(msg_obj)
        msg_text = msg_obj.text or ""
        base_text = f"{media_tag} {msg_text}".strip() if media_tag else msg_text

        enriched_message = f"{base_text}{fwd_info}{reply_info}".strip()

        payload = {
            "message": enriched_message,
            "raw_text": msg_text,
            "sender_name": sender_name,
            "chat_name": chat_name,
            "chat_id": event.chat_id,
            "msg_id": msg_obj.id,
        }

        await self.bus.publish(Events.TELETHON_CHANNEL_MESSAGE, **payload)

    async def _on_chat_action(self, event: events.ChatAction.Event) -> None:
        """Intercepts system actions in chat (user joined, pin, photo change)."""
        await self._update_state()

        chat = await event.get_chat()
        chat_name = utils.get_display_name(chat) if chat else "Unknown"

        action_text = "[System Action] A system event occurred in the chat."

        users = [utils.get_display_name(u) for u in event.users] if event.users else []
        users_str = ", ".join(users) if users else "Someone"

        if event.user_joined:
            action_text = f"[System Action] {users_str} joined the chat."
        elif event.user_added:
            action_text = f"[System Action] {users_str} was added to the chat."
        elif event.user_left:
            action_text = f"[System Action] {users_str} left the chat."
        elif event.user_kicked:
            action_text = f"[System Action] {users_str} was kicked."
        elif event.created:
            action_text = f"[System Action] Chat '{event.new_title or chat_name}' was created."
        elif event.new_title:
            action_text = f"[System Action] Chat title was changed to '{event.new_title}'."
        elif event.new_photo or event.photo_deleted:
            action_text = "[System Action] Chat photo was updated or deleted."
        elif event.new_pin:
            action_text = "[System Action] New message pinned in the chat."

        payload = {
            "message": action_text,
            "sender_name": "System",
            "chat_name": chat_name,
            "chat_id": event.chat_id,
        }

        await self.bus.publish(Events.TELETHON_CHAT_ACTION, **payload)

    # ==========================================================
    # HELPERS
    # ==========================================================

    async def _fetch_recent_history(self, target_entity: Any, limit: int = 5) -> str:
        """
        Pulls N last messages of the chat (history) for injection into the event.
        """
        if not target_entity:
            return ""

        try:
            client = self.tg_client.client()
            msgs = await client.get_messages(target_entity, limit=limit + 1)

            if len(msgs) <= 1:
                return ""

            lines = []
            for msg in reversed(msgs[1:]):
                formatted = await TelethonMessageParser.build_string(
                    client=client,
                    target_entity=target_entity,
                    msg=msg,
                    timezone=self.tg_client.timezone,
                    truncate_text_flag=True,
                )
                lines.append(formatted)

            return "\n" + "\n\n".join(lines)

        except Exception as e:
            main_logger.error(f"[Telegram Telethon] Failed to fetch history: {e}")
            return ""

    async def _get_unread_count(self, peer: Any) -> int:
        """Determines the unread messages count in the chat."""
        try:
            client = self.tg_client.client()
            peer_dialogs = await client(GetPeerDialogsRequest(peers=[peer]))
            if peer_dialogs and peer_dialogs.dialogs:
                return peer_dialogs.dialogs[0].unread_count
        except Exception as e:
            main_logger.debug(f"[TelethonEvents] Error obtaining unread_count: {e}")
        return 0

    async def _get_topics(self, client: Any, entity: Any, limit: int = 100) -> list:
        """Gets forum topics list via Raw API Telethon."""
        try:
            from telethon.tl.functions.channels import GetForumTopicsRequest
        except ImportError:
            main_logger.debug("[TelethonChats] GetForumTopicsRequest unavailable.")
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
            main_logger.error(f"[TelethonChats] Error _get_topics: {e}")
            return []
