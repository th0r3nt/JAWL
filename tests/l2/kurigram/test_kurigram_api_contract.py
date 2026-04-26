from __future__ import annotations

from inspect import signature
from typing import Any

import pytest


try:
    from pyrogram import Client, raw
    from pyrogram.enums import ParseMode
    from pyrogram.handlers import MessageHandler, RawUpdateHandler
    from pyrogram.types import ChatPermissions

    try:
        from pyrogram.types import ChatAdministratorRights
    except ImportError:  # pragma: no cover - older Pyrogram compatibility name
        from pyrogram.types import ChatPrivileges as ChatAdministratorRights
except ImportError as exc:  # pragma: no cover - this is the contract under test
    pytest.fail(
        "Kurigram/Pyrogram must be installed and importable as `pyrogram` for the "
        f"Telegram User API contract tests: {exc}",
        pytrace=False,
    )


_SELF = object()
_VALUE = object()


def _assert_bindable(callable_obj: Any, used_by: str, *args: Any, **kwargs: Any) -> None:
    sig = signature(callable_obj)
    try:
        sig.bind_partial(*args, **kwargs)
    except TypeError as exc:
        name = getattr(callable_obj, "__qualname__", repr(callable_obj))
        pytest.fail(
            f"{name}{sig} does not accept the argument shape used by {used_by}: {exc}",
            pytrace=False,
        )


def _client_method(name: str, used_by: str) -> Any:
    method = getattr(Client, name, None)
    if method is None:
        pytest.fail(
            f"pyrogram.Client is missing `{name}`, required by {used_by}.",
            pytrace=False,
        )
    return method


def _raw_attr(path: str, used_by: str) -> Any:
    obj: Any = raw
    for part in path.split("."):
        obj = getattr(obj, part, None)
        if obj is None:
            pytest.fail(
                f"pyrogram.raw is missing `{path}`, required by {used_by}.",
                pytrace=False,
            )
    return obj


