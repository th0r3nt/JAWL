"""
L0 State для Telethon.

Хранит MRU-кэши (Most Recently Used) диалогов и метаданные профилей.
Служит приборной панелью, чтобы агент не тратил API-запросы на проверку новых сообщений.
"""

class TelethonState:
    """
    Хранит состояние Telethon-клиента (User API).
    Последние n диалогов, статус непрочитанных.
    Обновляется слушателями (telethon/events.py) в фоне.
    """

    def __init__(self, number_of_last_chats: int = 15, private_chat_history_limit: int = 3):
        self.is_online = False
        self.number_of_last_chats = number_of_last_chats
        self.private_chat_history_limit = private_chat_history_limit

        # Хранилище последних чатов (Например: User | ID: 123 | Название: Bob [UNREAD: 1])
        self.last_chats = ""
        self.account_info = "Данные профиля загружаются..."






