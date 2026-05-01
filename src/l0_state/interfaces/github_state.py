"""
L0 State для интерфейса GitHub.

Хранит статусы отслеживаемых репозиториев, уведомления и историю запросов.
"""


class GithubState:
    """
    Хранит состояние Github-клиента.
    Флаг is_online, информация об аккаунте агента, его репозиториях,
    уведомлениях и короткая история запросов.
    """

    def __init__(self, history_limit: int = 10):
        self.is_online = False
        self.history_limit = history_limit
        self.history: list[str] = []

        self.account_info = "Ожидание инициализации..."
        self.own_repos = "Репозитории неизвестны."
        self.unread_notifications = "Уведомлений нет."

        # Watchers: { "owner/repo": "last_event_id" }
        self.tracked_repos: dict[str, str] = {}

        # MRU-кэш последних событий для вывода в контекст агента
        self.recent_watcher_events: list[str] = []

    def add_history(self, entry: str) -> None:
        """Добавляет запись в начало истории (самые свежие сверху)."""
        self.history.insert(0, entry)
        if len(self.history) > self.history_limit:
            self.history.pop()

    def add_watcher_event(self, event_str: str) -> None:
        """Добавляет событие репозитория в контекст."""
        self.recent_watcher_events.insert(0, event_str)
        if len(self.recent_watcher_events) > 10:  # Храним последние 10 событий
            self.recent_watcher_events.pop()

    @property
    def github_history(self) -> str:
        if not self.history:
            return "История пуста."
        return "\n".join(f"- {item}" for item in self.history)