@pytest.mark.parametrize(
    ("method_name", "used_by", "args", "kwargs"),
    [
        (
            "__init__",
            "KurigramClient.start",
            ("session_name",),
            {"api_id": 1, "api_hash": "hash", "workdir": "."},
        ),
        ("start", "KurigramClient.start", (), {}),
        ("stop", "KurigramClient.stop", (), {}),
        ("get_me", "KurigramClient.start/update_profile_state", (), {}),
        ("get_chat", "KurigramClient._get_profile_details/chats/events", ("chat",), {}),
        (
            "send_message",
            "KurigramMessages.send_message",
            (),
            {
                "chat_id": "chat",
                "text": "text",
                "disable_notification": False,
                "parse_mode": ParseMode.MARKDOWN,
                "reply_to_message_id": 1,
                "message_thread_id": 2,
                "schedule_date": _VALUE,
            },
        ),
        (
            "send_document",
            "KurigramMessages.send_file",
            (),
            {"chat_id": "chat", "document": "file", "caption": "caption", "parse_mode": ParseMode.MARKDOWN},
        ),
        (
            "get_messages",
            "KurigramMessages/Polls/Events message lookup",
            (),
            {"chat_id": "chat", "message_ids": 1, "replies": 0},
        ),
        ("get_messages", "KurigramEvents._get_message_by_id fallback", ("chat", 1), {}),
        (
            "download_media",
            "KurigramMessages.download_file/Account.download_avatar",
            (_VALUE,),
            {"file_name": "path"},
        ),
        (
            "forward_messages",
            "KurigramMessages.forward_message",
            (),
            {"chat_id": "to", "from_chat_id": "from", "message_ids": 1},
        ),
        (
            "delete_messages",
            "KurigramMessages.delete_message",
            (),
            {"chat_id": "chat", "message_ids": 1},
        ),
        (
            "edit_message_text",
            "KurigramMessages.edit_message",
            (),
            {"chat_id": "chat", "message_id": 1, "text": "text", "parse_mode": ParseMode.MARKDOWN},
        ),
        (
            "search_messages",
            "KurigramMessages.search_messages",
            (),
            {"chat_id": "chat", "query": "needle", "limit": 10},
        ),
        ("read_chat_history", "KurigramMessages.send_message/Chats._mark_chat_read", ("chat",), {}),
        ("get_dialogs_count", "KurigramChats.get_chats", (), {}),
        ("get_dialogs", "KurigramChats/Events dialog iteration", (), {"limit": 10}),
        ("get_dialogs", "KurigramChats._get_draft_text fallback", (), {}),
        ("get_chat_history", "KurigramChats.read_chat/Events history", ("chat",), {"limit": 10}),
        (
            "get_discussion_replies",
            "KurigramChats.read_chat/_latest_topic_message_id",
            ("chat", 1),
            {"limit": 10},
        ),
        ("join_chat", "KurigramChats.join_chat/join_channel_discussion", ("chat",), {}),
        ("leave_chat", "KurigramChats.leave_chat", ("chat",), {}),
        (
            "add_chat_members",
            "KurigramChats.invite_to_chat",
            ("chat", ["user"]),
            {"forward_limit": 0},
        ),
        ("resolve_peer", "KurigramAccount/Chats/Messages raw helpers", ("peer",), {}),
        ("create_supergroup", "KurigramAdmin.create_channel(is_megagroup=True)", (), {"title": "title", "description": "about"}),
        ("create_channel", "KurigramAdmin.create_channel", (), {"title": "title", "description": "about"}),
        ("set_chat_username", "KurigramAdmin.set_channel_username", ("chat", "username"), {}),
        (
            "set_chat_discussion_group",
            "KurigramAdmin.set_discussion_group",
            (),
            {"chat_id": "channel", "discussion_chat_id": "group"},
        ),
        ("set_chat_title", "KurigramAdmin.edit_chat_title", ("chat", "title"), {}),
        ("set_chat_description", "KurigramAdmin.edit_chat_description", ("chat", "description"), {}),
        ("set_chat_photo", "KurigramAdmin.edit_chat_avatar", ("chat",), {"photo": "path"}),
        ("export_chat_invite_link", "KurigramAdmin.create_invite_link", ("chat",), {}),
        ("get_chat_members", "KurigramAdmin.get_participants/Moderation.get_banned_users", ("chat",), {"limit": 10}),
        ("get_chat_members", "KurigramModeration.get_banned_users", ("chat",), {"filter": _VALUE, "limit": 10}),
        (
            "promote_chat_member",
            "KurigramAdmin.promote_user/demote_user",
            (),
            {"chat_id": "chat", "user_id": "user", "privileges": _VALUE},
        ),
        ("pin_chat_message", "KurigramAdmin.pin_message", ("chat", 1), {"disable_notification": False}),
        ("unpin_chat_message", "KurigramAdmin.unpin_message", ("chat", 1), {}),
        ("create_forum_topic", "KurigramAdmin.create_topic", ("chat", "title"), {}),
        ("ban_chat_member", "KurigramModeration.ban_user/kick_user", ("chat", "user"), {}),
        ("block_user", "KurigramModeration.ban_user(global)", ("user",), {}),
        ("unban_chat_member", "KurigramModeration.unban_user/kick_user", ("chat", "user"), {}),
        ("unblock_user", "KurigramModeration.unban_user(global)", ("user",), {}),
        (
            "restrict_chat_member",
            "KurigramModeration.mute_user",
            ("chat", "user"),
            {"permissions": _VALUE, "until_date": _VALUE},
        ),
        ("get_blocked_message_senders", "KurigramModeration.get_banned_users(global)", (), {"limit": 10}),
        ("send_poll", "KurigramPolls.create_poll", (), {"chat_id": "chat", "question": "q", "options": ["a", "b"]}),
        ("vote_poll", "KurigramPolls.vote_in_poll", ("chat", 1, [0]), {}),
        ("stop_poll", "KurigramPolls.close_poll", ("chat", 1), {}),
        ("send_reaction", "KurigramReactions.set/remove_reaction", (), {"chat_id": "chat", "message_id": 1, "emoji": "👍"}),
        ("send_reaction", "KurigramReactions.remove_reaction", (), {"chat_id": "chat", "message_id": 1}),
        ("update_profile", "KurigramAccount.change_username", (), {"first_name": "Name", "last_name": "Surname"}),
        ("update_profile", "KurigramAccount.change_bio", (), {"bio": "bio"}),
        ("set_profile_photo", "KurigramAccount.change_avatar", (), {"photo": "path"}),
        (
            "add_contact",
            "KurigramAccount.add_contact",
            (),
            {
                "user_id": "user",
                "first_name": "Name",
                "last_name": "Surname",
                "phone_number": "",
                "share_phone_number": False,
            },
        ),
        ("get_chat_photos", "KurigramAccount.download_avatar", ("chat",), {"limit": 1}),
    ],
)
def test_high_level_kurigram_client_calls_accept_migration_arguments(
    method_name: str, used_by: str, args: tuple[Any, ...], kwargs: dict[str, Any]
) -> None:
    method = _client_method(method_name, used_by)
    _assert_bindable(method, used_by, _SELF, *args, **kwargs)


