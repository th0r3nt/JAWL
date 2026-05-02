class WebRSSState:
    """
    Хранит состояние RSS-модуля.
    Показывает последнюю активность и свежие новости из лент.
    """

    def __init__(self, recent_limit: int = 5):
        self.is_online = False
        self.recent_limit = recent_limit
        self.feeds_status = "Ожидание инициализации..."
        self.latest_news = "Нет загруженных новостей."