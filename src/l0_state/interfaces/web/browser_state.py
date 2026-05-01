class WebBrowserState:
    """
    Хранит состояние полноценного веб-браузера (Playwright).
    Отображает текущий URL и дерево доступности (AOM) текущей страницы.
    """

    def __init__(self):
        self.is_online = False
        self.is_open = False

        self.current_url = "None"
        self.page_title = "None"
        self.viewport = "Браузер закрыт."

        self.history: list[str] = []

    def add_history(self, action: str):
        self.history.insert(0, action)
        if len(self.history) > 10:
            self.history.pop()