@pytest.mark.parametrize(
    ("callable_obj", "used_by", "args", "kwargs"),
    [
        (MessageHandler, "KurigramEvents.start message listeners", (_VALUE, _VALUE), {}),
        (RawUpdateHandler, "KurigramEvents.start reaction listener", (_VALUE,), {}),
        (ChatPermissions, "KurigramModeration.mute_user", (), {"can_send_messages": False}),
        (
            ChatAdministratorRights,
            "KurigramAdmin._chat_administrator_rights",
            (),
            {
                "can_manage_chat": True,
                "can_change_info": True,
                "can_post_messages": True,
                "can_edit_messages": True,
                "can_delete_messages": True,
                "can_restrict_members": True,
                "can_invite_users": True,
                "can_pin_messages": True,
                "can_promote_members": True,
                "can_manage_topics": True,
            },
        ),
    ],
)
def test_kurigram_types_and_handlers_accept_migration_arguments(
    callable_obj: Any, used_by: str, args: tuple[Any, ...], kwargs: dict[str, Any]
) -> None:
    _assert_bindable(callable_obj, used_by, *args, **kwargs)


@pytest.mark.parametrize(
    ("raw_path", "used_by", "kwargs"),
    [
        (
            "types.InputReplyToMessage",
            "KurigramMessages._draft_reply_to",
            {"reply_to_msg_id": 1, "top_msg_id": 1},
        ),
        ("functions.messages.GetAllDrafts", "KurigramMessages/Chats draft reads", {}),
        (
            "functions.messages.SaveDraft",
            "KurigramMessages.edit_draft/delete_draft",
            {"peer": _VALUE, "message": "draft", "reply_to": _VALUE},
        ),
        ("functions.contacts.Search", "KurigramChats.search_public_chats", {"q": "query", "limit": 5}),
        ("functions.channels.GetFullChannel", "KurigramChats.join_channel_discussion", {"channel": _VALUE}),
        (
            "functions.messages.GetForumTopics",
            "KurigramChats._get_topics",
            {"peer": _VALUE, "q": "", "offset_date": 0, "offset_id": 0, "offset_topic": 0, "limit": 10},
        ),
        (
            "functions.messages.ReadDiscussion",
            "KurigramChats._mark_chat_read",
            {"peer": _VALUE, "msg_id": 1, "read_max_id": 2},
        ),
        ("functions.messages.ReadMentions", "KurigramChats._mark_chat_read", {"peer": _VALUE, "top_msg_id": 1}),
        ("functions.messages.ReadReactions", "KurigramChats._mark_chat_read", {"peer": _VALUE, "top_msg_id": 1}),
        ("functions.messages.GetPeerDialogs", "KurigramChats._read_outbox_max_id", {"peers": [_VALUE]}),
        ("types.InputDialogPeer", "KurigramChats._read_outbox_max_id", {"peer": _VALUE}),
        ("types.InputChannel", "KurigramAccount/Chats input channel resolution", {"channel_id": 1, "access_hash": 2}),
        ("types.InputUser", "KurigramAccount._resolve_input_user", {"user_id": 1, "access_hash": 2}),
        ("types.InputUserSelf", "KurigramAccount._resolve_input_user/KurigramClient._get_profile_details", {}),
        ("types.InputChannelEmpty", "KurigramAccount.set_personal_channel(remove)", {}),
        ("functions.users.GetFullUser", "KurigramAccount.get_user_info/KurigramClient._get_profile_details", {"id": _VALUE}),
        ("functions.account.UpdatePersonalChannel", "KurigramAccount.set_personal_channel", {"channel": _VALUE}),
    ],
)
def test_raw_kurigram_constructors_accept_migration_arguments(
    raw_path: str, used_by: str, kwargs: dict[str, Any]
) -> None:
    raw_callable = _raw_attr(raw_path, used_by)
    _assert_bindable(raw_callable, used_by, **kwargs)
