"""
L0 State for the Telethon interface.

Stores connection status, chat limit, and the latest dialogues cache.
"""


class TelethonState:
    """
    Stores the state of the Telethon client (User API).
    Last n dialogues, unread status.
    Updated by listeners (telethon/events.py) in the background.
    """

    def __init__(self, number_of_last_chats: int = 15, private_chat_history_limit: int = 3):
        self.is_online = False
        self.number_of_last_chats = number_of_last_chats
        self.private_chat_history_limit = private_chat_history_limit

        # Last chats storage (e.g. User | ID: 123 | Name: Bob [UNREAD: 1])
        self.last_chats = ""
        self.account_info = "Profile data loading..."
