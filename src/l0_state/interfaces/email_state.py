"""
L0 State для интерфейса Email.

Пассивная панель входящих писем, обновляемая фоновым IMAP поллером.
"""

class EmailState:
    """
    Хранит состояние Email-клиента.
    Отображает информацию об аккаунте и список последних писем в ящике.
    """

    def __init__(self, recent_limit: int = 10):
        self.is_online = False
        self.recent_limit = recent_limit

        self.account_info = "Ожидание инициализации..."
        self.mailbox_preview = "Писем нет."


