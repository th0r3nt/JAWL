"""
L0 State для AIogram.

Служит приборной панелью, чтобы агент не тратил API-запросы на проверку новых сообщений.
"""


class AiogramState:
    """
    Хранит состояние Aiogram-клиента (Bot API).
    Т.к. боты не могут запрашивать список всех своих чатов у серверов Telegram,
    мы храним N последних чатов, откуда приходили сообщения, локально в памяти.
    """

    def __init__(self, number_of_last_chats: int = 10):
        self.is_online = False
        self.number_of_last_chats = number_of_last_chats
        self.last_chats = "Список диалогов пуст."
        
        # Внутренний кэш: {chat_id: "строка форматирования"}
        self._chats_cache: dict[int, str] = {}