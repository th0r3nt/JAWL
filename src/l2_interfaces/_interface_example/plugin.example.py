"""
Плагин (Plugin) пользовательского L2-интерфейса.

Этот файл - точка входа для вашего модуля. Фреймворк автоматически найдет его (Plugin Discovery).
Здесь происходит внедрение зависимостей (DI): мы создаем L0 State, настраиваем Клиента,
Воркера (Events) и регистрируем Навыки (Skills).

Советы для разработчиков:
1. Не пишите здесь бизнес-логику. Plugin нужен только для "сборки" конструктора.
2. Чтобы ваш плагин можно было включать/выключать, вам нужно добавить его структуру в
   схемы Pydantic в `src/utils/settings.py` (в класс InterfacesConfig).
"""

from typing import List, Any, Dict, Optional
from src.utils.logger import main_logger
from src.l2_interfaces.base import BaseInterface
from src.l3_agent.skills.registry import register_instance  # noqa: F401
from src.l3_agent.context.registry import ContextSection  # noqa: F401
from src.system.container import SystemContainer
from src.utils.settings import InterfacesConfig

# В реальном коде импортируйте ваши модули:
# from src.l2_interfaces.my_module.state import MyState
# from src.l2_interfaces.my_module.client import MyClient
# from src.l2_interfaces.my_module.events import MyEvents
# from src.l2_interfaces.my_module.skills.tools import MySkills


class ExamplePlugin(BaseInterface):
    """
    Главный класс плагина. Наследуется от BaseInterface, что гарантирует
    наличие нужных свойств и методов для инициализатора.
    """

    @property
    def name(self) -> str:
        return "EXAMPLE INTERFACE"

    @property
    def description(self) -> str:
        return "Test description for the agent."

    def is_enabled(self, config: InterfacesConfig) -> bool:
        # В реальности здесь будет что-то вроде: return config.my_module.enabled
        return False

    def setup(
        self, container: SystemContainer, env_vars: Dict[str, Optional[str]]
    ) -> List[Any]:
        """
        Инициализирует интерфейс и интегрирует его в ядро JAWL.

        Args:
            container: DI-контейнер фреймворка (через него мы получаем доступ к базам, шине событий).
            env_vars: Словарь секретов (читается из .env).

        Returns:
            List[Any]: Список компонентов жизненного цикла (обычно это client и events),
                       у которых оркестратор вызовет методы .start() и .stop().
        """

        # 0. Извлекаем ключи
        # api_key = env_vars.get("MY_API_KEY")
        # if not api_key:
        #     main_logger.error(f"[{self.name}] Ключ API не найден. Отключен.")
        #     self.register_off_provider(container.context_registry)
        #     return []

        # 1. Создаем стейт (приборную панель) и сохраняем его в контейнер
        # state = MyState()
        # container.l0_states["example"] = state

        # 2. Инициализируем Клиент (Отвечает за I/O, сессии, запросы)
        # client = MyClient(state=state, api_key=api_key)

        # 3. Инициализируем Воркер событий (Отвечает за фоновый поллинг)
        # events = MyEvents(client=client, event_bus=container.event_bus)

        # 4. Регистрируем Навыки (То, что LLM сможет вызывать)
        # register_instance(MySkills(client))

        # 5. Регистрируем Контекст (То, что LLM будет видеть на своей приборной панели)
        # container.context_registry.register_provider(
        #     name=self.name.lower().replace(" ", "_"),
        #     provider_func=client.get_context_block,
        #     section=ContextSection.INTERFACES,
        # )

        main_logger.info(f"[{self.name}] Пользовательский интерфейс загружен.")

        # Обязательно возвращаем объекты, у которых есть async def start() и async def stop()
        # return [client, events]
        return []
