"""
Stateful-клиент пользовательского интерфейса.

Здесь живет вся логика соединения с внешним миром (HTTP-сессии, подключение к базам данных,
управление токенами авторизации).

Советы для разработчиков:
Если вашему клиенту нужны вспомогательные функции (например, парсинг сложного HTML
или форматирование дат специфичного API), не пишите их здесь.
Создайте файл `src/l2_interfaces/ваше_название/utils.py` и вынесите вспомогательную логику туда (священный DRY).
"""

from typing import Any


class ExampleClient:
    """Менеджер соединения с вашим сервисом."""

    def __init__(self, state: Any, api_key: str) -> None:
        """
        Инициализация клиента.
        
        Args:
            state: Ссылка на L0 State из приборной панели агента.
            api_key: Ключ доступа.
        """

        self.state = state
        self.api_key = api_key
        # self.session = None  # Например, aiohttp.ClientSession

    async def start(self) -> None:
        """
        Метод жизненного цикла. Вызывается оркестратором (main.py) при старте системы.
        Здесь нужно открывать HTTP-сессии или делать тестовые запросы (ping) к API.
        """
        # self.session = aiohttp.ClientSession(headers={"Authorization": f"Bearer {self.api_key}"})
        self.state.is_online = True

    async def stop(self) -> None:
        """
        Метод жизненного цикла. Вызывается при выключении системы.
        Здесь необходимо безопасно закрыть все сокеты и освободить ресурсы.
        """
        # if self.session:
        #     await self.session.close()
        self.state.is_online = False

    async def get_context_block(self, **kwargs: Any) -> str:
        """
        Провайдер контекста. Вызывается каждый раз, когда агент просыпается (Heartbeat).
        
        Returns:
            str: Markdown-отформатированный текст, который будет внедрен в System Prompt агента.
                 Старайтесь делать его максимально коротким и информативным.
        """
        if not getattr(self.state, "is_online", False):
            return "### EXAMPLE_SERVICE [OFF]\nИнтерфейс отключен."

        # Отдаем агенту кэшированные (MRU) данные из стейта:
        # data = self.state.recent_notifications
        data = "Нет новых уведомлений."
        
        return f"### EXAMPLE_SERVICE [ON]\n{data}"
