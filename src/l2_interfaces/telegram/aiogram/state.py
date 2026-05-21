"""
L0 State for the Aiogram interface.

Stores connection status, chat limit, and the latest dialogues cache.
"""


class AiogramState:
    """
    Stores the state of the Aiogram client (Bot API).
    Since bots cannot query the list of all their chats from Telegram servers,
    we store the N latest chats from which messages arrived locally in memory.
    """

    def __init__(self, number_of_last_chats: int = 10):
        self.is_online = False
        self.number_of_last_chats = number_of_last_chats
        self.last_chats = "Dialogues list is empty."

        # Internal cache: {chat_id: "formatting string"}
        self._chats_cache: dict[int, str] = {}

        self.recent_messages: dict[int, list[str]] = {}
        self.recent_messages_limit: int = 5
