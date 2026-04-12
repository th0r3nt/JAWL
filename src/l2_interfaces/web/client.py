class WebClient:
    """
    Базовый клиент веб-интерфейса.
    Хранит общие константы и настройки для веб-скиллов.
    """

    def __init__(self, request_timeout: int = 15, max_page_chars: int = 15000):
        self.timeout = request_timeout
        self.max_page_chars = max_page_chars
