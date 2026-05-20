"""
Кастомные исключения для слоя взаимодействия с LLM.
Позволяют строго типизировать обработку ошибок без парсинга строк.
"""


class AllKeysExhaustedError(Exception):
    """
    Выбрасывается ротатором, когда все доступные API-ключи
    находятся во временной блокировке (Rate Limit/Cooldown).
    """

    def __init__(self, wait_time: int) -> None:
        self.wait_time = wait_time
        super().__init__(
            f"Все API ключи исчерпали лимиты. Необходимо подождать {wait_time} сек."
        )
